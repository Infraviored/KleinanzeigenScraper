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


def _local_metres_per_degree(latitude):
    """Scale factors for a flat approximation around a given latitude."""
    per_degree_lat = math.pi * EARTH_RADIUS_KM / 180.0
    return per_degree_lat, per_degree_lat * math.cos(math.radians(latitude))


def distance_to_segment_km(point, start, end):
    """Perpendicular distance from a point to a segment, clamped to its ends.

    Projected onto a plane local to the point. Over segment lengths of a few
    kilometres the distortion is far below the precision this feeds.
    """
    lat_scale, lon_scale = _local_metres_per_degree(point[0])

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
    lat_scale, lon_scale = _local_metres_per_degree(point[0])

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
