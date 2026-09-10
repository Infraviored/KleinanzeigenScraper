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


def detour_minutes(client, route, point, bracket_km=15.0):
    """Extra driving time to collect something at `point` while driving `route`.

    Anchors are placed `bracket_km` before and after the listing's nearest point
    on the route, and the answer is what the trip between those two anchors costs
    with the listing inserted, minus what it costs without.

    The "without" half is read off the route, never re-routed. Asking the routing
    service for the time between the two anchors would answer with the *best* way
    between them, which is not the way the driver is going: on a there-and-back
    trip the anchors can be fifteen kilometres apart along the route and yet
    neighbours on the same road, and the shortcut skips the whole turnaround.
    Measured against that case, re-routing charged a listing sitting directly on
    the driver's path a twenty-two minute detour it does not cost.

    A listing beyond the end of the route collapses to an out-and-back, because
    both anchors clamp to the same endpoint and the route contributes nothing
    between them.
    """
    import corridor

    polyline = route.polyline
    if len(polyline) < 2:
        there = client.duration_s([polyline[0], point])
        return 2 * there / 60.0

    at_km, _ = corridor.project_onto_route(point, polyline)
    total_km = corridor.length_km(polyline)

    from_km = max(0.0, at_km - bracket_km)
    to_km = min(total_km, at_km + bracket_km)

    before = corridor.point_at_km(polyline, from_km)
    after = corridor.point_at_km(polyline, to_km)

    direct = route.duration_between_km(from_km, to_km)
    via = client.duration_s([before, point, after])
    return max(0.0, (via - direct) / 60.0)


def annotate_detours(client, route, listings, max_offroute_km=None, bracket_km=15.0):
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
            minutes = detour_minutes(client, route, coords, bracket_km=bracket_km)
        except (RoutingError, KeyError, ValueError) as exc:
            logger.info("No detour for listing %s: %s", listing.get("id"), exc)
            minutes = None

        annotated.append(dict(listing, detour_min=minutes, offroute_km=offroute))
    return annotated
