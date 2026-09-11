"""Turning one search into a corridor of searches along a route.

A platform search is anchored to a single place. This module takes an ordinary
search URL, a route, and how far off it a buyer will turn, and produces the small
set of searches whose circles cover that corridor.

Three measured facts shape the implementation, and each of them removes work:

1. The radius in the URL is a free parameter, not one of the values the site's
   own dropdown offers. `r17` is served exactly as readily as `r25`. That means a
   circle can be sized to the geometry instead of the geometry being bent to fit
   a dropdown.
2. Only the trailing `k…c…l…r…` segment decides what is searched. A request for
   `/s-hamburg/brimnes/k0l13533r17` returns Inning results and renders "in Inning
   am Ammersee" — the readable path is decoration. So rewriting touches the tail
   and nothing else, which keeps this working for category URLs, price filters
   and keyword URLs alike without knowing which is which.
3. Place names and postal codes resolve to location ids through the site's own
   suggestion endpoint, so a centre computed as coordinates can be expressed as
   a search.

Because a centre must land on a real place, each ideal centre is snapped to the
nearest postal code, which moves it by a few kilometres. Rather than pretend the
gap away, each circle is widened by its own snap distance — affordable precisely
because of fact 1, and per circle so that one centre landing in a lake cannot
inflate the whole corridor.
"""

import json
import logging
import math
import re
import urllib.parse

import corridor
import geo

logger = logging.getLogger(__name__)

SUGGEST_URL = "https://www.kleinanzeigen.de/s-ort-empfehlungen.json"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"
    ),
    "Accept": "application/json,text/javascript,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

# How many nearby postal codes to try before giving up on a corridor centre.
# Three, because the failure it guards against is one unrecognised village, not a
# region the platform does not know at all — and each attempt is a lookup.
POSTAL_FALLBACK_CANDIDATES = 3

# k<keyword flag> c<category> l<location> r<radius>, any of the last three absent.
TAIL_RE = re.compile(r"(k\d+)(c\d+)?(l\d+)?(r\d+)?$")


def parse_tail(url):
    """Returns the (keyword, category, location, radius) parts, or None.

    A URL whose final segment does not carry this grammar is not a search we can
    re-aim, and saying so is better than emitting a plausible URL that quietly
    searches the wrong place.
    """
    path = urllib.parse.urlsplit(url).path.rstrip("/")
    last = path.rsplit("/", 1)[-1]
    match = TAIL_RE.fullmatch(last)
    if not match:
        return None
    keyword, category, location, radius = match.groups()
    return {
        "keyword": keyword,
        "category": category,
        "location": location,
        "radius": int(radius[1:]) if radius else None,
    }


def with_location(url, location_id, radius_km):
    """Re-aims a search URL at another location and radius.

    Everything before the final segment is left byte-for-byte alone.
    """
    parts = parse_tail(url)
    if parts is None:
        raise ValueError(
            f"Not a re-aimable search URL: {url!r} — its last path segment must "
            f"look like k0c278l6411r25"
        )

    location = str(location_id)
    if not location.startswith("l"):
        location = "l" + location.lstrip("_")

    radius = max(1, int(round(radius_km)))
    tail = f"{parts['keyword']}{parts['category'] or ''}{location}r{radius}"

    split = urllib.parse.urlsplit(url)
    path = split.path.rstrip("/")
    new_path = path.rsplit("/", 1)[0] + "/" + tail
    return urllib.parse.urlunsplit(split._replace(path=new_path))


def default_suggest_fetcher(timeout=10):
    """Queries the site's own location suggestions."""
    import requests

    session = requests.Session()

    def fetch(query):
        response = session.get(
            SUGGEST_URL,
            params={"query": query},
            headers=BROWSER_HEADERS,
            timeout=timeout,
        )
        if response.status_code != 200:
            raise LookupError(
                f"Location suggestions returned {response.status_code} for {query!r}"
            )
        try:
            return response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise LookupError(f"Unreadable suggestions for {query!r}: {exc}") from exc

    return fetch


def resolve_location_id(query, fetch):
    """Location id for a place name or postal code, or None.

    The endpoint answers with `{"_0": "Deutschland", "_13533": "Inning am
    Ammersee - Bayern"}`. `_0` is the whole country and is never what a corridor
    centre means, so it is discarded — searching all of Germany because a village
    was not recognised is the worst possible failure here.
    """
    suggestions = fetch(query)
    if not isinstance(suggestions, dict):
        return None, None

    for key, label in suggestions.items():
        identifier = key.lstrip("_")
        if identifier == "0" or not identifier.isdigit():
            continue
        return identifier, label
    return None, None


class LocationResolver:
    """Postal code -> location id, cached.

    Postal codes are stable, so a resolved id stays correct indefinitely; the
    cache is what keeps a long route from hammering the endpoint.
    """

    def __init__(self, fetch=None, cache=None):
        self._fetch = fetch or default_suggest_fetcher()
        self._cache = dict(cache or {})

    @property
    def cache(self):
        return dict(self._cache)

    def for_postal_code(self, postal_code):
        code = str(postal_code).strip()
        if code not in self._cache:
            identifier, label = resolve_location_id(code, self._fetch)
            self._cache[code] = (identifier, label)
        return self._cache[code]


