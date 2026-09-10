"""Covering a route corridor with the fewest search circles.

A platform search takes one centre and one radius. A route is a line. Bridging
the two is the whole job of this module, and the naive bridge — drop a point
every so many kilometres and use a generous radius — is wrong twice over.

It is wrong on cost: circles spaced well inside their own radius overlap heavily,
so the same listing is fetched three or four times. Against a site that starts
refusing after a handful of requests, redundant fetches are the scarce resource.

It is wrong on meaning: a 25 km radius around every point describes a corridor
50 km wide, which is not a corridor at all. What a buyer actually specifies is
how far off the route they are willing to turn — the half-width w. Once w and the
radius r are fixed, the spacing is not a matter of taste:

    d = 2 · sqrt(r² − w²)

The point hardest to reach lies midway between two neighbouring circles at the
very edge of the corridor. Its distance to either centre is sqrt((d/2)² + w²),
and that equals r exactly at the spacing above. Anything wider leaves a diamond
of corridor uncovered; anything narrower is paid-for overlap.
"""

import math

from geo import haversine_km, interpolate

EARTH_RADIUS_KM = 6371.0088


def spacing_for_corridor(radius_km, half_width_km):
    """Largest centre spacing that still covers a corridor of the given half-width.

    Raises when the corridor is at least as wide as the circles are large: no
    spacing covers it, and silently returning a tiny number would bury an
    impossible request under thousands of fetches.
    """
    if radius_km <= 0:
        raise ValueError("radius_km must be positive")
    if half_width_km < 0:
        raise ValueError("half_width_km must not be negative")
    if half_width_km >= radius_km:
        raise ValueError(
            f"A corridor half-width of {half_width_km} km cannot be covered by "
            f"circles of radius {radius_km} km. Widen the radius or narrow the "
            f"corridor."
        )
    return 2 * math.sqrt(radius_km**2 - half_width_km**2)


def cumulative_km(polyline):
    """Arc length at each vertex, starting at 0."""
    totals = [0.0]
    for previous, current in zip(polyline, polyline[1:]):
        totals.append(totals[-1] + haversine_km(previous, current))
    return totals


def length_km(polyline):
    return cumulative_km(polyline)[-1] if len(polyline) > 1 else 0.0


def point_at_km(polyline, distance_km):
    """The point that far along the polyline, interpolating within a segment."""
    if len(polyline) == 1:
        return polyline[0]

    totals = cumulative_km(polyline)
    if distance_km <= 0:
        return polyline[0]
    if distance_km >= totals[-1]:
        return polyline[-1]

    for index in range(1, len(totals)):
        if totals[index] >= distance_km:
            segment = totals[index] - totals[index - 1]
            if segment == 0:
                return polyline[index]
            fraction = (distance_km - totals[index - 1]) / segment
            return interpolate(polyline[index - 1], polyline[index], fraction)
    return polyline[-1]


def centres(polyline, radius_km, half_width_km):
    """Circle centres covering the corridor, endpoints included.

    Spacing is the route length divided by the smallest whole number of gaps that
    keeps it within the covering limit. Landing exactly on both endpoints matters:
    a buyer's origin and destination are the two places they are guaranteed to
    stand, and an off-by-one-gap layout that stops short of the destination is the
    one gap they would notice.
    """
    if not polyline:
        return []
    if len(polyline) == 1:
        return [polyline[0]]

    limit = spacing_for_corridor(radius_km, half_width_km)
    total = length_km(polyline)
    if total == 0:
        return [polyline[0]]

    gaps = max(1, math.ceil(total / limit))
    step = total / gaps
    return [point_at_km(polyline, index * step) for index in range(gaps + 1)]


def _km_per_degree(latitude):
    """Kilometres per degree of latitude and of longitude, at this latitude.

    Longitude degrees shrink towards the poles, which is the whole reason this
    is a function of latitude rather than a constant.
    """
    per_degree_lat = math.pi * EARTH_RADIUS_KM / 180.0
    return per_degree_lat, per_degree_lat * math.cos(math.radians(latitude))


