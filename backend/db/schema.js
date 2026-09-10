/**
 * Applies db/schema.sql to a database.
 *
 * The point is that this file contains no schema. It reads the same SQL the
 * Python side reads, so the two runtimes cannot drift apart — which they had,
 * with route_searches declared in both and a dashboard that returned 500 on
 * every fresh install because Node queried a table only Python created.
 *
 * Idempotent by construction: every statement in the file is IF NOT EXISTS or
 * an ALTER guarded below, so this runs on every startup and costs nothing on a
 * database that is already correct.
 */

const fs = require('fs');
const path = require('path');

const SCHEMA_PATH = path.join(__dirname, '..', '..', 'db', 'schema.sql');

/**
 * Splits the file into statements. Naive on purpose: the schema is plain DDL
 * with no triggers, so there are no semicolons inside statement bodies. If that
 * ever changes, this is the thing that breaks, loudly, on the next startup.
 */
function statements(sql) {
  return sql
    .split(/;\s*$/m)
    .map(s => s.replace(/^\s*--.*$/gm, '').trim())
    .filter(Boolean);
}

/**
 * @param {import('sqlite3').Database} db
 * @returns {Promise<void>} resolves once every statement has been applied.
 */
function applySchema(db) {
  const sql = fs.readFileSync(SCHEMA_PATH, 'utf8');
  const list = statements(sql);

  return new Promise((resolve, reject) => {
    db.serialize(() => {
      let remaining = list.length;
      if (remaining === 0) return resolve();

      for (const statement of list) {
        db.run(statement, err => {
          // "duplicate column name" is what ALTER TABLE ADD COLUMN says on a
          // database that already has the column. That is the expected answer
          // on every startup after the first, not a problem.
          if (err && !/duplicate column name/i.test(err.message)) {
            return reject(
              new Error(
                `Applying db/schema.sql failed on:\n${statement}\n\n${err.message}`
              )
            );
          }
          if (--remaining === 0) resolve();
        });
      }
    });
  });
}

module.exports = { applySchema, SCHEMA_PATH };
