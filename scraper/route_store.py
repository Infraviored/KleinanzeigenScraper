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
import db_schema
import json
import logging
import sqlite3

logger = logging.getLogger(__name__)

# The route_searches DDL lives in db/schema.sql, applied by db_schema.
# It was declared here too until the two copies began to drift.

# Why a listing has no detour, which decides whether asking again is worthwhile.
# Without this the three reasons are indistinguishable — all of them store a null
# detour — and a routing service that was briefly down would mark every listing
# of that run as settled forever.
ROUTED = "routed"  # answered
TOO_FAR = "too_far"  # deliberately not routed; distance already decides it
UNPLACEABLE = "unplaceable"  # no coordinates, and none are coming
FAILED = "failed"  # the attempt failed; try again next run

RETRYABLE = (FAILED,)


def ensure_schema(conn):
    """Bring the connection up to db/schema.sql.

    The route tables used to be declared here *and* in backend/server.js, and
    the two had already begun to drift. Both sides now read one file.
    """
    db_schema.apply_schema(conn)


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

    Returns (route_search_id, conflicts). A conflict is a circle that had to
    reuse an existing search row whose binding differs from this route's — a
    different knowledge set or campaign, or one that is disabled. Reuse itself is
    what makes overlapping corridors cheap rather than an error; reuse of a row
    that means something else is a problem the caller has to see.
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

    conflicts = attach_circles(
        conn,
        route_id,
        plan,
        name=name,
        destination=destination,
        campaign_id=campaign_id,
        knowledge_set_id=knowledge_set_id,
    )
    conn.commit()
    return route_id, conflicts


def attach_circles(
    conn,
    route_search_id,
    plan,
    name=None,
    destination=None,
    campaign_id=None,
    knowledge_set_id=None,
):
    """Registers each circle of `plan` as an ordinary search on this route.

    Split out of save_plan so that redrawing a corridor and building one use the
    same code. A circle whose url already has a search row reuses it, which is
    what lets a corridor be widened without re-scraping what it already found —
    and what lets two overlapping corridors share the work.

    Returns the conflicts: circles that had to reuse a row meaning something
    else.
    """
    cursor = conn.cursor()
    conflicts = []
    for index, circle in enumerate(plan.circles, 1):
        label = f"{name or destination} · {index}/{len(plan.circles)} {circle.label}"

        existing = cursor.execute(
            "SELECT id, campaign_id, knowledge_set_id, enabled FROM searches "
            "WHERE url = ?",
            (circle.url,),
        ).fetchone()

        if existing is None:
            try:
                cursor.execute(
                    "INSERT INTO searches (campaign_id, name, url, enabled, "
                    "knowledge_set_id) VALUES (?, ?, ?, 1, ?)",
                    (campaign_id, label, circle.url, knowledge_set_id),
                )
                search_id = cursor.lastrowid
            except sqlite3.IntegrityError:
                # Someone inserted this url between the SELECT above and here.
                # `searches.url` is unique, so the row that won is the row this
                # circle has to use — the same outcome as finding it in the
                # first place, reached a moment later.
                logger.info(
                    "Search for %s was created concurrently; using that row.",
                    circle.url,
                )
                existing = cursor.execute(
                    "SELECT id, campaign_id, knowledge_set_id, enabled FROM "
                    "searches WHERE url = ?",
                    (circle.url,),
                ).fetchone()
                if existing is None:
                    logger.warning(
                        "Could not register or find a search for %s; this circle "
                        "is not part of the route.",
                        circle.url,
                    )
                    continue

        if existing is not None:
            # `searches.url` is unique, so a corridor crossing a town another
            # search already covers has to reuse that row. Reuse is only safe
            # when the row means the same thing: a search bound to a different
            # knowledge set would score wardrobes with laptop criteria, and a
            # disabled one would never be scraped at all. Silently accepting
            # either was the original mistake — the circle is now recorded, and
            # the mismatch reported, rather than pretending it was registered.
            search_id, existing_campaign, existing_set, enabled = existing
            mismatch = []
            if knowledge_set_id is not None and existing_set != knowledge_set_id:
                mismatch.append(
                    f"knowledge set {existing_set} instead of {knowledge_set_id}"
                )
            if campaign_id is not None and existing_campaign != campaign_id:
                mismatch.append(
                    f"campaign {existing_campaign} instead of {campaign_id}"
                )
            if not enabled:
                mismatch.append("disabled")

            if mismatch:
                conflicts.append(
                    {
                        "url": circle.url,
                        "search_id": search_id,
                        "label": circle.label,
                        "reasons": mismatch,
                    }
                )
                logger.warning(
                    "Circle %s reuses existing search %s, which is %s. Its "
                    "listings will not be scored the way this route expects.",
                    circle.label,
                    search_id,
                    " and ".join(mismatch),
                )

        cursor.execute(
            "INSERT OR REPLACE INTO route_search_circles "
            "(route_search_id, search_id, location_id, label, radius_km) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                route_search_id,
                search_id,
                circle.location_id,
                circle.label,
                circle.radius_km,
            ),
        )

    return conflicts


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


def route(conn, route_search_id):
    """The stored route, rebuilt well enough to price stretches of itself.

    The per-segment durations are carried through so a detour is measured
    against what the drive actually costs, not against a fresh shortest path
    between the same two anchors.
    """
    import routing

    plan = get_plan(conn, route_search_id)
    if not plan:
        return None

    points = [(lat, lon) for lat, lon in plan.get("polyline", [])]
    if len(points) < 2:
        return None

    return routing.Route(
        polyline=points,
        duration_s=(plan.get("duration_min") or 0) * 60.0,
        distance_m=(plan.get("distance_km") or 0) * 1000.0,
    )


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


