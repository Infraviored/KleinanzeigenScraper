#!/usr/bin/env node
/**
 * Build a fixture database from the schema in db_setup.js, then seed it with
 * synthetic data for UI screenshots and integration tests.
 *
 * Usage:
 *   node scripts/seed_fixture_db.js <output-path>
 *
 * The schema comes from backend/db_setup.js. The users table is created by
 * server.js on startup, so we add it here as well.
 *
 * NEVER copies production data — everything is synthetic.
 */

const path = require('path');
const fs = require('fs');

const backendModules = path.join(__dirname, '..', 'backend', 'node_modules');
const sqlite3 = require(path.join(backendModules, 'sqlite3')).verbose();
const bcrypt = require(path.join(backendModules, 'bcrypt'));

const outPath = process.argv[2];
if (!outPath) {
  console.error('Usage: node scripts/seed_fixture_db.js <output.db>');
  process.exit(1);
}

// Remove if exists to start clean
if (fs.existsSync(outPath)) fs.unlinkSync(outPath);

const db = new sqlite3.Database(outPath);

const EMAIL = 'ui-shots@localhost';
const PASSWORD = 'ui-shots-only';

function run(sql, params = []) {
  return new Promise((resolve, reject) => {
    db.run(sql, params, function (err) {
      if (err) reject(err);
      else resolve(this);
    });
  });
}

async function main() {
  // ── Schema ─────────────────────────────────────────────────────────
  await run('PRAGMA foreign_keys = ON');

  await run(`CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL
  )`);

  await run(`CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE
  )`);

  await run(`CREATE TABLE IF NOT EXISTS knowledge_sets (
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
  )`);

  await run(`CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER REFERENCES campaigns(id) ON DELETE CASCADE,
    name TEXT,
    url TEXT UNIQUE,
    enabled INTEGER DEFAULT 1,
    knowledge_set_id INTEGER REFERENCES knowledge_sets(id) ON DELETE SET NULL
  )`);

  await run(`CREATE TABLE IF NOT EXISTS listings (
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
  )`);

  await run(`CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    listing_id TEXT REFERENCES listings(id) ON DELETE CASCADE,
    sender_name TEXT,
    sender_initials TEXT,
    is_outbound INTEGER,
    message_text TEXT,
    message_date TEXT
  )`);

  // ── Seed user ──────────────────────────────────────────────────────
  const hash = await bcrypt.hash(PASSWORD, 10);
  await run(
    "INSERT INTO users (email, password_hash, role) VALUES (?, ?, 'admin')",
    [EMAIL, hash]
  );

  // ── Seed campaign + search targets ─────────────────────────────────
  await run("INSERT INTO campaigns (id, name) VALUES (1, 'Laptop Hunt')");

  await run(
    "INSERT INTO searches (id, campaign_id, name, url, enabled) VALUES (1, 1, 'ThinkPad T14s', 'https://www.kleinanzeigen.de/s-thinkpad-t14s/k0', 1)"
  );
  await run(
    "INSERT INTO searches (id, campaign_id, name, url, enabled) VALUES (2, 1, 'ThinkPad X1 Carbon', 'https://www.kleinanzeigen.de/s-x1-carbon/k0', 1)"
  );

  // ── Seed listings ──────────────────────────────────────────────────
  const now = new Date().toISOString();
  const listings = [
    {
      id: 'fixture-001',
      title: 'ThinkPad T14s Gen 3, 16GB, 512GB SSD',
      price: '€ 650',
      location: '86899 Landsberg am Lech',
      niceness_score: 82,
      status: 'New',
      search_id: 1,
    },
    {
      id: 'fixture-002',
      title: 'Lenovo ThinkPad T14s AMD Ryzen 7 PRO, top Zustand',
      price: '€ 520',
      location: '80331 München',
      niceness_score: 74,
      status: 'New',
      search_id: 1,
    },
    {
      id: 'fixture-003',
      title: 'X1 Carbon Gen 11, i7, 32GB, WQUXGA',
      price: '€ 980',
      location: '10115 Berlin',
      niceness_score: 91,
      status: 'New',
      search_id: 2,
    },
    {
      id: 'fixture-004',
      title: 'ThinkPad X1 Carbon Gen 9, 16GB, FHD+',
      price: '€ 430',
      location: '50667 Köln',
      niceness_score: 65,
      status: 'Evaluate with AI',
      search_id: 2,
    },
  ];

  for (const l of listings) {
    await run(
      `INSERT INTO listings (id, title, price, location, niceness_score, status, search_id,
        url, short_description, llm_processed, last_description_changed_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)`,
      [
        l.id,
        l.title,
        l.price,
        l.location,
        l.niceness_score,
        l.status,
        l.search_id,
        `https://www.kleinanzeigen.de/s-anzeige/${l.id}`,
        `Synthetic fixture listing for CI screenshots.`,
        now,
      ]
    );
  }

  db.close();
  console.log(`Fixture database seeded: ${outPath}`);
  console.log(`  User: ${EMAIL} / ${PASSWORD}`);
  console.log(`  Campaigns: 1, Searches: 2, Listings: ${listings.length}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
