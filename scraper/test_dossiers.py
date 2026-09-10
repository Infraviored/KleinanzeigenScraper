import datetime
import sqlite3

import pytest

import dossiers

SOURCED_CLAIM = {
    "kind": "construction_defect",
    "statement": "Steuerkette rueckseitig verbaut, Kettenriss moeglich",
    "detail": "typisch 80.000-120.000 km, betroffen bis Produktion 09/2013",
    "sources": ["https://www.motor-talk.de/forum/n47-steuerkette-t3470450.html"],
}

PAYLOAD = {
    "summary": "Der N47 entscheidet sich an der Steuerkette.",
    "claims": [SOURCED_CLAIM],
    "check_fields": [
        {
            "id": "timingChainReplaced",
            "type": "boolean",
            "label": "Steuerkette erneuert",
            "description": "yes if timing chain replacement is claimed",
            "rationale": "construction_defect",
        }
    ],
}


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    dossiers.ensure_schema(connection)
    yield connection
    connection.close()


def test_identity_key_is_stable_and_normalised():
    assert (
        dossiers.identity_key("BMW", "3er", "E90", "320d", "N47")
        == "bmw/3er/e90/320d/n47"
    )
    # Unresolved parts must not create a bogus key segment.
    assert dossiers.identity_key("BMW", "", None, "unknown", "320d") == "bmw/320d"
    assert (
        dossiers.identity_key("Mercedes Benz", "C-Klasse") == "mercedes-benz/c-klasse"
    )


def test_unsourced_claims_are_dropped_not_softened():
    payload = {
        "claims": [
            SOURCED_CLAIM,
            {
                "kind": "typical_failure",
                "statement": "Getriebe geht kaputt",
                "sources": [],
            },
        ]
    }
    cleaned, dropped = dossiers.sanitize(payload)

    assert len(cleaned["claims"]) == 1
    assert len(dropped) == 1
    assert "no sources" in dropped[0]["reason"]


def test_claims_with_unrecognised_kind_are_dropped():
    payload = {"claims": [dict(SOURCED_CLAIM, kind="vibes")]}
    cleaned, dropped = dossiers.sanitize(payload)

    assert cleaned["claims"] == []
    assert "not recognised" in dropped[0]["reason"]


def test_claim_without_statement_is_dropped():
    payload = {"claims": [dict(SOURCED_CLAIM, statement="")]}
    cleaned, dropped = dossiers.sanitize(payload)
    assert cleaned["claims"] == []
    assert "no statement" in dropped[0]["reason"]


def test_storing_a_dossier_sanitises_it(conn):
    payload = {
        "claims": [SOURCED_CLAIM, {"kind": "recall", "statement": "x", "sources": []}]
    }
    cleaned, dropped = dossiers.put(conn, "bmw/320d/n47", "vehicles/cars", payload)

    assert len(dropped) == 1
    stored = dossiers.get(conn, "bmw/320d/n47")
    assert len(stored["payload"]["claims"]) == 1


def test_defects_stay_fresh_far_longer_than_prices():
    """The reason claims carry separate clocks."""
    long_ago = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    ).isoformat()

    defect = {"kind": "construction_defect", "statement": "s", "sources": ["x"]}
    price = {"kind": "price_band", "statement": "s", "sources": ["x"]}

    assert dossiers.claim_is_fresh(defect, long_ago) is True
    assert dossiers.claim_is_fresh(price, long_ago) is False


def test_fresh_claims_filters_by_kind():
    long_ago = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=60)
    ).isoformat()
    payload = {
        "claims": [
            {"kind": "construction_defect", "statement": "a", "sources": ["x"]},
            {"kind": "price_band", "statement": "b", "sources": ["x"]},
        ]
    }
    fresh = dossiers.fresh_claims(payload, long_ago)

    assert [c["kind"] for c in fresh] == ["construction_defect"]


def test_unapproved_dossier_is_hidden_when_approval_required(conn):
    dossiers.put(conn, "k", "vehicles/cars", PAYLOAD, approved=False)

    assert dossiers.get(conn, "k") is not None
    assert dossiers.get(conn, "k", require_approved=True) is None

    dossiers.put(conn, "k", "vehicles/cars", PAYLOAD, approved=True)
    assert dossiers.get(conn, "k", require_approved=True) is not None


def test_check_fields_are_shaped_like_playbook_fields(conn):
    """So they can be concatenated onto a category field set without special casing."""
    fields = dossiers.check_fields(PAYLOAD)

    assert fields[0]["id"] == "timingChainReplaced"
    assert fields[0]["type"] == "boolean"
    assert fields[0]["label"] and fields[0]["description"]


def test_research_runs_once_then_serves_from_cache(conn):
    calls = {"n": 0}

    def research(prompt):
        calls["n"] += 1
        assert "N47" in prompt
        return PAYLOAD

    first, cached = dossiers.get_or_research(
        conn, "bmw/320d/n47", "BMW 320d E90 N47", "vehicles/cars", "Autos", research
    )
    assert cached is False and calls["n"] == 1

    second, cached = dossiers.get_or_research(
        conn, "bmw/320d/n47", "BMW 320d E90 N47", "vehicles/cars", "Autos", research
    )
    assert cached is True
    assert calls["n"] == 1, "a cached dossier must not trigger research again"
    assert second["summary"] == first["summary"]


