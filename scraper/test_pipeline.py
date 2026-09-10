import json
import sqlite3

import pytest

import dossiers
import fact_sheets
import pipeline

FACTS = {
    "criteria": {
        "brand": {"value": "Apple"},
        "modelName": {"value": 'MacBook Pro 15" 2019'},
        "ramGb": {"value": 16},
        "cpuTier": {"value": 4},
        "hasFunctionalDefect": {"value": "no"},
    },
    "dimensions": {},
}

INTENT = {
    "fields": [
        {"id": "ramGb", "importance": "high", "buyer_wants": {"min": 8}},
        {
            "id": "hasFunctionalDefect",
            "importance": "high",
            "buyer_wants": {"match": False},
            "polarity": "negative",
        },
    ],
    "dimensions_enabled": False,
}

LAPTOP_SEARCH = "https://www.kleinanzeigen.de/s-notebooks/muenchen/laptop/k0c278l6411"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(
        """
        CREATE TABLE listings (id TEXT PRIMARY KEY, title TEXT, detailed_description TEXT,
            details TEXT, search_id INTEGER, extracted_facts TEXT, niceness_score INTEGER,
            llm_processed INTEGER DEFAULT 0, last_ai_evaluated_at TEXT);
        CREATE TABLE searches (id INTEGER PRIMARY KEY, url TEXT, enabled INTEGER,
            knowledge_set_id INTEGER);
        CREATE TABLE knowledge_sets (id INTEGER PRIMARY KEY, item_json TEXT,
            expert_knowledge TEXT);
        """
    )
    fact_sheets.ensure_schema(c)
    dossiers.ensure_schema(c)
    yield c
    c.close()


def seed(conn, search_url=LAPTOP_SEARCH, intent=INTENT, listing_ids=("l1",)):
    conn.execute(
        "INSERT INTO knowledge_sets (id, item_json, expert_knowledge) VALUES (1, ?, '')",
        (json.dumps(intent) if intent is not None else None,),
    )
    conn.execute(
        "INSERT INTO searches (id, url, enabled, knowledge_set_id) VALUES (1, ?, 1, 1)",
        (search_url,),
    )
    for lid in listing_ids:
        conn.execute(
            "INSERT INTO listings (id, title, detailed_description, details, search_id) "
            "VALUES (?, ?, ?, ?, 1)",
            (lid, "MacBook Pro 15 2019", "16GB RAM, i7, top", "Zustand: Gut"),
        )
    conn.commit()


class CountingModel:
    def __init__(self, facts=None):
        self.calls = 0
        self.facts = facts if facts is not None else FACTS

    def __call__(self, prompt, fields=None):
        self.calls += 1
        return self.facts


def test_a_listing_is_extracted_scored_and_persisted(conn):
    seed(conn)
    model = CountingModel()

    outcomes = pipeline.run(conn, model)

    assert len(outcomes) == 1
    assert outcomes[0].score == 100
    assert model.calls == 1

    row = conn.execute(
        "SELECT extracted_facts, niceness_score, llm_processed FROM listings WHERE id='l1'"
    ).fetchone()
    assert json.loads(row[0])["criteria"]["ramGb"]["value"] == 16
    assert row[1] == 100
    assert row[2] == 1


def test_a_second_run_costs_no_model_call(conn):
    """The decoupling, asserted through the production entry point."""
    seed(conn)
    model = CountingModel()

    pipeline.run(conn, model)
    outcomes = pipeline.run(conn, model)

    assert model.calls == 1
    assert outcomes[0].from_cache is True
    assert pipeline.summarise(outcomes)["model_calls"] == 0


def test_categories_without_a_playbook_fall_through_untouched(conn):
    seed(conn, search_url="https://www.kleinanzeigen.de/s-tiere/c130")
    model = CountingModel()

    outcomes = pipeline.run(conn, model)

    assert model.calls == 0
    assert outcomes[0].skipped == "no playbook for category"
    assert conn.execute("SELECT llm_processed FROM listings").fetchone()[0] == 0


