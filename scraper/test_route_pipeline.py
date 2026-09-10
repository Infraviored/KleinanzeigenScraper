import sqlite3

import pytest

import route_pipeline
import route_search
import route_store
import routing

BASE = (
    "https://www.kleinanzeigen.de/s-landsberg-am-lech/"
    "ikea-brimnes-kleiderschrank/k0l0r30"
)


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.executescript("""
        CREATE TABLE searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id INTEGER, name TEXT,
            url TEXT UNIQUE, enabled INTEGER DEFAULT 1, knowledge_set_id INTEGER);
        CREATE TABLE listings (
            id TEXT PRIMARY KEY, title TEXT, price TEXT, location TEXT, url TEXT,
            search_id INTEGER);
    """)
    route_store.ensure_schema(connection)
    yield connection
    connection.close()


class FakeOsrm:
    """Straight-line durations at 60 km/h, and a straight route."""

    def __init__(self):
        self.calls = 0

    def route(self, points, geometry=True):
        from geo import haversine_km

        line = [points[0], points[-1]]
        km = haversine_km(*line)
        # A few intermediate vertices, so corridor maths has something to walk.
        dense = [
            (
                points[0][0] + (points[-1][0] - points[0][0]) * i / 20,
                points[0][1] + (points[-1][1] - points[0][1]) * i / 20,
            )
            for i in range(21)
        ]
        return routing.Route(dense, duration_s=km * 60, distance_m=km * 1000)

    def duration_s(self, points):
        from geo import haversine_km

        self.calls += 1
        return sum(haversine_km(a, b) for a, b in zip(points, points[1:])) * 60.0


def suggest(query):
    return {"_0": "Deutschland", f"_{int(query)}": f"{query} Ort"}


def make_route(conn, **kwargs):
    options = dict(
        base_url=BASE,
        origin="86899",
        destination="78462",
        radius_km=30.0,
        half_width_km=15.0,
        client=FakeOsrm(),
        resolver=route_search.LocationResolver(fetch=suggest),
    )
    options.update(kwargs)
    return route_pipeline.create(conn, **options)


# --- resolving where a buyer is ------------------------------------------


def test_a_postal_code_resolves_to_coordinates():
    assert route_pipeline.resolve_place("82266") == pytest.approx(
        (48.076, 11.152), abs=0.01
    )


def test_a_town_with_its_state_resolves():
    assert route_pipeline.resolve_place("Konstanz, Baden-Württemberg") is not None


def test_coordinates_pass_through():
    assert route_pipeline.resolve_place((48.0, 11.0)) == (48.0, 11.0)


def test_an_unplaceable_origin_raises_rather_than_guessing():
    """A silently wrong origin yields a plausible corridor through the wrong part
    of the country — far more expensive than an error."""
    with pytest.raises(ValueError, match="Unknown postal code"):
        route_pipeline.resolve_place("00000")

    with pytest.raises(ValueError, match="Could not place"):
        route_pipeline.resolve_place("Nirgendwoburg")


def test_an_ambiguous_town_name_is_refused_with_advice():
    with pytest.raises(ValueError, match="Ort, Bundesland"):
        route_pipeline.resolve_place("Salem")


# --- creating a route search ---------------------------------------------


def test_creating_a_route_registers_one_ordinary_search_per_circle(conn):
    route_id, plan = make_route(conn)

    searches = conn.execute("SELECT url FROM searches").fetchall()
    assert len(searches) == len(plan.circles)
    for (url,) in searches:
        assert route_search.parse_tail(url)["location"]


def test_the_registered_searches_carry_the_buyers_knowledge_set(conn):
    """Otherwise the corridor scrapes listings nothing knows how to score."""
    make_route(conn, knowledge_set_id=7, campaign_id=3)

    rows = conn.execute("SELECT knowledge_set_id, campaign_id FROM searches").fetchall()
    assert rows and all(row == (7, 3) for row in rows)


def test_the_plan_is_stored_so_the_corridor_can_be_redrawn(conn):
    route_id, plan = make_route(conn)

    stored = route_store.get_plan(conn, route_id)
    assert len(stored["circles"]) == len(plan.circles)
    assert len(route_store.polyline(conn, route_id)) > 1


