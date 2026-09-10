/**
 * Copies a database aside before anything destructive touches it.
 *
 * Uses SQLite's own VACUUM INTO where it can, which produces a consistent
 * snapshot even while another process is writing. A plain file copy of a live
 * SQLite database can catch it mid-transaction; the WAL is a separate file and
 * copying one without the other yields a database missing its most recent
 * commits. VACUUM INTO has no such problem.
 */

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

/**
 * @param {string} dbPath  database to copy
 * @param {string} reason  short slug that lands in the filename
 * @returns {string} path of the backup
 */
function backup(dbPath, reason = 'backup') {
  const stamp = new Date()
    .toISOString()
    .replace(/[-:]/g, '')
    .replace(/\..+$/, '')
    .replace('T', '-');
  const target = path.join(
    path.dirname(dbPath),
    `${path.basename(dbPath)}.${reason}-${stamp}`
  );

  try {
    // Consistent even against a database being written to right now.
    execFileSync('sqlite3', [dbPath, `VACUUM INTO '${target}'`], {
      stdio: 'pipe',
    });
  } catch {
    // No sqlite3 binary, or a database too damaged to vacuum. A plain copy is
    // worth more than no backup at all — say so rather than pretending.
    fs.copyFileSync(dbPath, target);
    for (const suffix of ['-wal', '-shm']) {
      if (fs.existsSync(`${dbPath}${suffix}`)) {
        fs.copyFileSync(`${dbPath}${suffix}`, `${target}${suffix}`);
      }
    }
    console.warn(
      `sqlite3 was unavailable, so ${target} is a plain file copy including ` +
        `its WAL. Verify it before relying on it.`
    );
  }

  return target;
}

module.exports = { backup };
