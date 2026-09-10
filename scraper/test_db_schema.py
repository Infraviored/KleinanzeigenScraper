"""The schema is one file, and these tests are what keeps it that way.

Every failure here corresponds to something that actually happened: a table
declared in two runtimes that drifted, a dashboard returning 500 because Node
queried a table only Python created, and a setup script that deleted the
production database while being pointed at a temporary one.
"""

import os
import re
import sqlite3
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db_schema  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def fresh_db():
    path = os.path.join(tempfile.mkdtemp(), "test.db")
    db_schema.reset_cache()
    yield path
    db_schema.reset_cache()


def tables(connection):
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def test_schema_creates_every_table_the_application_uses(fresh_db):
    """A fresh database has to be complete before anyone queries it.

    The campaign dashboard returned 500 on every fresh install because
    route_searches was created lazily by whichever process happened to want it
    first, and the dashboard was not that process.
    """
    connection = db_schema.connect(fresh_db)
    expected = {
        "campaigns",
        "searches",
        "listings",
        "messages",
        "knowledge_sets",
        "users",
        "route_searches",
        "route_search_circles",
        "listing_route_geo",
        "fact_sheets",
        "dossiers",
    }
    assert expected <= tables(connection)


def test_applying_the_schema_twice_changes_nothing(fresh_db):
    """It runs on every connection, so it has to be free the second time."""
    connection = db_schema.connect(fresh_db)
    connection.execute("INSERT INTO campaigns (name) VALUES ('keep me')")
    connection.commit()

    before = tables(connection)
    db_schema.apply_schema(connection, force=True)
    db_schema.apply_schema(connection, force=True)

    assert tables(connection) == before
    assert connection.execute("SELECT name FROM campaigns").fetchall() == [("keep me",)]


def test_added_columns_survive_a_database_that_predates_them(fresh_db):
    """ALTER TABLE ADD COLUMN has no IF NOT EXISTS in SQLite.

    Re-applying the schema to a database that already has the column must be a
    no-op rather than an error, or every startup after the first fails.
    """
    connection = db_schema.connect(fresh_db)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(listings)")}
    assert "last_description_changed_at" in columns
    assert "last_ai_evaluated_at" in columns

    db_schema.apply_schema(connection, force=True)  # must not raise


def test_foreign_keys_are_on_for_every_connection(fresh_db):
    """SQLite wants this per connection, so it is forgotten roughly always.

    Deleting a campaign once left its searches, listings and messages behind as
    unreachable orphans, under a comment claiming the cascade worked.
    """
    connection = db_schema.connect(fresh_db)
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_no_module_declares_tables_outside_the_schema_file():
    """The rule that keeps the other tests meaningful.

    Two declarations of one table drift. route_searches was declared in both
    runtimes before this file existed.
    """
    offenders = []
    for directory, _, filenames in os.walk(ROOT):
        if any(
            part in directory
            for part in (".git", "node_modules", "venv", ".wt", "data_copy")
        ):
            continue
        for filename in filenames:
            if not filename.endswith((".py", ".js")):
                continue
            if filename.startswith("test_") or ".test." in filename:
                continue
            path = os.path.join(directory, filename)
            relative = os.path.relpath(path, ROOT)
            if relative in ("scripts/seed_fixture_db.js",):
                continue  # builds a throwaway CI fixture, deliberately its own
            try:
                text = open(path, encoding="utf-8").read()
            except (OSError, UnicodeDecodeError):
                continue
            if re.search(r"CREATE\s+TABLE", text, re.I):
                offenders.append(relative)

    assert offenders == [], (
        "These declare tables outside db/schema.sql, which is how a table ends "
        f"up existing in two shapes: {offenders}"
    )


def test_db_setup_refuses_to_delete_without_being_told_twice(fresh_db):
    """The script that deleted production while pointed somewhere else."""
    db_schema.connect(fresh_db).execute(
        "INSERT INTO campaigns (name) VALUES ('precious')"
    ).connection.commit()

    result = subprocess.run(
        ["node", os.path.join(ROOT, "backend", "db_setup.js"), "--recreate"],
        env={**os.environ, "PRISMDEALS_DB": fresh_db},
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Refusing to delete" in result.stderr
    connection = sqlite3.connect(fresh_db)
    assert connection.execute("SELECT name FROM campaigns").fetchall() == [
        ("precious",)
    ]


def test_db_setup_writes_where_it_is_pointed(fresh_db):
    """It hardcoded data/scraper.db while the server honoured PRISMDEALS_DB.

    So a command that reads as obviously safe destroyed production instead.
    """
    result = subprocess.run(
        ["node", os.path.join(ROOT, "backend", "db_setup.js")],
        env={**os.environ, "PRISMDEALS_DB": fresh_db},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert fresh_db in result.stdout
    assert "campaigns" in tables(sqlite3.connect(fresh_db))
