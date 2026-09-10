"""Coordinates, distances and postal-code centroids.

Everything spatial in this project reduces to three questions: how far apart are
two points, which postal code is nearest to a point, and where does a postal code
sit. All three are answered from a shipped table rather than a geocoding service.

That choice is deliberate. A corridor search resolves dozens of points per route,
and a per-point network geocode would be slow, rate-limited, and — worse —
non-deterministic: the same route would produce different circles on different
days, so a cached search URL could no longer be trusted to mean what it meant
yesterday. A local table costs 245 KB and makes the geometry reproducible.

Postal-code centroids are precise to roughly the size of a postal district, a few
kilometres in the country and a few hundred metres in a city. That is well inside
the error a search radius already carries, so nothing downstream needs better.
"""

import csv
import math
import os
import re

EARTH_RADIUS_KM = 6371.0088

CENTROID_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "reference", "plz_centroids.csv"
)


def haversine_km(a, b):
    """Great-circle distance between two (lat, lon) pairs, in kilometres."""
    lat1, lon1 = a
    lat2, lon2 = b
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)

    h = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def interpolate(a, b, fraction):
    """Point at `fraction` of the way from a to b.

    Linear in lat/lon rather than a true great-circle interpolation: over the
    few tens of kilometres between two route vertices the difference is far
    below the precision of a postal centroid.
    """
    return (
        a[0] + (b[0] - a[0]) * fraction,
        a[1] + (b[1] - a[1]) * fraction,
    )


class PostalCentroids:
    """Postal code -> centroid, and the reverse lookup by nearest centroid.

    The reverse lookup is a linear scan over ~8,300 rows. That is a few
    milliseconds and is called a handful of times per route; an index would be
    more code than the problem deserves.
    """

    def __init__(self, rows):
        self._by_code = dict(rows)

    @classmethod
    def load(cls, path=CENTROID_PATH):
        rows = []
        with open(path, encoding="utf-8") as handle:
            reader = csv.reader(handle)
            next(reader, None)  # header: "", lat, lng
            for record in reader:
                if len(record) < 3:
                    continue
                code = record[0].strip()
                try:
                    rows.append((code, (float(record[1]), float(record[2]))))
                except ValueError:
                    continue
        if not rows:
            raise ValueError(f"No postal centroids could be read from {path}")
        return cls(rows)

    def __len__(self):
        return len(self._by_code)

    def __contains__(self, code):
        return str(code).strip() in self._by_code

    def coordinates(self, code):
        """Centroid of a postal code, or None if it is not in the table."""
        return self._by_code.get(str(code).strip())

    def nearest(self, point):
        """Returns (postal_code, coordinates, distance_km) closest to `point`."""
        best_code, best_coords, best_km = None, None, float("inf")
        for code, coords in self._by_code.items():
            km = haversine_km(point, coords)
            if km < best_km:
                best_code, best_coords, best_km = code, coords, km
        return best_code, best_coords, best_km


_CACHED = None


def centroids():
    """Process-wide singleton, so the table is parsed once."""
    global _CACHED
    if _CACHED is None:
        _CACHED = PostalCentroids.load()
    return _CACHED


# Listings name a town, not a postal code: "Bayern - Landsberg (Lech)". Turning
# that into coordinates needs a second table, and the same reasons apply — it is
# shipped rather than queried, so the same listing always lands in the same place.

_PLACE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "reference", "place_centroids.csv"
)

# Suffixes the site prints that the gazetteer does not carry: district names,
# river qualifiers, "b." for bei. "Landsberg (Lech)" and "Hofstetten a. Lech"
# both have to reach the plain town.
_QUALIFIER_RE = re.compile(r"\s*(\(.*\)|\b(a\.|b\.|am|an|bei|im|i\.|OT)\b.*)$", re.I)


class PlaceCentroids:
    """Town name (optionally with federal state) -> coordinates.

    The state matters more than it looks: Landsberg is a town in Bavaria and
    another in Saxony-Anhalt, 400 km apart, and Salem sits both on Lake Constance
    and near Lübeck. Resolving without the state would put listings on the wrong
    side of the country and hand them an absurd detour.
    """

    def __init__(self, rows):
        self._exact = {}
        self._by_name = {}
        for name, state, coords in rows:
            self._exact[(name.lower(), state.lower())] = coords
            self._by_name.setdefault(name.lower(), []).append(coords)

    @classmethod
    def load(cls, path=_PLACE_PATH):
        rows = []
        with open(path, encoding="utf-8") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            for record in reader:
                if len(record) < 4:
                    continue
                try:
                    rows.append(
                        (record[0], record[1], (float(record[2]), float(record[3])))
                    )
                except ValueError:
                    continue
        if not rows:
            raise ValueError(f"No place centroids could be read from {path}")
        return cls(rows)

    def __len__(self):
        return len(self._by_name)

    def _candidates(self, name):
        """Progressively coarser readings of a printed place name."""
        cleaned = name.strip()
        yield cleaned
        without_qualifier = _QUALIFIER_RE.sub("", cleaned).strip()
        if without_qualifier and without_qualifier != cleaned:
            yield without_qualifier
        # "Köln Ehrenfeld" is a district of a town the gazetteer does know.
        head = without_qualifier.split()[0] if without_qualifier.split() else ""
        if head and head != without_qualifier:
            yield head

    def coordinates(self, name, state=None):
        """Coordinates for a printed place name, or None.

        Returns nothing rather than a guess when a bare name is ambiguous across
        states — an unplaceable listing is a listing without a detour, which is
        honest, while a confidently wrong one is a wasted drive.
        """
        if not name:
            return None

        for candidate in self._candidates(name):
            key = candidate.lower()
            if state:
                found = self._exact.get((key, state.strip().lower()))
                if found:
                    return found
            options = self._by_name.get(key)
            if options and len(options) == 1:
                return options[0]
        return None


_CACHED_PLACES = None


def places():
    global _CACHED_PLACES
    if _CACHED_PLACES is None:
        _CACHED_PLACES = PlaceCentroids.load()
    return _CACHED_PLACES
