"""Parsing real result pages.

The fixtures are trimmed captures of live pages, not hand-written markup. A
hand-written fixture would only prove the parser agrees with my idea of the page,
which is exactly the assumption that broke the previous parser: it looks for
`aditem-main--top--left`, a class that no longer occurs anywhere on a current
result page.
"""

import os

import pytest

import geo
import result_list

HERE = os.path.dirname(os.path.abspath(__file__))


def fixture(name):
    with open(os.path.join(HERE, "testdata", name), encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture
def with_carousel():
    """Landsberg, 31 km, "ikea brimnes kleiderschrank": 3 hits, 13 cards."""
    return fixture("search_3_hits_plus_carousel.html")


@pytest.fixture
def empty():
    """The same search from Holzgünz, which finds nothing."""
    return fixture("search_no_hits.html")


def test_only_the_real_hits_are_returned(with_carousel):
    """The measurement this module exists for. The live page carried 13 cards for
    3 results; the fixture keeps all 3 and a sample of the carousel behind them."""
    cards_on_page = with_carousel.count('data-adid="')
    assert result_list.total_results(with_carousel) == 3
    assert cards_on_page > 3, "the fixture must contain cards past the result list"

    listings = result_list.parse(with_carousel)
    assert len(listings) == 3


def test_the_carousel_listings_are_nationwide_and_must_not_leak(with_carousel):
    """They appeared in all five circles of a 200 km corridor, which is the tell:
    they are suggestions, not radius results."""
    places = {listing["location"] for listing in result_list.parse(with_carousel)}

    assert places <= {"Landsberg (Lech)", "Bobingen"}
    assert not places & {"Mainz", "Leipzig", "Köln", "Potsdam", "Oberhausen"}


def test_each_listing_carries_what_scoring_needs(with_carousel):
    listing = result_list.parse(with_carousel)[0]

    assert listing["id"].isdigit()
    assert listing["url"].startswith("https://www.kleinanzeigen.de/s-anzeige/")
    assert "Brimnes" in listing["title"]
    assert listing["description"]
    assert listing["price_eur"] == 60
    assert listing["location"] == "Landsberg (Lech)"
    assert listing["state"] == "Bayern"


def test_prices_are_numbers_not_strings(with_carousel):
    for listing in result_list.parse(with_carousel):
        assert listing["price_eur"] is None or isinstance(listing["price_eur"], int)


def test_a_search_with_no_hits_yields_nothing(empty):
    assert result_list.parse(empty) == []
    assert result_list.total_results(empty) is None


def test_an_empty_search_is_distinguished_from_a_broken_page(empty, with_carousel):
    """Both yield zero listings; only one of them is a fault worth reporting."""
    assert result_list.is_empty_result_page(empty) is True
    assert result_list.is_empty_result_page(with_carousel) is False
    assert result_list.is_empty_result_page("<html>blocked</html>") is False


def test_a_page_with_no_list_element_is_read_as_empty_not_as_the_whole_page():
    """Falling back to scanning the document would return the carousel."""
    assert result_list.result_list_html("<html><body>nope</body></html>") == ""


def test_listing_locations_resolve_against_the_shipped_gazetteer(with_carousel):
    """Parsing and geocoding have to agree, or every detour is missing."""
    places = geo.places()

    for listing in result_list.parse(with_carousel):
        assert places.coordinates(listing["location"], listing["state"]) is not None


# --- place resolution ----------------------------------------------------


def test_qualified_town_names_the_site_prints_still_resolve():
    places = geo.places()

    assert places.coordinates("Landsberg (Lech)", "Bayern") == pytest.approx(
        (48.025, 10.851), abs=0.01
    )
    assert places.coordinates("Hofstetten a. Lech", "Bayern") is not None
    assert places.coordinates("Köln Ehrenfeld", "Nordrhein-Westfalen") is not None


def test_the_federal_state_disambiguates_repeated_town_names():
    """Salem is on Lake Constance and also near Lübeck, 600 km apart."""
    places = geo.places()

    south = places.coordinates("Salem", "Baden-Württemberg")
    north = places.coordinates("Salem", "Schleswig-Holstein")

    assert south[0] < 48 and north[0] > 53


def test_every_state_in_the_gazetteer_is_a_real_one():
    """The source table spelled 1,307 rows "Schlewig-Holstein", so every listing
    in that state resolved to nothing. Nothing caught it, because the test that
    should have used the same misspelling. This is the guard that would have."""
    import csv

    with open(
        os.path.join(HERE, "reference", "place_centroids.csv"), encoding="utf-8"
    ) as fh:
        reader = csv.reader(fh)
        next(reader)
        found = {row[1] for row in reader if len(row) > 1}

    assert found <= set(geo.FEDERAL_STATES), (
        f"not real states: {found - set(geo.FEDERAL_STATES)}"
    )
    assert found == set(geo.FEDERAL_STATES), (
        f"missing: {set(geo.FEDERAL_STATES) - found}"
    )


def test_the_location_pattern_accepts_every_state_the_gazetteer_knows():
    """Pattern and data are generated from one list, so they cannot drift."""
    for state in geo.FEDERAL_STATES:
        alt = f'alt="Ein Schrank {state} - Musterstadt Vorschau"'
        match = result_list.ALT_LOCATION_RE.search(alt)
        assert match, state
        assert match.group(1) == state
        assert match.group(2) == "Musterstadt"


def test_an_ambiguous_town_without_a_state_resolves_to_nothing():
    """A listing with no detour is honest; one with a 600 km error is not."""
    assert geo.places().coordinates("Salem") is None


# --- the repair to scraper.py --------------------------------------------


def test_the_old_selectors_find_nothing_on_a_current_page(with_carousel):
    """The reason scraper.py had to change, kept as a regression guard: if these
    ever match again the site has rolled back, and the note in the module
    docstring is no longer true."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(with_carousel, "html.parser")

    assert soup.select("ul#srchrslt-adtable li.ad-listitem") == []
    assert soup.select("article.aditem") == []
    assert soup.select(".aditem-main--top--left") == []
    # The list element itself is still there; only the class names went away.
    assert soup.select("ul#srchrslt-adtable li")


def test_scraper_shapes_listings_the_way_the_database_expects(with_carousel):
    """main.py inserts these keys by name, so the shape is a contract."""
    listing = result_list.as_db_listing(result_list.parse(with_carousel)[0])

    for key in (
        "id",
        "title",
        "price",
        "location",
        "url",
        "short_description",
        "detailed_description",
    ):
        assert key in listing, key
    assert listing["price"] == "60 €"
    assert listing["location"] == "Bayern - Landsberg (Lech)"
    assert listing["url"].startswith("https://www.kleinanzeigen.de/")


def test_the_structured_fields_travel_alongside_the_legacy_strings(with_carousel):
    """So the route corridor can geocode without re-parsing "Bayern - Ort"."""
    listing = result_list.as_db_listing(result_list.parse(with_carousel)[0])

    assert listing["price_eur"] == 60
    assert listing["place"] == "Landsberg (Lech)"
    assert listing["state"] == "Bayern"
    assert geo.places().coordinates(listing["place"], listing["state"]) is not None


def test_a_listing_without_a_price_yields_an_empty_string_not_the_word_none():
    listing = result_list.as_db_listing(
        {
            "id": "1",
            "url": "https://x/y",
            "title": "t",
            "description": None,
            "price_eur": None,
            "location": None,
            "state": None,
        }
    )

    assert listing["price"] == ""
    assert listing["location"] == ""
    assert listing["short_description"] == ""


def test_a_script_mentioning_the_list_does_not_cut_the_results_short():
    """Depth-counting `<ul>` in raw text reads tags inside scripts and comments as
    markup. This page ships a script that names the list's own selector, so the
    hazard is not hypothetical: one `</ul>` in a JS string would silently drop
    every result after it."""
    page = (
        '<html><body><ul id="srchrslt-adtable">'
        '<article data-adid="1" data-href="/a"></article>'
        '<script>var t = "</ul>"; // closes nothing</script>'
        '<article data-adid="2" data-href="/b"></article>'
        "</ul>"
        '<div><article data-adid="99" data-href="/carousel"></article></div>'
        "</body></html>"
    )

    found = [listing["id"] for listing in result_list.parse(page)]

    assert found == ["1", "2"], "the script's text is not markup"
    assert "99" not in found, "and the carousel is still outside the list"


def test_a_card_survives_its_attributes_being_reordered():
    """Requiring data-adid to sit immediately before data-href would turn a
    reordered attribute into zero listings found, silently."""
    page = (
        '<ul id="srchrslt-adtable">'
        '<article class="card" data-href="/a" data-adid="7"></article>'
        "</ul>"
    )

    found = result_list.parse(page)

    assert [listing["id"] for listing in found] == ["7"]
    assert found[0]["url"].endswith("/a")


def test_an_element_without_both_attributes_is_not_a_card():
    page = (
        '<ul id="srchrslt-adtable">'
        '<article class="promo"></article>'
        '<article data-adid="7" data-href="/a"></article>'
        "</ul>"
    )

    assert [listing["id"] for listing in result_list.parse(page)] == ["7"]
