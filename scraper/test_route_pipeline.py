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


# --- second review: retry semantics and concurrency -----------------------


class BrokenOsrm(FakeOsrm):
    """Routing that is down right now, but will not be forever."""

    def duration_s(self, points):
        raise routing.RoutingError("connection refused")


def test_a_routing_outage_is_retried_rather_than_recorded_as_settled(conn):
    """A minute of downtime must not become a permanent gap: the three reasons a
    listing has no detour all stored a null, so they were indistinguishable."""
    route_id, _ = make_route(conn)
    seed_listing(conn, "a", "Bayern - Landsberg (Lech)", route_id)

    outage = route_pipeline.annotate(conn, route_id, client=BrokenOsrm())
    assert outage["failed"] == 1 and outage["routed"] == 0

    recovered = route_pipeline.annotate(conn, route_id, client=FakeOsrm())

    assert recovered["considered"] == 1, "the failed listing must come back"
    assert recovered["routed"] == 1
    assert route_store.geo_for_route(conn, route_id)["a"]["detour_min"] is not None


def test_a_settled_listing_is_never_asked_about_again(conn):
    """Answered, too far, or unplaceable — all three are done."""
    route_id, _ = make_route(conn)
    seed_listing(conn, "answered", "Bayern - Landsberg (Lech)", route_id)
    seed_listing(conn, "far", "Nordrhein-Westfalen - Oberhausen", route_id, index=1)
    seed_listing(conn, "nowhere", "Irgendwo - Nirgendwoburg", route_id, index=1)
    route_pipeline.annotate(conn, route_id, client=FakeOsrm())

    statuses = {
        listing_id: row["status"]
        for listing_id, row in route_store.geo_for_route(conn, route_id).items()
    }
    assert statuses == {
        "answered": route_store.ROUTED,
        "far": route_store.TOO_FAR,
        "nowhere": route_store.UNPLACEABLE,
    }

    client = FakeOsrm()
    assert route_pipeline.annotate(conn, route_id, client=client)["considered"] == 0
    assert client.calls == 0


def test_a_search_created_concurrently_is_adopted_not_crashed_into(conn):
    """searches.url is unique, and the SELECT that precedes the INSERT is not
    atomic. The row that wins the race is the row this circle has to use, so the
    loser adopts it instead of raising IntegrityError."""
    # A plan whose searches do not exist yet, or the SELECT finds them and the
    # INSERT this test is about never runs.
    plan = route_search.plan(
        BASE,
        FakeOsrm().route([(48.0, 10.0), (48.0, 11.0)]),
        radius_km=30.0,
        half_width_km=15.0,
        resolver=route_search.LocationResolver(fetch=suggest),
    )
    assert plan.circles

    class RacingCursor:
        """Slips the row in just before save_plan's own INSERT reaches sqlite."""

        def __init__(self, cursor, connection):
            self._cursor = cursor
            self._connection = connection
            self.raced = False

        def execute(self, sql, parameters=()):
            if "INSERT INTO searches" in sql and not self.raced:
                self.raced = True
                self._connection.execute(
                    "INSERT INTO searches (campaign_id, name, url, enabled, "
                    "knowledge_set_id) VALUES (?, ?, ?, 1, ?)",
                    (1, "someone else got there first", parameters[2], 1),
                )
            return self._cursor.execute(sql, parameters)

        def __getattr__(self, name):
            return getattr(self._cursor, name)

    class RacingConnection:
        def __init__(self, connection):
            self._connection = connection
            self.cursor_wrapper = None

        def cursor(self):
            self.cursor_wrapper = RacingCursor(
                self._connection.cursor(), self._connection
            )
            return self.cursor_wrapper

        def __getattr__(self, name):
            return getattr(self._connection, name)

    racing = RacingConnection(conn)

    second_id, _ = route_store.save_plan(
        racing,
        plan,
        base_url=BASE,
        origin="86899",
        destination="78462",
        knowledge_set_id=1,
    )

    assert racing.cursor_wrapper.raced, "the fixture must actually cause the race"
    assert second_id, "the race must not abort the plan"

    circles = conn.execute(
        "SELECT COUNT(*) FROM route_search_circles WHERE route_search_id = ?",
        (second_id,),
    ).fetchone()[0]
    assert circles == len(plan.circles), "every circle still belongs to the route"

    urls = conn.execute("SELECT COUNT(*), COUNT(DISTINCT url) FROM searches").fetchone()
    assert urls[0] == urls[1], "and no duplicate url was created"


# --- redrawing a corridor after the fact ----------------------------------


def test_replanning_a_corridor_keeps_what_it_already_found(conn):
    """Widening a corridor must not throw away the listings already in it.

    The reason to widen one is that something was missed, and starting over
    would discard the very listings that are the evidence for widening.
    """
    route_id, plan = make_route(conn, half_width_km=15.0)
    kept_url = plan.circles[0].url
    conn.execute(
        "INSERT INTO listings (id, title, search_id) "
        "SELECT 'listing-1', 'A wardrobe', id FROM searches WHERE url = ?",
        (kept_url,),
    )
    conn.commit()

    kept, added, removed, _ = route_pipeline.replan(
        conn,
        route_id,
        radius_km=30.0,
        half_width_km=5.0,
        client=FakeOsrm(),
        resolver=route_search.LocationResolver(fetch=suggest),
    )

    assert kept >= 1, "a circle that survives keeps its search row"
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM listings l JOIN searches s ON s.id = l.search_id "
            "WHERE s.url = ?",
            (kept_url,),
        ).fetchone()[0]
        == 1
    ), "and its listings come with it"


def test_a_wider_corridor_needs_more_circles(conn):
    """d = 2*sqrt(r^2 - w^2). Widening the corridor shortens the spacing.

    It reads backwards until the geometry is in view — a wider corridor sounds
    like fewer, larger circles — and I had this the wrong way round in this
    test's name until the API said otherwise: at r=30 the same 201 km route
    takes 5 searches at w=5 and 6 at w=20. The preview shows this number before
    anyone commits to it, so it had better be right.
    """
    route_id, narrow = make_route(conn, half_width_km=5.0)

    _, _, _, wide = route_pipeline.replan(
        conn,
        route_id,
        radius_km=30.0,
        half_width_km=25.0,
        client=FakeOsrm(),
        resolver=route_search.LocationResolver(fetch=suggest),
    )

    assert len(wide.circles) > len(narrow.circles)


def test_replanning_gives_listings_beyond_the_old_edge_another_look(conn):
    """A listing marked too_far was judged against the corridor as it was.

    Redraw it and that judgement is stale. Listings already routed keep their
    detour: the route has not moved, only which listings count as being on it.
    """
    route_id, _ = make_route(conn)
    conn.executemany(
        "INSERT INTO listing_route_geo "
        "(listing_id, route_search_id, detour_min, status, computed_at) "
        "VALUES (?, ?, ?, ?, '2026-01-01')",
        [
            ("far-one", route_id, None, "too_far"),
            ("near-one", route_id, 12.0, "routed"),
        ],
    )
    conn.commit()

    route_pipeline.replan(
        conn,
        route_id,
        radius_km=30.0,
        half_width_km=5.0,
        client=FakeOsrm(),
        resolver=route_search.LocationResolver(fetch=suggest),
    )

    statuses = dict(
        conn.execute(
            "SELECT listing_id, status FROM listing_route_geo "
            "WHERE route_search_id = ?",
            (route_id,),
        )
    )
    assert statuses["far-one"] == "failed", "queued for another look"
    assert statuses["near-one"] == "routed", "an answered listing stays answered"
