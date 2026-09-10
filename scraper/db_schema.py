"""Applies db/schema.sql to a database.

Deliberately holds no schema of its own. It reads the same file the Node side
reads, because two declarations of one table drift: route_searches was declared
in both runtimes, and the campaign dashboard returned 500 on every fresh install
because Node queried a table only this side knew how to create.

Idempotent: every statement in the file is IF NOT EXISTS, so this can run on
every connection and costs nothing on a database that is already correct.
"""

import os
import sqlite3

SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "schema.sql"
)

# Applying the schema per connection is cheap but not free, and some callers
# open a connection per listing. One pass per database file per process is
# enough: the file cannot become un-applied while we hold it.
_APPLIED = set()


def apply_schema(connection, force=False):
    """Bring `connection`'s database up to db/schema.sql.

    Also switches foreign keys on, which SQLite requires per connection and
    which is therefore forgotten roughly every time. A cascade that has never
    cascaded is worse than no cascade, because the code reads as if it works.
    """
    connection.execute("PRAGMA foreign_keys = ON")

    key = _database_key(connection)
    if not force and key is not None and key in _APPLIED:
        return

    with open(SCHEMA_PATH, encoding="utf-8") as handle:
        script = handle.read()

    # Statement at a time rather than executescript, because SQLite has no
    # ADD COLUMN IF NOT EXISTS and executescript would abandon the rest of the
    # file at the first column that already exists -- which is every startup
    # after the first.
    for statement in _statements(script):
        try:
            connection.execute(statement)
        except sqlite3.OperationalError as error:
            if "duplicate column name" not in str(error).lower():
                raise RuntimeError(
                    f"Applying db/schema.sql failed on:\n{statement}\n\n{error}"
                ) from error
    connection.commit()

    if key is not None:
        _APPLIED.add(key)


def _statements(script):
    """Split the schema file into statements.

    Naive on purpose: this is plain DDL with no triggers, so no statement body
    contains a semicolon. If that ever changes, it breaks here and loudly.
    """
    for chunk in script.split(";"):
        statement = "\n".join(
            line for line in chunk.splitlines() if not line.strip().startswith("--")
        ).strip()
        if statement:
            yield statement


def _database_key(connection):
    """The file this connection is attached to, or None for in-memory."""
    try:
        for _, name, path in connection.execute("PRAGMA database_list"):
            if name == "main":
                return path or None
    except sqlite3.Error:
        return None
    return None


def connect(path, **kwargs):
    """Open a database that is guaranteed to match the schema."""
    connection = sqlite3.connect(path, **kwargs)
    apply_schema(connection)
    return connection


def reset_cache():
    """Forget which databases have been brought up to date. For tests."""
    _APPLIED.clear()
