-- The database schema. All of it, in one place.
--
-- Before this file the schema lived in five: backend/db_setup.js created five
-- tables, backend/server.js created four more at startup, and
-- scraper/route_store.py, scraper/fact_sheets.py and scraper/dossiers.py each
-- created their own on first use. Nothing owned it, so whichever process ran
-- first decided what existed -- and on 2026-09-10 that produced a campaign
-- dashboard returning 500 on every fresh install, because Node queried a table
-- only Python knew how to create.
--
-- Two definitions of the same table are worse than one in the wrong place:
-- route_searches was declared in both Node and Python and had already begun to
-- drift. So: one file, plain SQL, no runtime.
--
-- Rules for changing it:
--   * Every statement is IF NOT EXISTS, so applying this to a live database is
--     a no-op. It runs on every connection, from both runtimes.
--   * Only ever add. SQLite cannot drop a column or add a foreign key to an
--     existing table, and these databases are live.
--   * A new column goes in ALTER TABLE ADD COLUMN below, not into the CREATE
--     TABLE above -- existing databases never re-run the CREATE.
--
-- Applied by backend/db/schema.js and scraper/db_schema.py, which read this
-- exact file rather than restating it.

PRAGMA foreign_keys = ON;


CREATE TABLE IF NOT EXISTS campaigns (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT UNIQUE
    );

CREATE TABLE IF NOT EXISTS dossiers (
    identity_key    TEXT PRIMARY KEY,
    category_key    TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    payload_json    TEXT NOT NULL,
    researched_at   TEXT NOT NULL,
    approved        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS fact_sheets (
    listing_id      TEXT NOT NULL,
    playbook_key    TEXT NOT NULL,
    playbook_version INTEGER NOT NULL,
    facts_json      TEXT NOT NULL,
    source_hash     TEXT,
    extracted_at    TEXT NOT NULL,
    PRIMARY KEY (listing_id, playbook_key)
);

CREATE TABLE IF NOT EXISTS knowledge_sets (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT UNIQUE NOT NULL,
      expert_knowledge TEXT,
      item_json TEXT,
      market_memo TEXT,
      good_reference_description TEXT,
      bad_reference_description TEXT,
      market_samples_json TEXT,
      source_search_url TEXT,
      sample_timestamp TEXT
    );

CREATE TABLE IF NOT EXISTS listing_route_geo (
    listing_id      TEXT NOT NULL,
    route_search_id INTEGER NOT NULL,
    lat             REAL,
    lon             REAL,
    offroute_km     REAL,
    detour_min      REAL,
    computed_at     TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'routed',
    PRIMARY KEY (listing_id, route_search_id)
);

CREATE TABLE IF NOT EXISTS listings (
      id TEXT PRIMARY KEY,
      title TEXT,
      price TEXT,
      location TEXT,
      url TEXT,
      short_description TEXT,
      detailed_description TEXT,
      llm_processed INTEGER DEFAULT 0,
      llm_processed_time TEXT,
      full_info_obtained INTEGER DEFAULT 0,
      extracted_facts TEXT,
      niceness_score INTEGER,
      status TEXT DEFAULT 'New',
      search_id INTEGER REFERENCES searches(id) ON DELETE CASCADE,
      details TEXT,
      images TEXT,
      last_description_changed_at TEXT,
      last_ai_evaluated_at TEXT
    );

CREATE TABLE IF NOT EXISTS messages (
      id TEXT PRIMARY KEY,
      listing_id TEXT REFERENCES listings(id) ON DELETE CASCADE,
      sender_name TEXT,
      sender_initials TEXT,
      is_outbound INTEGER,
      message_text TEXT,
      message_date TEXT
    );

CREATE TABLE IF NOT EXISTS route_search_circles (
    route_search_id INTEGER NOT NULL,
    search_id       INTEGER NOT NULL,
    location_id     TEXT,
    label           TEXT,
    radius_km       REAL,
    PRIMARY KEY (route_search_id, search_id)
);

CREATE TABLE IF NOT EXISTS route_searches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT,
    campaign_id     INTEGER,
    knowledge_set_id INTEGER,
    base_url        TEXT NOT NULL,
    origin          TEXT NOT NULL,
    destination     TEXT NOT NULL,
    radius_km       REAL NOT NULL,
    half_width_km   REAL NOT NULL,
    plan_json       TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS searches (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      campaign_id INTEGER REFERENCES campaigns(id) ON DELETE CASCADE,
      name TEXT,
      url TEXT UNIQUE,
      enabled INTEGER DEFAULT 1,
      knowledge_set_id INTEGER REFERENCES knowledge_sets(id) ON DELETE SET NULL
    );

CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      role TEXT NOT NULL
    );

-- Columns added after the tables above already existed in the wild.
--
-- These must be ALTER, not part of the CREATE: a live database never re-runs a
-- CREATE TABLE IF NOT EXISTS, so a column added to the definition above would
-- appear on fresh installs and be missing everywhere else -- the exact split
-- this file exists to prevent.
--
-- SQLite has no ADD COLUMN IF NOT EXISTS. The appliers on both sides treat
-- "duplicate column name" as success, which is what it means here.

ALTER TABLE listings ADD COLUMN last_description_changed_at TEXT;

ALTER TABLE listings ADD COLUMN last_ai_evaluated_at TEXT;
