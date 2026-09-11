#!/usr/bin/env node
/**
 * Brings a database up to db/schema.sql.
 *
 * This script used to begin by deleting the database:
 *
 *     // Delete existing database file to ensure a clean schema transition
 *     if (fs.existsSync(dbPath)) fs.unlinkSync(dbPath);
 *
 * and it hardcoded data/scraper.db while the server honoured PRISMDEALS_DB. So
 * `PRISMDEALS_DB=/tmp/test.db node backend/db_setup.js`, which reads as
 * obviously safe, destroyed production instead. On 2026-09-10 it did, and the
 * data came back only because a running process still held the deleted file
 * open. That is luck, not recovery.
 *
 * Now: it honours PRISMDEALS_DB, it only ever adds, and destroying a database
 * takes an explicit flag, a confirmation, and a backup taken first.
 *
 *   node backend/db_setup.js                     # bring up to date, keep data
 *   PRISMDEALS_DB=/tmp/x.db node backend/db_setup.js
 *   node backend/db_setup.js --recreate --yes    # start empty, backup first
 */

const fs = require('fs');
const path = require('path');
const sqlite3 = require('sqlite3').verbose();
const { applySchema } = require('./db/schema');
const { backup } = require('./db/backup');

const { defaultPath } = require('./db/path');

function parseArgs(argv) {
  return {
    recreate: argv.includes('--recreate'),
    confirmed: argv.includes('--yes'),
  };
}

async function main(argv) {
  const { recreate, confirmed } = parseArgs(argv);
  const dbPath = defaultPath();

  fs.mkdirSync(path.dirname(dbPath), { recursive: true });

  if (recreate) {
    if (!confirmed) {
      console.error(
        `Refusing to delete ${dbPath}.\n\n` +
          `--recreate destroys every row in the database. If that is genuinely\n` +
          `what you want, say so explicitly:\n\n` +
          `    node backend/db_setup.js --recreate --yes\n\n` +
          `To add missing tables while keeping the data, run it with no flags.`
      );
      process.exitCode = 1;
      return;
    }
    if (fs.existsSync(dbPath)) {
      const saved = backup(dbPath, 'before-recreate');
      console.log(`Backed up to ${saved}`);
      for (const suffix of ['', '-wal', '-shm']) {
        fs.rmSync(`${dbPath}${suffix}`, { force: true });
      }
      console.log(`Deleted ${dbPath}`);
    }
  }

  const existed = fs.existsSync(dbPath);
  const db = new sqlite3.Database(dbPath);
  try {
    await applySchema(db);
  } finally {
    await new Promise(resolve => db.close(resolve));
  }
  console.log(
    `${existed ? 'Updated' : 'Created'} ${dbPath} from db/schema.sql`
  );
}

if (require.main === module) {
  main(process.argv.slice(2)).catch(err => {
    console.error(err.message);
    process.exit(1);
  });
}

module.exports = { main };