def distance_to_segment_km(point, start, end):
    """Perpendicular distance from a point to a segment, clamped to its ends.

    Projected onto a plane local to the point. Over segment lengths of a few
    kilometres the distortion is far below the precision this feeds.
    """
    lat_scale, lon_scale = _km_per_degree(point[0])

    def project(p):
        return ((p[1] - point[1]) * lon_scale, (p[0] - point[0]) * lat_scale)

    ax, ay = project(start)
    bx, by = project(end)
    dx, dy = bx - ax, by - ay

    if dx == 0 and dy == 0:
        return math.hypot(ax, ay)

    t = -(ax * dx + ay * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(ax + t * dx, ay + t * dy)


def project_onto_route(point, polyline):
    """Returns (along_km, offroute_km) for the closest point on the route.

    `along_km` is the arc length at which the route passes closest to `point`.
    It has to be measured against the segments rather than the vertices: a route
    drawn with two vertices a hundred kilometres apart passes right by a town in
    the middle, yet that town's nearest *vertex* is fifty kilometres away at one
    of the ends. Anchoring a detour there would route a listing that is directly
    on the way as a long backtrack.
    """
    if not polyline:
        return 0.0, float("inf")
    if len(polyline) == 1:
        return 0.0, haversine_km(point, polyline[0])

    totals = cumulative_km(polyline)
    best_along, best_off = 0.0, float("inf")

    for index, (start, end) in enumerate(zip(polyline, polyline[1:])):
        offroute = distance_to_segment_km(point, start, end)
        if offroute >= best_off:
            continue

        segment_km = totals[index + 1] - totals[index]
        fraction = _foot_fraction(point, start, end) if segment_km else 0.0
        best_along = totals[index] + fraction * segment_km
        best_off = offroute

    return best_along, best_off


def _foot_fraction(point, start, end):
    """Position of the perpendicular foot along a segment, clamped to [0, 1]."""
    lat_scale, lon_scale = _km_per_degree(point[0])

    ax = (start[1] - point[1]) * lon_scale
    ay = (start[0] - point[0]) * lat_scale
    bx = (end[1] - point[1]) * lon_scale
    by = (end[0] - point[0]) * lat_scale
    dx, dy = bx - ax, by - ay

    if dx == 0 and dy == 0:
        return 0.0
    t = -(ax * dx + ay * dy) / (dx * dx + dy * dy)
    return max(0.0, min(1.0, t))


def distance_to_route_km(point, polyline):
    """Shortest distance from a point to anywhere on the route.

    This is a straight-line distance, not a detour: it says how far off the
    corridor a listing sits, which is the right cheap filter to apply before
    spending a routing request on the honest number.
    """
    return project_onto_route(point, polyline)[1]


def nearest_vertex_index(point, polyline):
    """Index of the route vertex closest to a point."""
    return min(
        range(len(polyline)),
        key=lambda index: haversine_km(point, polyline[index]),
    )


# A stretch of route over which the direction of travel swings by more than this
# has turned around. Measured over a window rather than at a single vertex: a
# driver turns via a roundabout, a slip road or a pair of junctions, and each of
# the eight or ten points that describes one deflects by only twenty or thirty
# degrees. Looking for a sharp corner finds the U-turn drawn as one vertex and
# misses every turnaround that a real road actually offers.
REVERSAL_DEGREES = 120.0

# How far the swing may take. Long enough for a motorway interchange loop, short
# enough that a winding valley road -- which also turns 120 degrees, over
# kilometres, while going somewhere -- is not mistaken for one.
REVERSAL_WINDOW_KM = 1.5


def _bearing(start_point, end_point):
    """Direction of travel between two points, in degrees."""
    lat_scale, lon_scale = _km_per_degree(start_point[0])
    east = (end_point[1] - start_point[1]) * lon_scale
    north = (end_point[0] - start_point[0]) * lat_scale
    if east == 0 and north == 0:
        return None
    return math.degrees(math.atan2(east, north))


def _angle_between(first, second):
    """Smallest angle between two bearings, 0-180."""
    difference = abs(first - second) % 360.0
    return difference if difference <= 180.0 else 360.0 - difference


def reversal_points(
    polyline,
    from_km=None,
    to_km=None,
    threshold_deg=REVERSAL_DEGREES,
    window_km=REVERSAL_WINDOW_KM,
):
    """Arc lengths at which the route turns back on itself.

    These are the points a router must be told about. Handed two positions on
    either side of a turnaround, it drives straight between them -- correct for a
    router, wrong for us, because the driver is going round the turn. Everything
    between two consecutive waypoints is the router's choice, so a turnaround
    falling in such a gap is silently cut off.

    Returns the middle of each turn, which is the point worth passing through.
    """
    if len(polyline) < 3:
        return []

    totals = cumulative_km(polyline)
    found = []
    index = 1

    while index < len(polyline) - 1:
        here = totals[index]
        if (from_km is not None and here <= from_km) or (
            to_km is not None and here >= to_km
        ):
            index += 1
            continue

        # The direction being travelled just before this point...
        incoming = _bearing(polyline[index - 1], polyline[index])
        if incoming is None:
            index += 1
            continue

        # ...against the direction at every point within the window ahead.
        end = index + 1
        turned_at = None
        while end < len(polyline):
            # The next segment always counts, however long it is: a route drawn
            # with two kilometres between vertices turns around between two of
            # them, and a window smaller than one step would never look at it.
            # Past that first step, the window decides.
            if end > index + 1 and totals[end] - here > window_km:
                break
            outgoing = _bearing(polyline[end - 1], polyline[end])
            if (
                outgoing is not None
                and _angle_between(incoming, outgoing) >= threshold_deg
            ):
                turned_at = end
                break
            end += 1

        if turned_at is None:
            index += 1
            continue

        # The middle of the turn, so the waypoint sits on the loop rather than
        # at the moment the swing completes.
        middle = (here + totals[turned_at]) / 2.0
        found.append(middle)

        # Clear of the whole turn before looking again. Resuming just past the
        # point where the swing completed lands inside the same loop, whose
        # second half then reads as a second turnaround.
        index = turned_at + 1
        while index < len(polyline) - 1 and totals[index] - middle <= window_km:
            index += 1

    return found


# A route doubles back when it returns to somewhere it has already been. Two
# positions this far apart along the route...
TURNAROUND_MIN_SEPARATION_KM = 15.0

# ...yet this close on the ground.
TURNAROUND_MAX_GAP_KM = 4.0

# How finely to sample when looking for that.
TURNAROUND_SAMPLE_KM = 2.0


def turnaround_points(
    polyline,
    min_separation_km=TURNAROUND_MIN_SEPARATION_KM,
    max_gap_km=TURNAROUND_MAX_GAP_KM,
    sample_km=TURNAROUND_SAMPLE_KM,
):
    """Arc lengths where the route genuinely turns back on itself.

    `reversal_points` above asks whether the direction of travel swings round,
    and on a real road the answer is yes constantly: roundabouts, motorway
    interchanges, a switchback out of a valley. Landsberg to Konstanz — a route
    that never doubles back — has twelve of them. Handing those to a router as
    waypoints pins the journey to the road already chosen, which is precisely
    the mistake that charged Friedrichshafen 140 minutes for a 15-minute stop.

    So this asks the question that actually matters for a detour: does the route
    come back to somewhere it has already been? Two positions far apart along
    the route but close together on the ground mean the driver goes out and
    returns, and a listing near that stretch must be priced against the whole
    loop rather than against a shortcut across it.

    A roundabout fails this test — two hundred metres later the route is two
    hundred metres away, not fifteen kilometres of driving from itself.
    """
    total = length_km(polyline)
    if total < min_separation_km:
        return []

    steps = int(total / sample_km) + 1
    samples = [
        (index * sample_km, point_at_km(polyline, index * sample_km))
        for index in range(steps + 1)
    ]

    found = []
    for i, (km_a, point_a) in enumerate(samples):
        for km_b, point_b in samples[i + 1 :]:
            if km_b - km_a < min_separation_km:
                continue
            if haversine_km(point_a, point_b) <= max_gap_km:
                # The apex of the loop, not the midpoint of the pair that found
                # it. The waypoint has to be the place the driver actually turns
                # round: put it short of that and the comparison journey stops
                # short too, quietly under-charging every listing near the turn.
                apex = max(
                    (
                        km_a + step * sample_km
                        for step in range(int((km_b - km_a) / sample_km) + 1)
                    ),
                    key=lambda km: haversine_km(point_a, point_at_km(polyline, km)),
                )
                # One waypoint per loop, not one per sampled pair inside it.
                if not found or apex - found[-1] > min_separation_km:
                    found.append(apex)
                break

    return found
