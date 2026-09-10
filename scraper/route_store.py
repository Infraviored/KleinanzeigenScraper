"""Route searches as first-class rows, and where listings sit relative to them.

A route search is not a new kind of search. It is one buyer intent expressed as
several ordinary searches — one per circle covering the corridor — and the rest
of the system already knows how to run those. So this module writes into the
existing `searches` table rather than beside it, and everything downstream
(scraping, extraction, scoring) keeps working without knowing a route exists.

Two things do need somewhere to live:

- the route itself, so a corridor can be re-planned or re-drawn without asking
  the routing service again, and so the circles can be traced back to the intent
  that produced them;
- where each listing sits relative to that route. The detour is a property of
  (listing, route), not of the listing, so it belongs in its own table for the
  same reason fact sheets do: one listing on two routes has two detours, and
  neither is a fact about the listing.
"""

import datetime
import json
import logging

logger = logging.getLogger(__name__)

SCHEMA = """
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

CREATE TABLE IF NOT EXISTS route_search_circles (
    route_search_id INTEGER NOT NULL,
    search_id       INTEGER NOT NULL,
    location_id     TEXT,
    label           TEXT,
    radius_km       REAL,
    PRIMARY KEY (route_search_id, search_id)
);

CREATE TABLE IF NOT EXISTS listing_route_geo (
    listing_id      TEXT NOT NULL,
    route_search_id INTEGER NOT NULL,
    lat             REAL,
    lon             REAL,
    offroute_km     REAL,
    detour_min      REAL,
    computed_at     TEXT NOT NULL,
    PRIMARY KEY (listing_id, route_search_id)
);
"""


def ensure_schema(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def save_plan(
    conn,
    plan,
    base_url,
    origin,
    destination,
    name=None,
    campaign_id=None,
    knowledge_set_id=None,
):
    """Stores a corridor plan and registers each circle as an ordinary search.

    Returns the route search id. Circles are inserted with `INSERT OR IGNORE`
    because `searches.url` is unique: a corridor that overlaps one the user
    already had reuses that search rather than failing, which is the behaviour
    that makes overlapping routes cheap instead of an error.
    """
    ensure_schema(conn)

    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO route_searches (name, campaign_id, knowledge_set_id, base_url, "
        "origin, destination, radius_km, half_width_km, plan_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            name or f"{origin} → {destination}",
            campaign_id,
            knowledge_set_id,
            base_url,
            origin,
            destination,
            plan.radius_km,
            plan.half_width_km,
            json.dumps(plan.as_dict(), ensure_ascii=False),
            _now(),
        ),
    )
    route_id = cursor.lastrowid

    for index, circle in enumerate(plan.circles, 1):
        cursor.execute(
            "INSERT OR IGNORE INTO searches (campaign_id, name, url, enabled, "
            "knowledge_set_id) VALUES (?, ?, ?, 1, ?)",
            (
                campaign_id,
                f"{name or destination} · {index}/{len(plan.circles)} {circle.label}",
                circle.url,
                knowledge_set_id,
            ),
        )
        row = cursor.execute(
            "SELECT id FROM searches WHERE url = ?", (circle.url,)
        ).fetchone()
        if row is None:
            logger.warning("Could not register a search for %s", circle.url)
            continue

        cursor.execute(
            "INSERT OR REPLACE INTO route_search_circles "
            "(route_search_id, search_id, location_id, label, radius_km) "
            "VALUES (?, ?, ?, ?, ?)",
            (route_id, row[0], circle.location_id, circle.label, circle.radius_km),
        )

    conn.commit()
    return route_id


def get_plan(conn, route_search_id):
    """The stored plan payload, or None."""
    row = conn.execute(
        "SELECT plan_json FROM route_searches WHERE id = ?", (route_search_id,)
    ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except (ValueError, TypeError):
        logger.warning("Corrupt route plan for %s", route_search_id)
        return None


def polyline(conn, route_search_id):
    plan = get_plan(conn, route_search_id)
    if not plan:
        return []
    return [(lat, lon) for lat, lon in plan.get("polyline", [])]


def listings_for_route(conn, route_search_id):
    """Every listing found through any of this route's circles.

    A listing found by two circles appears once: it is one listing, and the
    corridor is one search from the buyer's point of view.
    """
    rows = conn.execute(
        "SELECT DISTINCT l.id, l.title, l.price, l.location, l.url "
        "FROM listings l "
        "JOIN route_search_circles c ON l.search_id = c.search_id "
        "WHERE c.route_search_id = ?",
        (route_search_id,),
    ).fetchall()
    return [
        {
            "id": row[0],
            "title": row[1],
            "price": row[2],
            "location": row[3],
            "url": row[4],
        }
        for row in rows
    ]


def save_geo(conn, route_search_id, listing_id, coordinates, offroute_km, detour_min):
    ensure_schema(conn)
    lat, lon = coordinates if coordinates else (None, None)
    conn.execute(
        "INSERT OR REPLACE INTO listing_route_geo "
        "(listing_id, route_search_id, lat, lon, offroute_km, detour_min, computed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (listing_id, route_search_id, lat, lon, offroute_km, detour_min, _now()),
    )
    conn.commit()


def geo_for_route(conn, route_search_id):
    """Listing id -> what we know about its position on this route."""
    rows = conn.execute(
        "SELECT listing_id, lat, lon, offroute_km, detour_min FROM listing_route_geo "
        "WHERE route_search_id = ?",
        (route_search_id,),
    ).fetchall()
    return {
        row[0]: {
            "coordinates": (row[1], row[2]) if row[1] is not None else None,
            "offroute_km": row[3],
            "detour_min": row[4],
        }
        for row in rows
    }


def pending_geo(conn, route_search_id):
    """Listings on this route that have no detour computed yet."""
    known = geo_for_route(conn, route_search_id)
    return [
        listing
        for listing in listings_for_route(conn, route_search_id)
        if listing["id"] not in known
    ]