def test_two_routes_sharing_a_circle_reuse_the_same_search(conn):
    """searches.url is unique; overlapping corridors must be cheap, not an error."""
    first, _ = make_route(conn)
    second, _ = make_route(conn, destination="78462", name="zweite Fahrt")

    urls = conn.execute("SELECT COUNT(*), COUNT(DISTINCT url) FROM searches").fetchone()
    assert urls[0] == urls[1]

    circles = conn.execute(
        "SELECT COUNT(*) FROM route_search_circles WHERE route_search_id = ?", (second,)
    ).fetchone()[0]
    assert circles > 0, "the second route must still know its own circles"


def test_a_corridor_with_no_resolvable_centre_refuses_to_be_created(conn):
    with pytest.raises(ValueError, match="cannot be searched"):
        make_route(
            conn,
            resolver=route_search.LocationResolver(
                fetch=lambda q: {"_0": "Deutschland"}
            ),
        )


# --- annotating detours --------------------------------------------------


def seed_listing(conn, listing_id, location, route_id, index=0):
    search_id = conn.execute(
        "SELECT search_id FROM route_search_circles WHERE route_search_id = ? "
        "ORDER BY search_id LIMIT 1 OFFSET ?",
        (route_id, index),
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO listings (id, title, price, location, url, search_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (listing_id, "Brimnes", "60 €", location, "https://x/" + listing_id, search_id),
    )
    conn.commit()


def test_detours_are_computed_and_stored(conn):
    route_id, _ = make_route(conn)
    seed_listing(conn, "a", "Bayern - Landsberg (Lech)", route_id)

    summary = route_pipeline.annotate(conn, route_id, client=FakeOsrm())

    assert summary["routed"] == 1
    stored = route_store.geo_for_route(conn, route_id)["a"]
    assert stored["detour_min"] is not None
    assert stored["coordinates"] is not None


def test_a_second_run_does_not_recompute_what_it_already_knows(conn):
    """A thousand-listing route must not re-route yesterday's answers."""
    route_id, _ = make_route(conn)
    seed_listing(conn, "a", "Bayern - Landsberg (Lech)", route_id)
    route_pipeline.annotate(conn, route_id, client=FakeOsrm())

    client = FakeOsrm()
    summary = route_pipeline.annotate(conn, route_id, client=client)

    assert summary["considered"] == 0
    assert client.calls == 0


def test_a_listing_whose_place_cannot_be_resolved_is_recorded_not_retried(conn):
    route_id, _ = make_route(conn)
    seed_listing(conn, "a", "Irgendwo - Nirgendwoburg", route_id)

    first = route_pipeline.annotate(conn, route_id, client=FakeOsrm())
    second = route_pipeline.annotate(conn, route_id, client=FakeOsrm())

    assert first["unplaceable"] == 1
    assert second["considered"] == 0, "an unplaceable listing must not be retried"


def test_listings_far_off_the_route_are_marked_without_being_routed(conn):
    route_id, _ = make_route(conn)
    seed_listing(conn, "a", "Nordrhein-Westfalen - Oberhausen", route_id)

    client = FakeOsrm()
    summary = route_pipeline.annotate(conn, route_id, client=client)

    assert summary["too_far"] == 1
    assert client.calls == 0


def test_one_listing_found_by_two_circles_is_counted_once(conn):
    route_id, _ = make_route(conn)
    seed_listing(conn, "a", "Bayern - Landsberg (Lech)", route_id)

    assert len(route_store.listings_for_route(conn, route_id)) == 1


def test_ranking_puts_the_cheapest_detour_first_and_the_unknown_last(conn):
    """An unmeasured trip is not a free one."""
    route_id, _ = make_route(conn)
    seed_listing(conn, "near", "Bayern - Landsberg (Lech)", route_id)
    seed_listing(conn, "far", "Bayern - Kempten", route_id, index=1)
    seed_listing(conn, "nowhere", "Irgendwo - Nirgendwoburg", route_id, index=1)
    route_pipeline.annotate(conn, route_id, client=FakeOsrm())

    order = [listing["id"] for listing in route_pipeline.ranked(conn, route_id)]

    assert order[0] == "near"
    assert order[-1] == "nowhere"


def test_annotating_a_route_without_geometry_is_an_error(conn):
    with pytest.raises(ValueError, match="no stored geometry"):
        route_pipeline.annotate(conn, 999, client=FakeOsrm())