def test_research_prompt_forbids_unsourced_claims():
    prompt = dossiers.build_research_prompt("BMW 320d E90 N47", "Autos")

    assert "omit the claim entirely" in prompt
    assert "https://" in prompt
    assert "START_JSON" in prompt and "END_JSON" in prompt
    assert "check_fields" in prompt


# Verbatim output from deepseek-v4-flash asked to research the N47 without any
# retrieval tool. The statements are substantively correct; the sources are
# citation-shaped inventions. This is the exact failure the validator exists for.
CONFABULATED = [
    {
        "kind": "construction_defect",
        "statement": "The N47 timing chain is prone to stretching and failure",
        "sources": [
            "Honest John - BMW N47 timing chain problems",
            "E90Post forum - N47 timing chain failure thread",
        ],
    },
    {
        "kind": "recall",
        "statement": "BMW issued a technical service bulletin for N47 timing chains",
        "sources": [
            "Auto Express - BMW N47 timing chain issue",
            "BMW Service Bulletin #11 01 12",
        ],
    },
]


def test_citation_shaped_strings_without_urls_are_rejected():
    cleaned, dropped = dossiers.sanitize({"claims": CONFABULATED})

    assert cleaned["claims"] == [], "named publications are not retrievable sources"
    assert len(dropped) == 2
    assert all("retrievable source URL" in d["reason"] for d in dropped)


def test_a_url_anywhere_in_the_source_string_counts():
    claim = dict(
        SOURCED_CLAIM,
        sources=["Motor-Talk Forum, https://www.motor-talk.de/forum/n47-t3470450.html"],
    )
    ok, reason = dossiers.validate_claim(claim)

    assert ok, reason
    assert dossiers.source_urls(claim) == [
        "https://www.motor-talk.de/forum/n47-t3470450.html"
    ]


def test_mixed_sources_keep_the_claim_if_one_url_is_present():
    claim = dict(
        SOURCED_CLAIM, sources=["BMW Bulletin #11 01 12", "https://example.org/n47"]
    )
    ok, _ = dossiers.validate_claim(claim)
    assert ok


def test_failed_research_returns_nothing_rather_than_an_empty_dossier(conn):
    payload, cached = dossiers.get_or_research(
        conn, "k", "identity", "vehicles/cars", "Autos", lambda prompt: None
    )
    assert payload is None and cached is False
    assert dossiers.get(conn, "k") is None


# --- source verification -------------------------------------------------

LIVE = "https://www.motor-talk.de/forum/n47-steuerkette-t3470450.html"
DEAD = "https://www.motor-talk.de/forum/erfunden-t9999999.html"


def claim_with(*urls, kind="construction_defect"):
    return {"kind": kind, "statement": "s", "sources": list(urls)}


def test_a_claim_whose_urls_all_404_is_removed():
    """A well-formed but invented URL passes every syntactic check."""
    payload = {"claims": [claim_with(DEAD)]}
    cleaned, removed = dossiers.verify_sources(payload, lambda url: url == LIVE)

    assert cleaned["claims"] == []
    assert removed[0]["reason"] == "no source URL resolves"


def test_one_live_source_is_enough_to_keep_a_claim():
    payload = {"claims": [claim_with(DEAD, LIVE)]}
    cleaned, removed = dossiers.verify_sources(payload, lambda url: url == LIVE)

    assert len(cleaned["claims"]) == 1
    assert removed == []


def test_an_unreachable_network_does_not_strip_a_dossier():
    """Verification must remove inventions, not punish a flaky connection."""
    payload = {"claims": [claim_with(LIVE)]}
    cleaned, removed = dossiers.verify_sources(payload, lambda url: None)

    assert len(cleaned["claims"]) == 1
    assert removed == []
    assert cleaned["claims"][0]["sources_unverified"] is True


def test_a_partially_checkable_claim_is_kept_and_marked():
    payload = {"claims": [claim_with(DEAD, LIVE)]}
    checks = {DEAD: False, LIVE: None}
    cleaned, _ = dossiers.verify_sources(payload, lambda url: checks[url])

    assert len(cleaned["claims"]) == 1
    assert cleaned["claims"][0]["sources_unverified"] is True


def test_verification_leaves_the_rest_of_the_payload_alone():
    payload = {
        "summary": "s",
        "check_fields": [{"id": "x"}],
        "claims": [claim_with(LIVE)],
    }
    cleaned, _ = dossiers.verify_sources(payload, lambda url: True)

    assert cleaned["summary"] == "s"
    assert cleaned["check_fields"] == [{"id": "x"}]


def test_verification_composes_with_sanitisation():
    """Unsourced claims go first, then the surviving URLs are checked."""
    payload = {
        "claims": [
            claim_with(LIVE),
            claim_with(DEAD),
            {"kind": "recall", "statement": "no sources at all", "sources": []},
        ]
    }
    sanitised, dropped = dossiers.sanitize(payload)
    verified, removed = dossiers.verify_sources(sanitised, lambda url: url == LIVE)

    assert len(dropped) == 1
    assert len(removed) == 1
    assert len(verified["claims"]) == 1


def test_only_a_definitive_404_counts_as_dead():
    """403 from bot protection must not be read as a dead source."""
    assert dossiers.classify_status(200) is True
    assert dossiers.classify_status(301) is True
    assert dossiers.classify_status(404) is False
    assert dossiers.classify_status(410) is False
    # Blocked, rate-limited or broken: unknown, not gone.
    assert dossiers.classify_status(403) is None
    assert dossiers.classify_status(429) is None
    assert dossiers.classify_status(500) is None
