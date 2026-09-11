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

    def nearest_n(self, point, count=3):
        from geo import haversine_km

        ranked = sorted(self.TOWNS, key=lambda c: haversine_km(point, self.TOWNS[c]))
        return [
            (code, self.TOWNS[code], haversine_km(point, self.TOWNS[code]))
            for code in ranked[:count]
        ]


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


def straight_line_route(points):
    """A Route over `points`, driven at 60 km/h — so time mirrors distance."""
    from geo import haversine_km

    steps = [haversine_km(a, b) * 60.0 for a, b in zip(points, points[1:])]
    return routing.Route(
        polyline=list(points),
        duration_s=sum(steps),
        distance_m=sum(steps) / 60.0 * 1000.0,
    )


def test_detour_is_extra_driving_time_not_distance_from_the_route():
    """The number the whole feature turns on.

    A listing 22 km to the side of a 149 km route costs about six minutes, not
    the forty-four its distance suggests, because the driver drifts towards it
    over the whole journey rather than turning off and back. That gap is the
    entire reason this is measured in minutes of detour rather than kilometres
    of separation.

    This test used to demand more than twenty minutes, which was the answer the
    old bracketed calculation gave — it charged every listing an out-and-back
    from the nearest point on the route. The test was pinning the bug.
    """
    route = straight_line_route([(48.0, 10.0), (48.0, 12.0)])
    on_the_way = (48.0, 11.0)
    off_to_the_side = (48.2, 11.0)  # 22 km from the line

    client = FakeOsrm()
    assert routing.detour_minutes(client, route, on_the_way) == pytest.approx(
        0, abs=0.1
    )

    aside = routing.detour_minutes(client, route, off_to_the_side)
    assert aside > 1.0, "a genuine diversion still costs something"
    assert aside < 15.0, (
        "and it costs far less than the 44 minutes an out-and-back would, "
        "which is what makes detour a different question from distance"
    )


def test_an_ordinary_route_asks_the_router_the_plain_question():
    """A -> listing -> B, and nothing else.

    Every extra waypoint is a constraint on the router, and constraints only
    ever make the answer longer. The version that fed the route's own vertices
    back in charged Friedrichshafen 140 minutes for a 15-minute stop. On a route
    that never doubles back there is nothing to preserve, so nothing is sent.
    """
    route = straight_line_route([(48.0, 10.0), (48.0, 11.0), (48.0, 12.0)])
    seen = []

    class Recording(FakeOsrm):
        def duration_s(self, points):
            seen.append(list(points))
            return super().duration_s(points)

    listing = (48.1, 11.0)
    routing.detour_minutes(Recording(), route, listing)

    assert seen == [[route.polyline[0], listing, route.polyline[-1]]]


def test_a_trip_that_goes_nowhere_makes_every_listing_a_round_trip():
    """Both anchors collapse, and out-and-back becomes the honest cost."""
    route = straight_line_route([(48.0, 10.0), (48.0, 10.0)])
    aside = (48.1, 10.0)

    minutes = routing.detour_minutes(FakeOsrm(), route, aside)
    one_way = FakeOsrm().duration_s([route.polyline[0], aside]) / 60.0

    assert minutes == pytest.approx(2 * one_way, rel=0.05)


def test_a_listing_beside_a_short_route_is_not_charged_a_full_round_trip():
    """The trip continues past the listing, so the return leg is partly free."""
    route = straight_line_route([(48.0, 10.0), (48.0, 10.05)])  # ~3.7 km
    aside = (48.1, 10.0)  # ~11 km to the side

    minutes = routing.detour_minutes(FakeOsrm(), route, aside)
    one_way = FakeOsrm().duration_s([route.polyline[0], aside]) / 60.0

    assert one_way < minutes < 2 * one_way


def there_and_back_route():
    """Out 20 km east, then back the same way — 40 km driven, 0 km net."""
    out = [(48.0, 10.0 + step * 0.0268) for step in range(11)]
    return straight_line_route(out + list(reversed(out))[1:]), out


def test_a_route_that_doubles_back_does_not_invent_a_detour():
    """Anchors 15 km apart along a there-and-back trip can be neighbours on the
    same road; asking the router for the time between them answers with the
    shortcut, not with the drive. A listing directly on the outbound leg was
    charged 22 minutes it does not cost."""
    route, out = there_and_back_route()

    minutes = routing.detour_minutes(FakeOsrm(), route, out[9])

    assert minutes == pytest.approx(0, abs=1.5)


def test_a_detour_near_a_turnaround_is_charged_rather_than_clamped_to_zero():
    """The trap in the first fix, and the reason the test above is not enough on
    its own: correcting only the reference half made `via` the shorter of the two
    near a turnaround, so `max(0.0, ...)` reported every such listing as free. A
    listing genuinely off the road must still cost something."""
    route, out = there_and_back_route()

    beside_the_outbound_leg = (out[9][0] + 0.045, out[9][1])  # ~5 km north

    minutes = routing.detour_minutes(FakeOsrm(), route, beside_the_outbound_leg)

    assert minutes > 2.0, "a real diversion must not be clamped away"


