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
    north = places.coordinates("Salem", "Schlewig-Holstein")

    assert south[0] < 48 and north[0] > 53


def test_an_ambiguous_town_without_a_state_resolves_to_nothing():
    """A listing with no detour is honest; one with a 600 km error is not."""
    assert geo.places().coordinates("Salem") is None
