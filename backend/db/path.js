/**
 * Which database this process should open.
 *
 * One expression of the rule, for the same reason `scraper/db_schema.py` has
 * one: the two runtimes must agree on which file they mean, and a rule written
 * out in several places is one that drifts. It has drifted twice already —
 * `db_setup.js` ignored `PRISMDEALS_DB` and deleted production while pointed at
 * a temporary file, and `scraper/main.py` ignored it while the backend obeyed
 * it, so a corridor "replanned against a copy" was replanned against
 * production.
 */

const path = require('path');

function defaultPath() {
  return (
    process.env.PRISMDEALS_DB ||
    path.join(__dirname, '..', '..', 'data', 'scraper.db')
  );
}

module.exports = { defaultPath };
