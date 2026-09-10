import pytest

import route_search
import routing

BRIMNES = (
    "https://www.kleinanzeigen.de/s-inning-am-ammersee/preis:10:60/"
    "ikea-brimnes-kleiderschrank/k0l13533r25"
)
LAPTOPS = (
    "https://www.kleinanzeigen.de/s-notebooks/muenchen/preis::450/laptop/k0c278l6411"
)


def test_tail_parsing_covers_the_shapes_the_site_emits():
    assert route_search.parse_tail(BRIMNES) == {
        "keyword": "k0",
        "category": None,
        "location": "l13533",
        "radius": 25,
    }
    assert route_search.parse_tail(LAPTOPS) == {
        "keyword": "k0",
        "category": "c278",
        "location": "l6411",
        "radius": None,
    }
    assert route_search.parse_tail("https://www.kleinanzeigen.de/s-tiere/k0c130") == {
        "keyword": "k0",
        "category": "c130",
        "location": None,
        "radius": None,
    }


def test_a_url_without_the_grammar_is_refused_not_guessed():
    assert route_search.parse_tail("https://www.kleinanzeigen.de/s-notebooks/") is None

    with pytest.raises(ValueError, match="re-aimable"):
        route_search.with_location("https://www.kleinanzeigen.de/s-notebooks/", 1, 25)


def test_re_aiming_replaces_only_the_final_segment():
    """The readable path is decoration; rewriting it could only break things."""
    moved = route_search.with_location(BRIMNES, "6358", 30)

    assert moved == (
        "https://www.kleinanzeigen.de/s-inning-am-ammersee/preis:10:60/"
        "ikea-brimnes-kleiderschrank/k0l6358r30"
    )


def test_re_aiming_keeps_the_category():
    moved = route_search.with_location(LAPTOPS, "13533", 17)
    assert moved.endswith("/k0c278l13533r17")
    assert "/preis::450/laptop/" in moved


def test_location_ids_are_accepted_in_any_of_their_written_forms():
    for form in ("6358", "l6358", "_6358"):
        assert route_search.with_location(BRIMNES, form, 30).endswith("l6358r30")


def test_radius_is_rounded_to_a_whole_kilometre():
    """Measured: the site serves any integer radius, not only its dropdown values."""
    assert route_search.with_location(BRIMNES, "1", 17.4).endswith("r17")
    assert route_search.with_location(BRIMNES, "1", 0.2).endswith("r1")


# --- location resolution -------------------------------------------------

SUGGESTIONS = {
    "82266": {"_0": "Deutschland", "_6358": "82266 Inning am Ammersee"},
    "78462": {"_0": "Deutschland", "_6741": "78462 Konstanz"},
    "99999": {"_0": "Deutschland"},
}


def fake_fetch(query):
    return SUGGESTIONS.get(str(query), {})


def test_resolving_a_postal_code_to_a_location_id():
    identifier, label = route_search.resolve_location_id("82266", fake_fetch)

    assert identifier == "6358"
    assert label == "82266 Inning am Ammersee"


def test_the_whole_country_is_never_accepted_as_a_centre():
    """`_0` means Germany. Searching all of it because a village was unknown is
    the one outcome worse than skipping the circle."""
    identifier, _ = route_search.resolve_location_id("99999", fake_fetch)

    assert identifier is None


def test_the_resolver_asks_once_per_postal_code():
    calls = []

    def counting(query):
        calls.append(query)
        return SUGGESTIONS.get(str(query), {})

    resolver = route_search.LocationResolver(fetch=counting)
    resolver.for_postal_code("82266")
    resolver.for_postal_code("82266")
    resolver.for_postal_code(" 82266 ")

    assert calls == ["82266"]


# --- planning ------------------------------------------------------------


class FakeCentroids:
    """A handful of towns on a west-east line, ~40 km apart."""

    TOWNS = {
        "10000": (48.0, 10.0),
        "20000": (48.0, 10.54),
        "30000": (48.0, 11.08),
        "40000": (48.0, 11.62),
        "50000": (48.0, 12.16),
    }

    def coordinates(self, code):
        return self.TOWNS.get(str(code).strip())

    def nearest(self, point):
        from geo import haversine_km

        code = min(self.TOWNS, key=lambda c: haversine_km(point, self.TOWNS[c]))
        return code, self.TOWNS[code], haversine_km(point, self.TOWNS[code])


def fake_town_fetch(query):
    return {"_0": "Deutschland", f"_{int(query) // 100}": f"{query} Testort"}


def straight_route(km_points=6):
    line = [(48.0, 10.0 + step * 0.29) for step in range(km_points)]
    return routing.Route(line, duration_s=3600, distance_m=120_000)


def build_plan(**kwargs):
    options = dict(
        radius_km=25.0,
        half_width_km=10.0,
        resolver=route_search.LocationResolver(fetch=fake_town_fetch),
        centroids=FakeCentroids(),
    )
    options.update(kwargs)
    return route_search.plan(BRIMNES, straight_route(), **options)


def test_a_plan_produces_re_aimed_urls_for_every_circle():
    result = build_plan()

    assert result.circles
    for url in result.urls:
        parts = route_search.parse_tail(url)
        assert parts["location"] and parts["radius"]
        assert "/ikea-brimnes-kleiderschrank/" in url


