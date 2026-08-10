"""Buyer-independent fact extraction.

This is the seam the whole cost model rests on. `get_or_extract` produces a
category fact sheet for a listing and caches it, so N buyers interested in the
same listing cost one extraction rather than N. Nothing in this module may take
a buyer's intent as input — if it ever needs to, the seam has been broken.
"""

import json
import logging

import fact_sheets
import playbooks
from prompts import build_evaluation_prompt

logger = logging.getLogger(__name__)


class ExtractionResult:
    __slots__ = ("facts", "from_cache", "playbook_key", "unknown_intent_fields")

    def __init__(self, facts, from_cache, playbook_key, unknown_intent_fields=()):
        self.facts = facts
        self.from_cache = from_cache
        self.playbook_key = playbook_key
        self.unknown_intent_fields = list(unknown_intent_fields)

    def __repr__(self):
        origin = "cache" if self.from_cache else "model"
        return f"<ExtractionResult {self.playbook_key} from={origin}>"


def build_extraction_config(playbook):
    """The item_json-shaped config the prompt builder expects for a playbook.

    Extraction always asks for the full canonical field set, never a subset, so
    one sheet can serve any buyer's intent without re-extraction.
    """
    return {
        "fields": playbooks.extraction_fields(playbook),
        "dimensions_enabled": True,
    }


def get_or_extract(
    conn,
    listing,
    playbook,
    call_model,
    expert_knowledge="",
    force=False,
):
    """Returns an ExtractionResult, calling the model only on a cache miss.

    `listing` is a mapping with at least id, title, detailed_description and
    details. `call_model` is called as call_model(prompt, fields) and returns the
    parsed facts dict; it receives the field definitions so it can validate the
    response against them. It is injected so this module stays free of provider
    concerns and testable without network access.
    """
    listing_id = listing["id"]
    key = playbook["key"]
    version = playbook.get("version", 1)
    text_hash = fact_sheets.source_hash(
        listing.get("title"),
        listing.get("detailed_description"),
        listing.get("details"),
    )

    if not force:
        cached = fact_sheets.get(
            conn,
            listing_id,
            key,
            playbook_version=version,
            expected_hash=text_hash,
        )
        if cached is not None:
            return ExtractionResult(cached, True, key)

    config = build_extraction_config(playbook)
    prompt = build_evaluation_prompt(
        listing.get("title") or "",
        listing.get("details") or "",
        listing.get("detailed_description") or "",
        json.dumps(config, ensure_ascii=False),
        expert_knowledge or "",
    )

    facts = call_model(prompt, config["fields"])
    if facts is None:
        raise RuntimeError(f"Extraction produced no facts for listing {listing_id}")

    fact_sheets.put(conn, listing_id, key, version, facts, text_hash)
    logger.info("Extracted fact sheet for %s against %s v%s", listing_id, key, version)
    return ExtractionResult(facts, False, key)


def score_against_intent(facts, playbook, intent, score_listing):
    """Scores a cached fact sheet against one buyer's intent.

    Pure and model-free by construction: this is the operation that runs once per
    (buyer x listing) pair, so it must never become expensive.
    """
    intent_fields = intent.get("fields", [])
    resolved, unknown = playbooks.resolve_scoring_fields(playbook, intent_fields)

    if unknown:
        logger.warning(
            "Intent references fields absent from playbook %s: %s. "
            "They are ignored; add them to the playbook to make them scoreable.",
            playbook["key"],
            ", ".join(str(u) for u in unknown),
        )

    config = {
        "fields": resolved,
        "dimensions_enabled": intent.get("dimensions_enabled", True),
    }
    if "dimensions_weight" in intent:
        config["dimensions_weight"] = intent["dimensions_weight"]

    return score_listing(facts, config), unknown
