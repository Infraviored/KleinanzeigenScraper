"""Running a route search end to end.

Two operations, deliberately separate because they happen at different times and
cost different things:

`create` plans a corridor and registers its circles as ordinary searches. It runs
once, when a buyer says where they are driving. Everything after that is the
existing pipeline: the scraper collects those searches like any other, the
extractor builds fact sheets, the scorer ranks against intent.

`annotate` computes what the ordinary pipeline cannot know — how far off the route
each listing sits, and what collecting it would cost in driving time. It runs
after scraping, over listings that do not have an answer yet, so a route with a
thousand listings does not re-route the ones it settled yesterday.

Keeping them apart is what stops the routing service from ever sitting in the
scraper's path: if routing is down, listings still arrive, they simply arrive
without a detour until the next annotate run.
"""

import logging

import geo
import route_search
import route_store
import routing

logger = logging.getLogger(__name__)

# Beyond this, the straight-line distance already proves the detour is worse than
# any listing is worth, and a routing request would only measure how much worse.
DEFAULT_MAX_OFFROUTE_KM = 40.0


def resolve_place(where, centroids=None, places=None):
    """Accepts a postal code, a "Ort, Bundesland" pair, or coordinates.

    Raises rather than guessing: a mistyped origin that silently resolves to the
    wrong town produces a plausible corridor through the wrong part of the
    country, which is far more expensive than an error message.
    """
    if isinstance(where, (tuple, list)) and len(where) == 2:
        return (float(where[0]), float(where[1]))

    text = str(where).strip()
    table = centroids or geo.centroids()

    if text.isdigit() and len(text) == 5:
        found = table.coordinates(text)
        if found:
            return found
        raise ValueError(f"Unknown postal code: {text}")

    gazetteer = places or geo.places()
    name, _, state = text.partition(",")
    found = gazetteer.coordinates(name.strip(), state.strip() or None)
    if found:
        return found

    raise ValueError(
        f"Could not place {text!r}. Give a postal code, or "
        f'"Ort, Bundesland" when the name occurs more than once.'
    )


def create(
    conn,
    base_url,
    origin,
    destination,
    radius_km=30.0,
    half_width_km=15.0,
    name=None,
    campaign_id=None,
    knowledge_set_id=None,
    client=None,
    resolver=None,
):
    """Plans a corridor and registers its searches. Returns (route_id, plan)."""
    client = client or routing.OsrmClient()

    start = resolve_place(origin)
    end = resolve_place(destination)

    route = client.route([start, end])
    plan = route_search.plan(
        base_url,
        route,
        radius_km=radius_km,
        half_width_km=half_width_km,
        resolver=resolver,
    )

    if not plan.circles:
        raise ValueError(
            "No circle centre could be resolved to a location, so this corridor "
            f"cannot be searched. Unresolved postal codes: {plan.unresolved}"
        )

    route_id, conflicts = route_store.save_plan(
        conn,
        plan,
        base_url=base_url,
        origin=str(origin),
        destination=str(destination),
        name=name,
        campaign_id=campaign_id,
        knowledge_set_id=knowledge_set_id,
    )

    logger.info(
        "Route %s: %.0f km, %.0f min, %d searches covering a %.0f km corridor.",
        route_id,
        route.distance_km,
        route.duration_min,
        len(plan.circles),
        half_width_km * 2,
    )
    if conflicts:
        logger.warning(
            "%d of %d circles reuse a search bound differently than this route. "
            "Their listings will not be scored as this route expects: %s",
            len(conflicts),
            len(plan.circles),
            "; ".join(f"{c['label']} ({', '.join(c['reasons'])})" for c in conflicts),
        )
    plan.conflicts = conflicts
    return route_id, plan


def _coordinates_for(listing, places):
    """A listing's position, from the place string the scraper stored.

    The stored form is "Bayern - Landsberg (Lech)"; the state is what makes the
    town unambiguous, so it is kept rather than split away.
    """
    text = (listing.get("location") or "").strip()
    if not text:
        return None
    state, separator, place = text.partition(" - ")
    if not separator:
        state, place = None, text
    return places.coordinates(place.strip(), (state or "").strip() or None)


def annotate(
    conn,
    route_search_id,
    client=None,
    max_offroute_km=DEFAULT_MAX_OFFROUTE_KM,
    places=None,
    limit=None,
):
    """Computes detours for listings on this route that lack one.

    Returns a summary rather than the rows: the numbers are in the database, and
    what a caller wants to know is how much was done and what could not be.
    """
    route = route_store.route(conn, route_search_id)
    if route is None:
        raise ValueError(f"Route {route_search_id} has no stored geometry.")

    client = client or routing.OsrmClient()
    gazetteer = places or geo.places()

    pending = route_store.pending_geo(conn, route_search_id)
    if limit:
        pending = pending[:limit]

    located = []
    unplaceable = 0
    for listing in pending:
        coordinates = _coordinates_for(listing, gazetteer)
        if coordinates is None:
            unplaceable += 1
            # Recorded, so an unplaceable listing is not retried on every run.
            route_store.save_geo(conn, route_search_id, listing["id"], None, None, None)
            continue
        located.append(dict(listing, coordinates=coordinates))

    annotated = routing.annotate_detours(
        client, route, located, max_offroute_km=max_offroute_km
    )

    too_far = 0
    for listing in annotated:
        if listing.get("too_far"):
            too_far += 1
        route_store.save_geo(
            conn,
            route_search_id,
            listing["id"],
            listing.get("coordinates"),
            listing.get("offroute_km"),
            listing.get("detour_min"),
        )

    summary = {
        "considered": len(pending),
        "routed": len(annotated) - too_far,
        "too_far": too_far,
        "unplaceable": unplaceable,
    }
    logger.info(
        "Route %s: %d listings considered, %d routed, %d beyond %.0f km, "
        "%d without a resolvable place.",
        route_search_id,
        summary["considered"],
        summary["routed"],
        too_far,
        max_offroute_km,
        unplaceable,
    )
    return summary


def ranked(conn, route_search_id):
    """Listings on this route, cheapest detour first.

    Listings whose detour is unknown sort last rather than first: an unmeasured
    trip is not a free one.
    """
    geo_rows = route_store.geo_for_route(conn, route_search_id)
    listings = []
    for listing in route_store.listings_for_route(conn, route_search_id):
        listings.append(dict(listing, **geo_rows.get(listing["id"], {})))

    return sorted(
        listings,
        key=lambda listing: (
            listing.get("detour_min") is None,
            listing.get("detour_min") or 0.0,
        ),
    )