def save_geo(
    conn,
    route_search_id,
    listing_id,
    coordinates,
    offroute_km,
    detour_min,
    status=ROUTED,
):
    ensure_schema(conn)
    lat, lon = coordinates if coordinates else (None, None)
    conn.execute(
        "INSERT OR REPLACE INTO listing_route_geo "
        "(listing_id, route_search_id, lat, lon, offroute_km, detour_min, status, "
        "computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            listing_id,
            route_search_id,
            lat,
            lon,
            offroute_km,
            detour_min,
            status,
            _now(),
        ),
    )
    conn.commit()


def geo_for_route(conn, route_search_id):
    """Listing id -> what we know about its position on this route."""
    rows = conn.execute(
        "SELECT listing_id, lat, lon, offroute_km, detour_min, status "
        "FROM listing_route_geo WHERE route_search_id = ?",
        (route_search_id,),
    ).fetchall()
    return {
        row[0]: {
            "coordinates": (row[1], row[2]) if row[1] is not None else None,
            "offroute_km": row[3],
            "detour_min": row[4],
            "status": row[5],
        }
        for row in rows
    }


def pending_geo(conn, route_search_id):
    """Listings on this route still worth asking about.

    Never seen before, or seen and failed. A listing that was answered, was too
    far to be worth routing, or has no resolvable place is settled — asking again
    would cost a request and change nothing. A listing whose attempt failed is
    not settled, and treating it as though it were is how one minute of routing
    downtime turns into a permanent gap.
    """
    known = geo_for_route(conn, route_search_id)
    return [
        listing
        for listing in listings_for_route(conn, route_search_id)
        if known.get(listing["id"], {}).get("status", FAILED) in RETRYABLE
    ]


def definition(conn, route_search_id):
    """What the route was asked for: url, both ends, and its bindings.

    Companion to `get_plan`, which returns the drawn shape. This returns the
    question that produced it, so a corridor can be redrawn without the caller
    knowing the column layout.
    """
    row = conn.execute(
        "SELECT base_url, origin, destination, name, campaign_id, knowledge_set_id "
        "FROM route_searches WHERE id = ?",
        (route_search_id,),
    ).fetchone()
    if row is None:
        return None
    keys = ("base_url", "origin", "destination", "name", "campaign_id", "set_id")
    return dict(zip(keys, row))


def replace_circles(
    conn,
    route_search_id,
    plan,
    name=None,
    destination=None,
    campaign_id=None,
    knowledge_set_id=None,
):
    """Swaps a route's circles for a freshly drawn plan's, in one step.

    The search rows behind the circles are deliberately not touched: attach_circles
    reuses any search whose url already exists, so a circle that survives the new
    plan keeps everything already scraped through it. That is what makes widening
    a corridor cheap instead of a fresh start.

    It holds only while the radius stays put. The radius is part of the search
    url, so changing it rewrites every circle's url and nothing is recognised as
    the same search — measured: changing a corridor's radius reported "0 kept,
    5 added, 7 removed" and left the previous searches, with their listings,
    detached from the route. Widening the corridor at the same radius is the
    cheap operation; changing the radius is closer to a fresh start, and the
    caller should expect to re-scrape.
    """
    conn.execute(
        "DELETE FROM route_search_circles WHERE route_search_id = ?",
        (route_search_id,),
    )
    conn.execute(
        "UPDATE route_searches SET radius_km = ?, half_width_km = ?, plan_json = ? "
        "WHERE id = ?",
        (
            plan.radius_km,
            plan.half_width_km,
            json.dumps(plan.as_dict(), ensure_ascii=False),
            route_search_id,
        ),
    )
    conflicts = attach_circles(
        conn,
        route_search_id,
        plan,
        name=name,
        destination=destination,
        campaign_id=campaign_id,
        knowledge_set_id=knowledge_set_id,
    )
    conn.commit()
    return conflicts


def retire_searches(conn, urls, keep_route_id=None):
    """Switches off searches that no route covers any more.

    Deleting the circle rows was not enough: the search behind a dropped circle
    kept `enabled = 1` and its campaign, so the scraper went on fetching it every
    run and its listings went on arriving. Narrowing a corridor to cut the load
    against a site that rate-limits therefore cut nothing, and repeated redraws
    piled up searches nobody had asked for.

    Disabled rather than deleted: the listings already found through it are real
    and stay reachable in the campaign. Only searches no other route still uses
    are touched.
    """
    retired = 0
    for url in urls:
        row = conn.execute("SELECT id FROM searches WHERE url = ?", (url,)).fetchone()
        if row is None:
            continue
        search_id = row[0]
        still_used = conn.execute(
            "SELECT 1 FROM route_search_circles WHERE search_id = ? LIMIT 1",
            (search_id,),
        ).fetchone()
        if still_used:
            continue
        conn.execute("UPDATE searches SET enabled = 0 WHERE id = ?", (search_id,))
        retired += 1
    conn.commit()
    return retired


def circle_urls(conn, route_search_id):
    """The search urls this route currently covers."""
    return {
        url
        for (url,) in conn.execute(
            "SELECT s.url FROM route_search_circles c JOIN searches s "
            "ON s.id = c.search_id WHERE c.route_search_id = ?",
            (route_search_id,),
        )
    }


def requeue(conn, route_search_id, from_status=TOO_FAR):
    """Puts settled rows back in the queue, for when the question changed.

    A listing marked too_far was judged against the corridor as it was; redraw
    it and that judgement is stale. Rows already routed keep their detour — the
    route has not moved, only which listings count as being on it.
    """
    cursor = conn.execute(
        "UPDATE listing_route_geo SET status = ?, detour_min = NULL "
        "WHERE route_search_id = ? AND status = ?",
        (FAILED, route_search_id, from_status),
    )
    conn.commit()
    return cursor.rowcount
