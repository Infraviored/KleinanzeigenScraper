import sqlite3

import pytest

import fact_sheets
import playbooks
from extraction import get_or_extract, score_against_intent
from scoring import score_listing

LISTING = {
    "id": "test-1",
    "title": 'MacBook Pro 15" 2019 | i7 | 16 GB',
    "detailed_description": "Sehr guter Zustand, 16GB RAM, 256GB SSD, Netzteil dabei.",
    "details": "Zustand: Gut",
}

FACTS = {
    "criteria": {
        "ramGb": {"value": 16},
        "storageGb": {"value": 256},
        "cpuTier": {"value": 4},
        "conditionGrade": {"value": "gut"},
        "hasFunctionalDefect": {"value": "no"},
        "accountLocked": {"value": "no"},
    },
    "dimensions": {},
}


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    fact_sheets.ensure_schema(connection)
    yield connection
    connection.close()


@pytest.fixture
def laptops():
    return playbooks.get_playbook("electronics/laptops")


class CountingModel:
    """Stands in for the LLM so the test can count calls rather than tokens."""

    def __init__(self, facts=None):
        self.calls = 0
        self.facts = facts if facts is not None else FACTS
        self.last_prompt = None

    def __call__(self, prompt):
        self.calls += 1
        self.last_prompt = prompt
        return self.facts


def test_second_buyer_costs_no_model_call(conn, laptops):
    """The central claim of the architecture, asserted directly."""
    model = CountingModel()

    first = get_or_extract(conn, LISTING, laptops, model)
    assert first.from_cache is False
    assert model.calls == 1

    # A different buyer, same listing.
    second = get_or_extract(conn, LISTING, laptops, model)
    assert second.from_cache is True
    assert model.calls == 1, "cached listing must not trigger a second extraction"
    assert second.facts == first.facts


def test_edited_listing_text_invalidates_the_sheet(conn, laptops):
    model = CountingModel()
    get_or_extract(conn, LISTING, laptops, model)

    edited = dict(LISTING, detailed_description="Doch nur 8GB RAM, Display defekt.")
    result = get_or_extract(conn, edited, laptops, model)

    assert result.from_cache is False
    assert model.calls == 2


def test_new_playbook_version_invalidates_the_sheet(conn, laptops):
    model = CountingModel()
    get_or_extract(conn, LISTING, laptops, model)

    bumped = dict(laptops, version=laptops.get("version", 1) + 1)
    result = get_or_extract(conn, LISTING, bumped, model)

    assert result.from_cache is False
    assert model.calls == 2


def test_force_bypasses_the_cache(conn, laptops):
    model = CountingModel()
    get_or_extract(conn, LISTING, laptops, model)
    result = get_or_extract(conn, LISTING, laptops, model, force=True)

    assert result.from_cache is False
    assert model.calls == 2


def test_extraction_asks_for_the_whole_playbook_not_a_buyer_subset(conn, laptops):
    model = CountingModel()
    get_or_extract(conn, LISTING, laptops, model)

    prompt = model.last_prompt
    for field in laptops["fields"]:
        assert f'"{field["id"]}"' in prompt, field["id"]


def test_units_and_enum_options_reach_the_prompt(conn, laptops):
    model = CountingModel()
    get_or_extract(conn, LISTING, laptops, model)
    prompt = model.last_prompt

    # A number field carries its unit, so the model does not invent one.
    assert "expressed in GB" in prompt
    # An enum field carries the exact allowed values.
    assert '"neuwertig"' in prompt and '"defekt"' in prompt


def test_one_sheet_serves_two_different_intents(conn, laptops):
    model = CountingModel()
    sheet = get_or_extract(conn, LISTING, laptops, model).facts

    demanding = {
        "fields": [
            {"id": "ramGb", "importance": "high", "buyer_wants": {"min": 32}},
            {
                "id": "hasFunctionalDefect",
                "importance": "high",
                "buyer_wants": {"match": False},
            },
        ],
        "dimensions_enabled": False,
    }
    modest = {
        "fields": [
            {"id": "ramGb", "importance": "high", "buyer_wants": {"min": 8}},
            {
                "id": "hasFunctionalDefect",
                "importance": "high",
                "buyer_wants": {"match": False},
            },
        ],
        "dimensions_enabled": False,
    }

    strict_result, _ = score_against_intent(sheet, laptops, demanding, score_listing)
    loose_result, _ = score_against_intent(sheet, laptops, modest, score_listing)

    assert model.calls == 1, "scoring must never call the model"
    assert loose_result.score > strict_result.score


def test_intent_referencing_an_unknown_field_is_dropped(conn, laptops):
    intent = {
        "fields": [
            {"id": "ramGb", "importance": "high", "buyer_wants": {"min": 8}},
            {"id": "nonexistentField", "importance": "high", "buyer_wants": {}},
        ],
        "dimensions_enabled": False,
    }

    result, unknown = score_against_intent(FACTS, laptops, intent, score_listing)

    assert unknown == ["nonexistentField"]
    # The unknown field must not silently consume weight and drag the score down.
    assert result.score == 100


def test_resolve_merges_playbook_type_onto_intent(laptops):
    resolved, unknown = playbooks.resolve_scoring_fields(
        laptops, [{"id": "ramGb", "importance": "high", "buyer_wants": {"min": 16}}]
    )

    assert unknown == []
    assert resolved[0]["type"] == "number", "type comes from the playbook, not intent"
    assert resolved[0]["buyer_wants"] == {"min": 16}


def test_playbook_lookup_from_a_search_url():
    found = playbooks.playbook_for_url(
        "https://www.kleinanzeigen.de/s-notebooks/muenchen/preis::450/laptop/k0c278l6411"
    )
    assert found is not None
    assert found["key"] == "electronics/laptops"


def test_playbook_lookup_returns_none_for_unknown_category():
    assert (
        playbooks.playbook_for_url("https://www.kleinanzeigen.de/s-tiere/c130") is None
    )
    assert playbooks.playbook_for_url("") is None


def test_every_playbook_field_is_well_formed():
    """Guards the asset the whole product rests on."""
    valid_types = {"boolean", "number", "enum", "tier", "text"}

    for key, playbook in playbooks.all_playbooks().items():
        seen = set()
        for field in playbook["fields"]:
            fid = field.get("id")
            assert fid, f"{key}: field without id"
            assert fid not in seen, f"{key}: duplicate field id {fid}"
            seen.add(fid)

            ftype = field.get("type")
            assert ftype in valid_types, f"{key}.{fid}: bad type {ftype}"
            assert field.get("label"), f"{key}.{fid}: missing label"
            assert field.get("description"), f"{key}.{fid}: missing description"

            if ftype == "enum":
                assert field.get("options"), f"{key}.{fid}: enum without options"
            if ftype == "tier":
                assert field.get("tier_scale"), f"{key}.{fid}: tier without scale"


def test_cache_stats_report_coverage(conn, laptops):
    model = CountingModel()
    get_or_extract(conn, LISTING, laptops, model)
    get_or_extract(conn, dict(LISTING, id="test-2"), laptops, model)

    assert fact_sheets.stats(conn) == {"sheets": 2, "listings": 2, "playbooks": 1}
