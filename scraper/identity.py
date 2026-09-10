"""Resolving a listing to a canonical product identity.

Identity is what makes a dossier addressable: without a stable key there is
nothing to look knowledge up by, and no way to share that knowledge across the
thousands of listings that describe the same product.

The resolution deliberately runs *after* extraction rather than on the raw title.
By then the make, model and engine code are already separate typed fields, so
this is a normalisation problem rather than a parsing one.

The guiding rule is to under-resolve rather than mis-resolve. A missing key costs
one dossier lookup; a wrong key attaches another product's known defects to this
listing and mis-scores it with full confidence.
"""

import logging
import re

import dossiers

logger = logging.getLogger(__name__)

# Field ids, in key order, that identify a product in each category.
IDENTITY_FIELDS = {
    "vehicles/cars": ("make", "model", "generationCode", "engineCode"),
    "vehicles/motorcycles": ("make", "model"),
    "electronics/laptops": ("brand", "modelName"),
    "electronics/phones": ("brand", "modelName"),
}

# Parts without which a key is meaningless: a generation code alone identifies
# nothing, so these must all be present before a key is built.
REQUIRED_FIELDS = {
    "vehicles/cars": ("make", "model"),
    "vehicles/motorcycles": ("make", "model"),
    "electronics/laptops": ("brand", "modelName"),
    "electronics/phones": ("brand", "modelName"),
}

_NOISE = re.compile(
    r"\b(zu verkaufen|gebraucht|top zustand|neuwertig|guter zustand|defekt|"
    r"ovp|inkl|mit|und|sehr gut|privatverkauf|no paypal|vb)\b",
    re.IGNORECASE,
)
_PUNCT = re.compile(r"[^\w\s./-]+", re.UNICODE)
_SPACE = re.compile(r"\s+")


def normalize_part(value):
    """Reduces a free-text field to a key-safe token.

    Sellers write "BMW 320d Touring !!! TOP ZUSTAND" where the product is
    "320d touring"; the decoration must not end up in the key or two listings
    for the same car would get different dossiers.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() in ("unknown", "none", "null", "-"):
        return ""

    text = _NOISE.sub(" ", text)
    text = _PUNCT.sub(" ", text)
    text = _SPACE.sub(" ", text).strip().lower()
    return text.replace(" ", "-")


def field_value(facts, field_id):
    entry = (facts.get("criteria") or {}).get(field_id)
    if isinstance(entry, dict):
        return entry.get("value")
    return entry


def resolve(facts, playbook):
    """Returns (identity_key, parts) or (None, reason) when identity is unclear.

    `parts` is the ordered list of resolved components, useful for building the
    human-readable product name a research prompt needs.
    """
    key_spec = IDENTITY_FIELDS.get(playbook["key"])
    if not key_spec:
        return None, f"no identity fields defined for {playbook['key']}"

    required = REQUIRED_FIELDS.get(playbook["key"], ())
    parts = []
    for field_id in key_spec:
        normalized = normalize_part(field_value(facts, field_id))
        if not normalized and field_id in required:
            return None, f"required identity field {field_id} is missing"
        if normalized:
            parts.append(normalized)

    if not parts:
        return None, "no identity fields could be resolved"

    return dossiers.identity_key(*parts), parts


def display_name(parts):
    """The product name a research prompt should be given."""
    return " ".join(part.replace("-", " ") for part in parts)


def resolve_or_log(facts, playbook, listing_id=None):
    """Convenience wrapper that logs rather than raising on an unresolved identity."""
    key, detail = resolve(facts, playbook)
    if key is None:
        logger.info(
            "Identity unresolved for listing %s (%s): %s",
            listing_id,
            playbook["key"],
            detail,
        )
        return None, None
    return key, detail