class Circle:
    """One search in a corridor plan."""

    def __init__(
        self, centre, postal_code, location_id, label, snap_km, radius_km, url=None
    ):
        self.centre = centre
        self.postal_code = postal_code
        self.location_id = location_id
        self.label = label
        self.snap_km = snap_km
        self.radius_km = radius_km
        self.url = url

    def as_dict(self):
        return {
            "lat": self.centre[0],
            "lon": self.centre[1],
            "postal_code": self.postal_code,
            "location_id": self.location_id,
            "label": self.label,
            "snap_km": round(self.snap_km, 2),
            "radius_km": self.radius_km,
            "url": self.url,
        }


class RoutePlan:
    """A route, the circles that cover its corridor, and the searches to run."""

    def __init__(self, route, circles, radius_km, half_width_km, unresolved=()):
        self.route = route
        self.circles = circles
        self.radius_km = radius_km
        self.half_width_km = half_width_km
        self.unresolved = list(unresolved)
        # Filled in by route_store.save_plan: circles that had to reuse an
        # existing search row bound to something else.
        self.conflicts = []

    @property
    def urls(self):
        return [circle.url for circle in self.circles if circle.url]

    def as_dict(self):
        return {
            "distance_km": round(self.route.distance_km, 1),
            "duration_min": round(self.route.duration_min),
            "radius_km": self.radius_km,
            "half_width_km": self.half_width_km,
            "polyline": [[lat, lon] for lat, lon in self.route.polyline],
            "circles": [circle.as_dict() for circle in self.circles],
            "unresolved": self.unresolved,
        }


def plan(
    base_url,
    route,
    radius_km=25.0,
    half_width_km=10.0,
    resolver=None,
    centroids=None,
):
    """Builds the corridor plan for a route.

    Raises before any network work if the corridor cannot be covered at this
    radius — a request for a 25 km-wide corridor from 25 km circles has no
    answer, and finding that out after a hundred lookups helps nobody.
    """
    corridor.spacing_for_corridor(radius_km, half_width_km)  # fail fast

    resolver = resolver or LocationResolver()
    table = centroids or geo.centroids()

    ideal = corridor.centres(route.polyline, radius_km, half_width_km)

    circles, unresolved = [], []
    by_location = {}

    for point in ideal:
        # The nearest postal code is not always one the platform recognises, and
        # giving up on the first miss punches a hole the width of a whole circle
        # in the corridor. Trying the next few nearest costs one extra lookup in
        # the rare case and nothing in the common one.
        postal_code = snapped = location_id = label = None
        snap_km = 0.0
        tried = []
        for candidate, coordinates, distance_km in table.nearest_n(
            point, POSTAL_FALLBACK_CANDIDATES
        ):
            tried.append(candidate)
            found_id, found_label = resolver.for_postal_code(candidate)
            if found_id:
                postal_code, snapped, snap_km = candidate, coordinates, distance_km
                location_id, label = found_id, found_label
                break

        if not location_id:
            unresolved.extend(tried)
            logger.info(
                "No location id for any of %s near this centre; circle skipped. "
                "The corridor has a gap here.",
                ", ".join(tried),
            )
            continue

        if len(tried) > 1:
            logger.info(
                "Postal code %s is not a known location; used %s instead, %.1f km "
                "from the ideal centre.",
                tried[0],
                postal_code,
                snap_km,
            )

        # Snapping moved this centre by snap_km, so anything the ideal centre
        # would have covered is now at most radius + snap_km away. Widening each
        # circle by its own shift restores the covering guarantee.
        #
        # Per circle, not once for the worst case: on this route the centre near
        # Lindau lands in the middle of Lake Constance, where no postal code
        # exists, and snaps 12 km. Applying that to every circle would inflate a
        # 30 km search to 43 km everywhere and flood the corridor with listings
        # that are nowhere near it — one awkward centre would undo the precision
        # the corridor is for.
        needed = math.ceil(radius_km + snap_km)

        existing = by_location.get(location_id)
        if existing is None:
            circle = Circle(snapped, postal_code, location_id, label, snap_km, needed)
            by_location[location_id] = circle
            circles.append(circle)
            continue

        # Two ideal centres snapped onto the same town, so one search has to
        # stand in for both — and it has to reach as far as the further of them
        # required. Merely dropping the second centre, which is what this did
        # first, leaves the corridor around it uncovered: a centre 30 km further
        # along that snaps 16 km back needs radius + 16, not the radius + 2 the
        # first one asked for.
        if needed > existing.radius_km:
            logger.info(
                "Two corridor centres snapped onto %s; widening its circle from "
                "r%s to r%s so it still covers both.",
                label,
                existing.radius_km,
                needed,
            )
            existing.radius_km = needed
            existing.snap_km = max(existing.snap_km, snap_km)

    for circle in circles:
        circle.url = with_location(base_url, circle.location_id, circle.radius_km)

    return RoutePlan(route, circles, radius_km, half_width_km, unresolved)


def plan_between(base_url, origin, destination, client, **kwargs):
    """Convenience wrapper: route the two points, then plan the corridor."""
    return plan(base_url, client.route([origin, destination]), **kwargs)
