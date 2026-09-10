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
import difflib
import math
import os
import re

EARTH_RADIUS_KM = 6371.0088

# The sixteen federal states, spelled as the site spells them. This is the join
# key between a listing's printed location and the gazetteer, so both sides have
# to agree exactly — and one of them was wrong: the source gazetteer spelled
# 1,307 rows "Schlewig-Holstein", which silently made every listing in that state
# unplaceable. The tuple is the single definition both sides now use, and
# `test_every_state_in_the_gazetteer_is_a_real_one` fails if the data drifts from
# it again.
FEDERAL_STATES = (
    "Baden-Württemberg",
    "Bayern",
    "Berlin",
    "Brandenburg",
    "Bremen",
    "Hamburg",
    "Hessen",
    "Mecklenburg-Vorpommern",
    "Niedersachsen",
    "Nordrhein-Westfalen",
    "Rheinland-Pfalz",
    "Saarland",
    "Sachsen",
    "Sachsen-Anhalt",
    "Schleswig-Holstein",
    "Thüringen",
)

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

    def nearest_n(self, point, count=3):
        """The `count` closest postal codes, nearest first.

        A corridor centre needs a postal code the *platform* also recognises, and
        the nearest one is not always among those. Offering the next few lets a
        caller try again instead of leaving a hole in the corridor where a single
        unrecognised village happened to be closest.
        """
        ranked = sorted(
            (
                (haversine_km(point, coords), code, coords)
                for code, coords in self._by_code.items()
            ),
            key=lambda row: row[0],
        )
        return [(code, coords, km) for km, code, coords in ranked[:count]]


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


class Place:
    """One town, as the gazetteer knows it."""

    __slots__ = ("name", "qualifier", "state", "postal_code", "coordinates")

    def __init__(self, name, qualifier, state, postal_code, coordinates):
        self.name = name
        self.qualifier = qualifier
        self.state = state
        self.postal_code = postal_code
        self.coordinates = coordinates

    @property
    def label(self):
        """What a person recognises: "86899 Landsberg a. Lech, Bayern"."""
        town = f"{self.name} {self.qualifier}".strip() if self.qualifier else self.name
        return f"{self.postal_code} {town}, {self.state}"

    def as_dict(self):
        return {
            "label": self.label,
            "name": self.name,
            "qualifier": self.qualifier,
            "state": self.state,
            "postal_code": self.postal_code,
            "lat": self.coordinates[0],
            "lon": self.coordinates[1],
        }


def _fold(text):
    """Lowercase, umlauts spelled out, punctuation dropped.

    So that "Landsberg am Lech", "landsberg a. lech" and "Landsberg a.Lech" are
    one string, and Muenchen finds München.
    """
    lowered = str(text).strip().lower()
    for source, target in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        lowered = lowered.replace(source, target)
    # "am"/"an"/"bei"/"im" are written "a."/"b."/"i." half the time; drop the
    # distinction rather than trying to guess which spelling a person used.
    for word in (
        " am ",
        " an ",
        " bei ",
        " im ",
        " a. ",
        " b. ",
        " i. ",
        " a.",
        " b.",
        " i.",
    ):
        lowered = lowered.replace(word, " ")
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", lowered).split())


class PlaceCentroids:
    """Places, looked up by name or searched by what someone typed.

    Two jobs, and they want different things. Resolving a listing's printed
    location has to be strict: "Salem" alone is a town on Lake Constance and
    another near Lübeck, and picking one would put a listing 600 km from where
    it is. Helping a person type is the opposite — offer both Salems and let
    them say which, which is why `suggest` exists and why nothing here has to
    guess.
    """

    def __init__(self, places):
        self._places = places
        self._exact = {}
        self._by_name = {}
        self._by_postal = {}
        for place in places:
            key = _fold(place.name)
            self._exact[(key, _fold(place.state))] = place
            self._by_name.setdefault(key, []).append(place)
            full = _fold(f"{place.name} {place.qualifier}")
            if full != key:
                self._exact[(full, _fold(place.state))] = place
                self._by_name.setdefault(full, []).append(place)
            self._by_postal.setdefault(place.postal_code, place)

    @classmethod
    def load(cls, path=_PLACE_PATH):
        places = []
        with open(path, encoding="utf-8") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            for record in reader:
                if len(record) < 6:
                    continue
                try:
                    places.append(
                        Place(
                            record[0],
                            record[1],
                            record[2],
                            record[3],
                            (float(record[4]), float(record[5])),
                        )
                    )
                except ValueError:
                    continue
        if not places:
            raise ValueError(f"No place centroids could be read from {path}")
        return cls(places)

    def __len__(self):
        return len(self._places)

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

    def by_postal_code(self, postal_code):
        return self._by_postal.get(str(postal_code).strip())

    def coordinates(self, name, state=None):
        """Coordinates for a printed place name, or None.

        Returns nothing rather than a guess when a bare name is ambiguous across
        states — an unplaceable listing is a listing without a detour, which is
        honest, while a confidently wrong one is a wasted drive.
        """
        if not name:
            return None

        for candidate in self._candidates(name):
            key = _fold(candidate)
            if state:
                found = self._exact.get((key, _fold(state)))
                if found:
                    return found.coordinates
            options = self._by_name.get(key)
            if options and len({p.coordinates for p in options}) == 1:
                return options[0].coordinates
        return None

    def suggest(self, query, limit=8):
        """Places matching what someone has typed so far, best first.

        Ranked rather than filtered: a prefix of the name beats a match in the
        middle of it, which beats a near-miss. Typing "Landsberg" should put
        Landsberg a. Lech at the top and still offer the other one, because the
        person is the only one who knows which they meant.
        """
        text = str(query).strip()
        if len(text) < 2:
            return []

        if text[:5].isdigit():
            found = self.by_postal_code(text[:5])
            return [found] if found else []

        needle = _fold(text)
        if not needle:
            return []

        scored = []
        for place in self._places:
            name = _fold(place.name)
            full = _fold(f"{place.name} {place.qualifier}")

            if name.startswith(needle) or full.startswith(needle):
                rank = 0
            elif needle in name or needle in full:
                rank = 1
            elif place.postal_code.startswith(text):
                rank = 2
            else:
                ratio = difflib.SequenceMatcher(None, needle, name).ratio()
                if ratio < 0.82:
                    continue
                rank = 3 - ratio  # closer misses sort ahead of looser ones

            # Among equals, the shorter name is the one that was typed.
            scored.append((rank, len(name), place.name, place))

        scored.sort(key=lambda row: row[:3])
        return [row[3] for row in scored[:limit]]


_CACHED_PLACES = None


def places():
    global _CACHED_PLACES
    if _CACHED_PLACES is None:
        _CACHED_PLACES = PlaceCentroids.load()
    return _CACHED_PLACES