def test_each_circle_absorbs_its_own_snap_and_nobody_elses():
    """Centres must land on places that have ids, which moves them. Because the
    radius is a free parameter the shift is paid for rather than ignored — but
    per circle, so one awkward centre cannot inflate the whole corridor."""
    result = build_plan()

    for circle in result.circles:
        assert circle.radius_km >= 25
        assert circle.radius_km == pytest.approx(25 + circle.snap_km, abs=1)

    tight = min(result.circles, key=lambda c: c.snap_km)
    loose = max(result.circles, key=lambda c: c.snap_km)
    if loose.snap_km - tight.snap_km > 1:
        assert tight.radius_km < loose.radius_km


def test_a_circle_that_snaps_far_does_not_widen_its_neighbours():
    """Measured on Landsberg->Konstanz: the centre near Lindau falls in the lake
    and snaps 12 km. Charging every circle for that would turn a 30 km search
    into a 43 km one and drown the corridor in off-route listings."""

    class LopsidedCentroids(FakeCentroids):
        TOWNS = dict(FakeCentroids.TOWNS, **{"30000": (48.15, 11.08)})  # ~17 km off

    result = build_plan(centroids=LopsidedCentroids())
    far = [c for c in result.circles if c.snap_km > 5]
    near = [c for c in result.circles if c.snap_km <= 5]

    assert far and near, "the fixture must produce both kinds of circle"
    assert max(c.radius_km for c in near) < min(c.radius_km for c in far)


def test_two_centres_snapping_onto_one_town_yield_one_search():
    """Otherwise a dense stretch of route pays twice for identical results."""
    result = build_plan(radius_km=25.0, half_width_km=23.0)  # very tight spacing
    ids = [circle.location_id for circle in result.circles]

    assert len(ids) == len(set(ids))


def test_an_impossible_corridor_fails_before_any_lookup_happens():
    def explode(query):
        raise AssertionError("no lookup should happen for an impossible corridor")

    with pytest.raises(ValueError, match="cannot be covered"):
        build_plan(
            half_width_km=30.0,
            resolver=route_search.LocationResolver(fetch=explode),
        )


def test_unresolvable_centres_are_reported_rather_than_dropped_in_silence():
    result = build_plan(
        resolver=route_search.LocationResolver(fetch=lambda q: {"_0": "Deutschland"})
    )

    assert result.circles == []
    assert result.unresolved


def test_the_plan_serialises_for_the_map():
    payload = build_plan().as_dict()

    assert payload["distance_km"] == pytest.approx(120.0)
    assert payload["duration_min"] == 60
    assert len(payload["polyline"]) > 1
    assert payload["circles"][0]["location_id"]


# --- detours -------------------------------------------------------------


class FakeOsrm:
    """Durations proportional to straight-line distance at 60 km/h."""

    def __init__(self):
        self.calls = 0

    def duration_s(self, points):
        from geo import haversine_km

        self.calls += 1
        total = sum(haversine_km(a, b) for a, b in zip(points, points[1:]))
        return total * 60.0


def test_detour_is_extra_driving_time_not_distance_from_the_route():
    """The number the whole feature turns on."""
    line = [(48.0, 10.0), (48.0, 12.0)]
    on_the_way = (48.0, 11.0)
    off_to_the_side = (48.2, 11.0)

    client = FakeOsrm()
    assert routing.detour_minutes(client, line, on_the_way) == pytest.approx(0, abs=0.1)
    assert routing.detour_minutes(client, line, off_to_the_side) > 20


def test_a_trip_that_goes_nowhere_makes_every_listing_a_round_trip():
    """Both anchors collapse, and out-and-back becomes the honest cost."""
    line = [(48.0, 10.0), (48.0, 10.0)]
    aside = (48.1, 10.0)

    minutes = routing.detour_minutes(FakeOsrm(), line, aside)
    one_way = FakeOsrm().duration_s([line[0], aside]) / 60.0

    assert minutes == pytest.approx(2 * one_way, rel=0.05)


def test_a_listing_beside_a_short_route_is_not_charged_a_full_round_trip():
    """The trip continues past the listing, so the return leg is partly free."""
    line = [(48.0, 10.0), (48.0, 10.05)]  # ~3.7 km
    aside = (48.1, 10.0)  # ~11 km to the side

    minutes = routing.detour_minutes(FakeOsrm(), line, aside)
    one_way = FakeOsrm().duration_s([line[0], aside]) / 60.0

    assert one_way < minutes < 2 * one_way


def test_a_listing_on_a_coarsely_drawn_route_is_anchored_where_it_belongs():
    """A route drawn with two distant vertices still passes by the towns between
    them; anchoring on the nearest vertex would route those as a backtrack."""
    line = [(48.0, 10.0), (48.0, 12.0)]  # one 148 km segment, no middle vertex
    along_km, offroute = __import__("corridor").project_onto_route((48.0, 11.0), line)

    assert along_km == pytest.approx(74, abs=2)
    assert offroute == pytest.approx(0, abs=0.1)


def test_listings_far_off_the_route_are_rejected_without_a_routing_request():
    line = [(48.0, 10.0), (48.0, 12.0)]
    client = FakeOsrm()

    annotated = routing.annotate_detours(
        client,
        line,
        [{"id": "a", "coordinates": (49.5, 11.0)}],
        max_offroute_km=20,
    )

    assert annotated[0]["too_far"] is True
    assert annotated[0]["detour_min"] is None
    assert client.calls == 0, "distance already proves the detour is hopeless"


def test_listings_without_coordinates_survive_annotation():
    annotated = routing.annotate_detours(
        FakeOsrm(), [(48.0, 10.0), (48.0, 12.0)], [{"id": "a"}]
    )

    assert annotated[0]["detour_min"] is None