def test_identity_is_resolved_from_the_extracted_facts(conn):
    seed(conn)
    outcomes = pipeline.run(conn, CountingModel())

    assert outcomes[0].identity_key == "apple/macbook-pro-15-2019"


def test_an_unconfigured_knowledge_set_is_left_to_the_legacy_worker(conn):
    """Transitional: avoids paying twice while the legacy path still runs."""
    seed(conn, intent={})
    model = CountingModel()

    outcomes = pipeline.run(conn, model)

    assert model.calls == 0
    assert outcomes[0].skipped == "knowledge set defines no fields"


def test_extraction_can_be_precomputed_without_an_intent(conn):
    """Extraction is buyer-independent; require_intent=False is the end state."""
    seed(conn, intent={})
    model = CountingModel()

    outcomes = pipeline.run(conn, model, require_intent=False)

    assert model.calls == 1
    assert outcomes[0].score is None
    assert fact_sheets.stats(conn)["sheets"] == 1


def test_a_broken_knowledge_set_does_not_abort_the_run(conn):
    conn.execute("INSERT INTO knowledge_sets (id, item_json) VALUES (1, '{not json')")
    conn.execute(
        "INSERT INTO searches (id, url, enabled, knowledge_set_id) VALUES (1, ?, 1, 1)",
        (LAPTOP_SEARCH,),
    )
    conn.execute(
        "INSERT INTO listings (id, title, detailed_description, details, search_id) "
        "VALUES ('l1', 't', 'd', '', 1)"
    )
    conn.commit()

    outcomes = pipeline.run(conn, CountingModel(), require_intent=False)
    assert outcomes[0].skipped is None
    assert outcomes[0].score is None


def test_one_failing_listing_does_not_stop_the_others(conn):
    seed(conn, listing_ids=("l1", "l2"))

    class Flaky(CountingModel):
        def __call__(self, prompt, fields=None):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("provider blew up")
            return FACTS

    outcomes = pipeline.run(conn, Flaky())
    skipped = [o for o in outcomes if o.skipped]
    scored = [o for o in outcomes if o.score is not None]

    assert len(skipped) == 1 and "provider blew up" in skipped[0].skipped
    assert len(scored) == 1


def test_dossier_check_fields_extend_the_extraction_set():
    playbook = {
        "key": "vehicles/cars",
        "version": 1,
        "fields": [
            {"id": "make", "type": "text", "label": "Marke", "description": "d"}
        ],
    }
    payload = {
        "check_fields": [
            {
                "id": "timingChainReplaced",
                "type": "boolean",
                "label": "SK",
                "description": "d",
            }
        ]
    }

    fields = pipeline.effective_fields(playbook, payload)
    assert [f["id"] for f in fields] == ["make", "timingChainReplaced"]


def test_playbook_fields_win_over_a_dossier_on_an_id_collision():
    """A reviewed category definition outranks a generated one."""
    playbook = {
        "key": "vehicles/cars",
        "version": 1,
        "fields": [
            {"id": "make", "type": "text", "label": "Marke", "description": "canonical"}
        ],
    }
    payload = {
        "check_fields": [
            {
                "id": "make",
                "type": "enum",
                "label": "Marke",
                "description": "researched",
            }
        ]
    }

    fields = pipeline.effective_fields(playbook, payload)
    assert len(fields) == 1
    assert fields[0]["description"] == "canonical"


def test_summarise_reports_cache_effectiveness(conn):
    seed(conn, listing_ids=("l1", "l2"))
    model = CountingModel()

    pipeline.run(conn, model)
    second = pipeline.summarise(pipeline.run(conn, model))

    assert second["processed"] == 2
    assert second["from_cache"] == 2
    assert second["model_calls"] == 0
    assert second["identities_resolved"] == 2
