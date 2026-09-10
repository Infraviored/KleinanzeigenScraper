import math

import pytest

import corridor
import geo
from geo import haversine_km

INNING = (48.0762653, 11.1523493)
MUNICH = (48.1440989, 11.5695525)

# A due-east line at ~48 N, sampled every ~10 km, standing in for a route.
STRAIGHT = [(48.0, 11.0 + step * 0.134) for step in range(11)]


def test_haversine_matches_a_known_distance():
    # Inning am Ammersee to Munich centre is about 32 km as the crow flies.
    assert haversine_km(INNING, MUNICH) == pytest.approx(32, abs=1.5)


def test_spacing_is_the_widest_that_still_covers_the_corridor():
    """The midpoint at the corridor edge must land exactly on the circle."""
    radius, half_width = 25.0, 10.0
    spacing = corridor.spacing_for_corridor(radius, half_width)

    worst_case = math.hypot(spacing / 2, half_width)
    assert worst_case == pytest.approx(radius)


def test_a_narrower_corridor_permits_wider_spacing():
    assert corridor.spacing_for_corridor(25, 5) > corridor.spacing_for_corridor(25, 20)


def test_a_corridor_wider_than_the_circles_is_refused():
    """No spacing covers it, so returning a tiny one would mean endless fetches."""
    with pytest.raises(ValueError, match="cannot be covered"):
        corridor.spacing_for_corridor(25, 25)
    with pytest.raises(ValueError):
        corridor.spacing_for_corridor(25, 40)


def test_centres_start_and_end_on_the_route_endpoints():
    """The two places a buyer is certain to stand must both be covered."""
    points = corridor.centres(STRAIGHT, radius_km=25, half_width_km=10)

    assert haversine_km(points[0], STRAIGHT[0]) == pytest.approx(0, abs=0.01)
    assert haversine_km(points[-1], STRAIGHT[-1]) == pytest.approx(0, abs=0.01)


def test_every_corridor_point_lands_inside_some_circle():
    """The property the spacing formula exists to guarantee."""
    radius, half_width = 25.0, 10.0
    points = corridor.centres(STRAIGHT, radius, half_width)
    total = corridor.length_km(STRAIGHT)

    for step in range(0, 201):
        along = total * step / 200
        on_route = corridor.point_at_km(STRAIGHT, along)
        # Offset to the very edge of the corridor, north and south.
        for sign in (1, -1):
            edge = (on_route[0] + sign * half_width / 111.19, on_route[1])
            closest = min(haversine_km(edge, centre) for centre in points)
            assert closest <= radius + 0.5, f"gap at {along:.1f} km, side {sign}"


def test_a_wider_corridor_needs_more_circles():
    narrow = corridor.centres(STRAIGHT, radius_km=25, half_width_km=5)
    wide = corridor.centres(STRAIGHT, radius_km=25, half_width_km=20)

    assert len(wide) > len(narrow)


def test_covering_beats_naive_sampling_on_request_count():
    """The measurement that motivates the module: fewer fetches, same coverage."""
    total = corridor.length_km(STRAIGHT)
    naive = math.ceil(total / 15) + 1  # a point every 15 km, radius 25
    covering = len(corridor.centres(STRAIGHT, radius_km=25, half_width_km=10))

    assert covering < naive


def test_point_at_km_interpolates_within_a_segment():
    midpoint = corridor.point_at_km(STRAIGHT, corridor.length_km(STRAIGHT) / 2)
    from_start = haversine_km(STRAIGHT[0], midpoint)

    assert from_start == pytest.approx(corridor.length_km(STRAIGHT) / 2, abs=0.5)


def test_point_at_km_clamps_outside_the_route():
    assert corridor.point_at_km(STRAIGHT, -50) == STRAIGHT[0]
    assert corridor.point_at_km(STRAIGHT, 10_000) == STRAIGHT[-1]


def test_a_single_point_route_yields_a_single_circle():
    assert corridor.centres([INNING], 25, 10) == [INNING]
    assert corridor.length_km([INNING]) == 0.0


def test_distance_to_route_is_measured_to_the_line_not_the_vertices():
    """A point beside a segment's middle is close, even if far from both ends."""
    segment = [(48.0, 11.0), (48.0, 12.0)]  # ~74 km long
    beside_the_middle = (48.05, 11.5)

    assert corridor.distance_to_route_km(beside_the_middle, segment) == pytest.approx(
        5.6, abs=0.6
    )
    assert haversine_km(beside_the_middle, segment[0]) > 30


def test_distance_to_segment_clamps_beyond_the_ends():
    segment_start, segment_end = (48.0, 11.0), (48.0, 11.1)
    well_past = (48.0, 12.0)

    clamped = corridor.distance_to_segment_km(well_past, segment_start, segment_end)
    assert clamped == pytest.approx(haversine_km(well_past, segment_end), rel=0.02)


def test_nearest_vertex_index():
    assert corridor.nearest_vertex_index(STRAIGHT[3], STRAIGHT) == 3


# --- postal centroids ----------------------------------------------------


def test_the_shipped_centroid_table_covers_germany():
    table = geo.centroids()

    assert len(table) > 8000
    assert "82266" in table
    assert table.coordinates("82266") == pytest.approx(INNING, abs=0.01)


def test_unknown_postal_codes_return_nothing_rather_than_guessing():
    assert geo.centroids().coordinates("00000") is None
    assert geo.centroids().coordinates("nonsense") is None


def test_nearest_postal_code_to_a_point():
    code, coords, km = geo.centroids().nearest(INNING)

    assert code == "82266"
    assert km == pytest.approx(0, abs=0.5)
    assert coords == pytest.approx(INNING, abs=0.01)


def test_postal_lookup_tolerates_whitespace():
    assert geo.centroids().coordinates(" 82266 ") is not None