def test_a_trip_that_doubles_back_keeps_its_far_end():
    """A journey out and back starts and ends in the same place, so
    `drive(A -> listing -> A)` is free to skip the far end of it entirely and
    the subtraction goes negative. The turnarounds are handed back to the router
    so the trip still goes where it was going."""
    route, out = there_and_back_route()
    seen = []

    class Recording(FakeOsrm):
        def duration_s(self, points):
            seen.append(points)
            return super().duration_s(points)

    routing.detour_minutes(Recording(), route, out[9])

    assert len(seen) == 1, "one request per listing"
    assert len(seen[0]) > 3, "the turnaround is passed back to the router"


def test_the_reference_time_is_read_off_the_route_not_re_routed():
    """Halves the requests per listing, and is what keeps the case above right."""
    route = straight_line_route([(48.0, 10.0), (48.0, 12.0)])
    client = FakeOsrm()

    routing.detour_minutes(client, route, (48.1, 11.0))

    assert client.calls == 1, "only the leg containing the listing is a request"


def test_a_listing_on_a_coarsely_drawn_route_is_anchored_where_it_belongs():
    """A route drawn with two distant vertices still passes by the towns between
    them; anchoring on the nearest vertex would route those as a backtrack."""
    line = [(48.0, 10.0), (48.0, 12.0)]  # one 148 km segment, no middle vertex
    along_km, offroute = __import__("corridor").project_onto_route((48.0, 11.0), line)

    assert along_km == pytest.approx(74, abs=2)
    assert offroute == pytest.approx(0, abs=0.1)


def test_listings_far_off_the_route_are_rejected_without_a_routing_request():
    route = straight_line_route([(48.0, 10.0), (48.0, 12.0)])
    client = FakeOsrm()

    annotated = routing.annotate_detours(
        client,
        route,
        [{"id": "a", "coordinates": (49.5, 11.0)}],
        max_offroute_km=20,
    )

    assert annotated[0]["too_far"] is True
    assert annotated[0]["detour_min"] is None
    assert client.calls == 0, "distance already proves the detour is hopeless"


def test_listings_without_coordinates_survive_annotation():
    annotated = routing.annotate_detours(
        FakeOsrm(), straight_line_route([(48.0, 10.0), (48.0, 12.0)]), [{"id": "a"}]
    )

    assert annotated[0]["detour_min"] is None


def test_two_centres_on_one_town_widen_that_circle_to_cover_both():
    """Dropping the second centre without widening the first leaves the corridor
    around it uncovered: a centre that snaps 16 km back needs radius + 16, not
    the radius + 2 the first one asked for."""

    class OneTown:
        """Everything snaps to a single town, at varying distances."""

        TOWN = (48.0, 11.0)

        def coordinates(self, code):
            return self.TOWN

        def nearest(self, point):
            from geo import haversine_km

            return "10000", self.TOWN, haversine_km(point, self.TOWN)

        def nearest_n(self, point, count=3):
            return [self.nearest(point)]

    result = build_plan(centroids=OneTown())

    assert len(result.circles) == 1, "one town can only carry one search"
    circle = result.circles[0]
    # The furthest ideal centre from that town decides how far the circle reaches.
    furthest = max(
        __import__("geo").haversine_km(OneTown.TOWN, centre)
        for centre in __import__("corridor").centres(
            straight_route().polyline, 25.0, 10.0
        )
    )
    assert circle.radius_km >= 25 + furthest - 1


def test_an_unrecognised_postal_code_falls_back_to_the_next_nearest():
    """Otherwise one unknown village punches a whole circle out of the corridor."""
    asked = []

    def only_some_are_known(query):
        asked.append(query)
        # The nearest postal code of each centre is unknown to the platform.
        if query.endswith("00"):
            return {"_0": "Deutschland"}
        return {"_0": "Deutschland", f"_{int(query)}": f"{query} Testort"}

    class TwoCandidates(FakeCentroids):
        def nearest_n(self, point, count=3):
            code, coords, km = self.nearest(point)
            # Same place, but a second code the platform does recognise.
            return [(code, coords, km), (code[:-2] + "11", coords, km + 1.0)]

    result = build_plan(
        centroids=TwoCandidates(),
        resolver=route_search.LocationResolver(fetch=only_some_are_known),
    )

    assert result.circles, "the corridor must not lose its circles"
    assert all(circle.postal_code.endswith("11") for circle in result.circles)


def test_a_centre_with_no_recognised_code_nearby_is_reported_as_a_gap():
    class TwoCandidates(FakeCentroids):
        def nearest_n(self, point, count=3):
            code, coords, km = self.nearest(point)
            return [(code, coords, km), (code[:-2] + "11", coords, km + 1.0)]

    result = build_plan(
        centroids=TwoCandidates(),
        resolver=route_search.LocationResolver(fetch=lambda q: {"_0": "Deutschland"}),
    )

    assert result.circles == []
    assert len(result.unresolved) >= 2, "every code tried is reported, not just one"
