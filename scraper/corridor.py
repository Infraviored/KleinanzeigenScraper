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

    This asked a different question until it was found to be the wrong one: it
    used to look for swings in the direction of travel, and on a real road the
    answer is yes constantly — roundabouts, motorway interchanges, a switchback
    out of a valley. Landsberg to Konstanz, a route that never doubles back, has
    twelve such swings. Handing those to a router as
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

    # One walk of the polyline for the whole grid. point_at_km rebuilds the
    # cumulative distances from scratch on every call, so asking it per sample
    # walked all 4500 vertices a hundred times over -- 0.2 s on an ordinary
    # route and five seconds on one that doubles back, per call.
    samples = _sample_route(polyline, sample_km)

    found = []
    for i, (km_a, point_a) in enumerate(samples):
        for j in range(i + 1, len(samples)):
            km_b, point_b = samples[j]
            if km_b - km_a < min_separation_km:
                continue
            if haversine_km(point_a, point_b) <= max_gap_km:
                # The apex of the loop, not the midpoint of the pair that found
                # it. The waypoint has to be the place the driver actually turns
                # round: put it short of that and the comparison journey stops
                # short too, quietly under-charging every listing near the turn.
                #
                # The candidates are the samples already in hand -- recomputing
                # their positions was the second half of the same waste.
                apex, _ = max(
                    samples[i : j + 1],
                    key=lambda sample: haversine_km(point_a, sample[1]),
                )
                # One waypoint per loop, not one per sampled pair inside it.
                if not found or apex - found[-1] > min_separation_km:
                    found.append(apex)
                break

    return found


def _sample_route(polyline, sample_km):
    """(arc length, point) every `sample_km` along the route, ends included.

    Walks the polyline once and interpolates, rather than asking point_at_km
    per sample and paying for a fresh cumulative walk each time.
    """
    totals = cumulative_km(polyline)
    total = totals[-1]

    samples = []
    vertex = 0
    distance = 0.0
    while distance < total:
        while vertex + 1 < len(totals) - 1 and totals[vertex + 1] < distance:
            vertex += 1
        span = totals[vertex + 1] - totals[vertex]
        fraction = (distance - totals[vertex]) / span if span else 0.0
        samples.append(
            (distance, interpolate(polyline[vertex], polyline[vertex + 1], fraction))
        )
        distance += sample_km

    samples.append((total, polyline[-1]))
    return samples
