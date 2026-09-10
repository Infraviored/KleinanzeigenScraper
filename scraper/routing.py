"""Routes and detours, via OSRM.

The number this module exists to produce is the detour: how much longer the trip
becomes if a listing is collected on the way.

    detour = drive(A -> listing -> B) - drive(A -> B)

Straight-line distance cannot answer that. A wardrobe five kilometres off the
motorway down a dead-end lane costs ten kilometres and a turnaround; one fifteen
kilometres away but on the road already being driven costs almost nothing. For a
bulky, cheap item the detour is a large part of the real price, which is why it
belongs beside the score rather than behind a filter.

The detour is computed locally, between two anchors that bracket the listing's
nearest point on the route, not by re-routing the whole journey per listing. Both
give the same answer whenever the listing is genuinely near the corridor — the
untouched parts of the route cancel in the subtraction — and the local form keeps
each listing to one short request instead of one long one.

Only the half with the listing in it is a request. What the same stretch costs
without the listing is read off the route's own per-segment durations, which both
halves the requests and, more importantly, keeps the comparison honest: a routing
service asked for the time between two points answers with the best way between
them, and on a there-and-back trip that is not the way the driver is going.
"""

import logging
import time

logger = logging.getLogger(__name__)

DEFAULT_OSRM_URL = "https://router.project-osrm.org"

# The public demo server is a courtesy. One request every this many seconds.
MIN_REQUEST_INTERVAL_S = 1.0


class RoutingError(RuntimeError):
    pass


class Route:
    """A driven route: its shape, and what it costs to drive.

    `segment_durations` holds the driving time of each step of the polyline, so
    the cost of any stretch of the route can be read off rather than re-routed.
    That distinction matters more than it sounds: asking a routing service for
    the time between two points on a route gives the *best* way between them,
    which is not the way the driver is going. On a there-and-back trip two
    anchors fifteen kilometres apart along the route can be neighbours on the
    same road, and the "direct" time then skips the entire turnaround.
    """

    def __init__(self, polyline, duration_s, distance_m, segment_durations=None):
        self.polyline = polyline
        self.duration_s = duration_s
        self.distance_m = distance_m
        self.segment_durations = segment_durations
        self._cumulative_km = None
        self._cumulative_s = None

    def _build_profile(self):
        """Arc length and elapsed driving time at each vertex."""
        import corridor

        self._cumulative_km = corridor.cumulative_km(self.polyline)

        durations = self.segment_durations
        if not durations or len(durations) != len(self.polyline) - 1:
            # No per-segment times: spread the total evenly by distance. Coarser
            # than the real thing — a motorway kilometre is not a town kilometre
            # — but it still measures time along the route rather than along a
            # shortcut the driver will not take.
            total_km = self._cumulative_km[-1] or 1.0
            self._cumulative_s = [
                km / total_km * self.duration_s for km in self._cumulative_km
            ]
            return

        elapsed, running = [0.0], 0.0
        for step in durations:
            running += step
            elapsed.append(running)
        self._cumulative_s = elapsed

    def duration_at_km(self, distance_km):
        """Elapsed driving time at a point that far along the route."""
        if self._cumulative_km is None:
            self._build_profile()

        totals, elapsed = self._cumulative_km, self._cumulative_s
        if distance_km <= 0:
            return elapsed[0]
        if distance_km >= totals[-1]:
            return elapsed[-1]

        for index in range(1, len(totals)):
            if totals[index] >= distance_km:
                span = totals[index] - totals[index - 1]
                if span == 0:
                    return elapsed[index]
                fraction = (distance_km - totals[index - 1]) / span
                return elapsed[index - 1] + fraction * (
                    elapsed[index] - elapsed[index - 1]
                )
        return elapsed[-1]

    def duration_between_km(self, from_km, to_km):
        """Driving time along this route between two arc lengths."""
        return abs(self.duration_at_km(to_km) - self.duration_at_km(from_km))

    @property
    def duration_min(self):
        return self.duration_s / 60.0

    @property
    def distance_km(self):
        return self.distance_m / 1000.0

    def __repr__(self):
        return (
            f"Route({len(self.polyline)} points, "
            f"{self.distance_km:.1f} km, {self.duration_min:.0f} min)"
        )


def _waypoints(points):
    """OSRM takes lon,lat — the reverse of every other coordinate here."""
    return ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)


