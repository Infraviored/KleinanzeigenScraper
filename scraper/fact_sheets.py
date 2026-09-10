"""Persistence for category fact sheets.

A fact sheet is the canonical set of facts extracted from one listing against one
category playbook. It is keyed by (listing_id, playbook_key) and carries the
playbook version it was produced with, so a playbook change invalidates exactly
the sheets it affects and nothing else.

This table is what makes extraction independent of any buyer: scoring reads a
sheet instead of calling a model, so adding a buyer costs no tokens at all.
"""

import json
import db_schema
import logging

logger = logging.getLogger(__name__)

# The fact_sheets DDL lives in db/schema.sql, applied by db_schema.
# It was declared here too until the two copies began to drift.


def ensure_schema(conn):
    """Bring the connection up to db/schema.sql."""
    db_schema.apply_schema(conn)
    conn.commit()


def source_hash(listing_title, description, details):
    """Fingerprints the listing text a sheet was derived from.

    A seller editing the description must invalidate the sheet; a re-scrape that
    changes nothing must not.
    """
    import hashlib

    payload = "\x1f".join(
        [listing_title or "", description or "", details or ""]
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


def get(conn, listing_id, playbook_key, playbook_version=None, expected_hash=None):
    """Returns the stored facts dict, or None when no usable sheet exists.

    A sheet is unusable when it was produced by an older playbook version or
    from different listing text; in both cases the caller must re-extract.
    """
    row = conn.execute(
        "SELECT facts_json, playbook_version, source_hash FROM fact_sheets "
        "WHERE listing_id = ? AND playbook_key = ?",
        (listing_id, playbook_key),
    ).fetchone()
    if not row:
        return None

    facts_json, version, stored_hash = row[0], row[1], row[2]

    if playbook_version is not None and version != playbook_version:
        logger.info(
            "Fact sheet for %s is stale (playbook v%s, sheet v%s); re-extracting.",
            listing_id,
            playbook_version,
            version,
        )
        return None

    if expected_hash is not None and stored_hash and stored_hash != expected_hash:
        logger.info(
            "Listing text for %s changed since extraction; re-extracting.", listing_id
        )
        return None

    try:
        return json.loads(facts_json)
    except (ValueError, TypeError):
        logger.warning("Corrupt fact sheet for %s; re-extracting.", listing_id)
        return None


def put(conn, listing_id, playbook_key, playbook_version, facts, hash_value=None):
    import datetime

    conn.execute(
        "INSERT INTO fact_sheets "
        "(listing_id, playbook_key, playbook_version, facts_json, source_hash, extracted_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(listing_id, playbook_key) DO UPDATE SET "
        "playbook_version = excluded.playbook_version, "
        "facts_json = excluded.facts_json, "
        "source_hash = excluded.source_hash, "
        "extracted_at = excluded.extracted_at",
        (
            listing_id,
            playbook_key,
            playbook_version,
            json.dumps(facts, ensure_ascii=False),
            hash_value,
            datetime.datetime.now(datetime.timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def stats(conn):
    """Cache effectiveness, for the cost reporting the architecture depends on."""
    row = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT listing_id), COUNT(DISTINCT playbook_key) "
        "FROM fact_sheets"
    ).fetchone()
    return {"sheets": row[0], "listings": row[1], "playbooks": row[2]}