class OsrmClient:
    """Minimal OSRM client with throttling and a per-process cache.

    Caching is keyed on the rounded coordinates of the whole request. Listings in
    one postal district resolve to the same key, so a route through a town costs
    one request rather than one per listing.
    """

    def __init__(self, base_url=DEFAULT_OSRM_URL, fetch_json=None, profile="driving"):
        self.base_url = base_url.rstrip("/")
        self.profile = profile
        self._fetch_json = fetch_json or self._default_fetch
        self._cache = {}
        self._last_request_at = 0.0

    def _default_fetch(self, url):
        import requests

        wait = MIN_REQUEST_INTERVAL_S - (time.monotonic() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

        response = requests.get(url, timeout=20)
        if response.status_code != 200:
            raise RoutingError(f"OSRM returned {response.status_code} for {url}")
        return response.json()

    def route(self, points, geometry=True):
        """Route through the given (lat, lon) points."""
        if len(points) < 2:
            raise ValueError("A route needs at least two points")

        key = (
            "route",
            geometry,
            tuple((round(lat, 5), round(lon, 5)) for lat, lon in points),
        )
        if key in self._cache:
            return self._cache[key]

        url = (
            f"{self.base_url}/route/v1/{self.profile}/{_waypoints(points)}"
            f"?overview={'full' if geometry else 'false'}&geometries=geojson"
            + ("&annotations=duration" if geometry else "")
        )
        payload = self._fetch_json(url)

        if payload.get("code") != "Ok" or not payload.get("routes"):
            raise RoutingError(
                f"OSRM could not route these points: {payload.get('code')}"
            )

        first = payload["routes"][0]
        coordinates = (first.get("geometry") or {}).get("coordinates") or []

        # Per-segment durations, concatenated across legs, so the cost of any
        # stretch of the route can be read off instead of re-routed.
        segment_durations = []
        for leg in first.get("legs") or []:
            annotation = leg.get("annotation") or {}
            segment_durations.extend(annotation.get("duration") or [])

        result = Route(
            polyline=[(lat, lon) for lon, lat in coordinates] or list(points),
            duration_s=first["duration"],
            distance_m=first["distance"],
            segment_durations=segment_durations or None,
        )
        self._cache[key] = result
        return result

    def duration_s(self, points):
        return self.route(points, geometry=False).duration_s


def detour_minutes(client, route, point):
    """Extra driving time to collect something at `point` while driving `route`.

        detour = drive(the route, with the listing inserted) - drive(the route)

    For an ordinary journey from A to B that is exactly `drive(A -> point -> B)
    minus drive(A -> B)`: one request per listing, against the whole trip, which
    is the definition and what a driver comparing this against their phone sees.

    An earlier version measured it locally instead, between anchors fifteen
    kilometres either side of the listing, feeding the route's own vertices back
    in as waypoints so both halves described the same path. It over-reported,
    badly:

        Friedrichshafen     140 min      actual  15 min
        Bermatingen         153 min      actual  37 min
        Ueberlingen          85 min      actual  19 min

    Two mistakes compounded. Forcing the route's vertices back in turns any
    diversion into an out-and-back from the nearest route point, when a driver
    would leave earlier and rejoin later. And the fifteen-kilometre bracket
    forbids exactly that: around Lake Constance, rejoining within fifteen
    kilometres means driving round the lake and back, which is how a
    fifteen-minute stop came to cost two hours. Dropping the waypoints alone
    fixed the inland cases exactly -- Huglfing 97 against 97, Peissenberg 86
    against 86 -- and left the lake ones as wrong, because the bracket was the
    other half of it.

    What the waypoints were right about is kept, in the smallest form that
    works. A journey that doubles back has the same start and end, so
    `drive(A -> point -> A)` is free to skip the far end of it entirely and the
    subtraction goes negative. Only the turnarounds are therefore passed back to
    the router -- the points that carry the route's shape. An ordinary A-to-B
    route has none of them, and the call is the plain three-point one.
    """
    import corridor

    polyline = route.polyline
    if len(polyline) < 2:
        there = client.duration_s([polyline[0], point])
        return 2 * there / 60.0

    at_km, _ = corridor.project_onto_route(point, polyline)
    turns = corridor.turnaround_points(polyline)

    waypoints = [polyline[0]]
    waypoints += [corridor.point_at_km(polyline, km) for km in turns if km < at_km]
    waypoints.append(point)
    waypoints += [corridor.point_at_km(polyline, km) for km in turns if km >= at_km]
    waypoints.append(polyline[-1])

    via = client.duration_s(waypoints)
    return max(0.0, (via - route.duration_s) / 60.0)


def annotate_detours(client, route, listings, max_offroute_km=None):
    """Adds a `detour_min` to each listing that carries coordinates.

    Listings further from the route than `max_offroute_km` are marked without a
    routing request: the straight-line distance already proves the detour is at
    least twice that, so spending a request to learn precisely how bad it is
    would be wasted.
    """
    import corridor

    polyline = route.polyline
    annotated = []
    for listing in listings:
        coords = listing.get("coordinates")
        if not coords:
            annotated.append(dict(listing, detour_min=None, offroute_km=None))
            continue

        offroute = corridor.distance_to_route_km(coords, polyline)
        if max_offroute_km is not None and offroute > max_offroute_km:
            annotated.append(
                dict(listing, detour_min=None, offroute_km=offroute, too_far=True)
            )
            continue

        try:
            minutes = detour_minutes(client, route, coords)
        except (RoutingError, KeyError, ValueError) as exc:
            # A failed attempt is not an answer. Saying so lets the caller try
            # again rather than filing a routing outage as a settled result.
            logger.info("No detour for listing %s: %s", listing.get("id"), exc)
            annotated.append(
                dict(listing, detour_min=None, offroute_km=offroute, failed=True)
            )
            continue

        annotated.append(dict(listing, detour_min=minutes, offroute_km=offroute))
    return annotated
