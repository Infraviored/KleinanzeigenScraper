"""Reading a search result page.

There is no open search API. The mobile endpoint at api.kleinanzeigen.de answers
401, the page carries no embedded state (`astroSharedData` holds an empty session
object), and the only public JSON services are helpers such as location
suggestions. So the result list is read from HTML — not by preference, but
because nothing else is on offer.

That makes *where* the reading is anchored the whole question. The site has moved
to utility CSS, and class names like `aditem-main--top--left` — which the older
parser in `scraper.py` still looks for — no longer exist anywhere on a current
page. Anchoring on appearance means re-breaking on every redesign.

This module anchors on meaning instead: `data-adid` and `data-href`, which carry
identity, and the per-card JSON-LD block, which carries the title and description
as data. Both survive restyling.

The other thing HTML forces us to get right is the boundary of the list. A search
with three hits renders thirteen cards: the three results, then a "more listings"
carousel of nationwide suggestions. Measured on a Landsberg search for a Brimnes
wardrobe, those extras came from Mainz, Leipzig, Cologne and Potsdam and appeared
in all five circles of a route corridor — they are not radius results at all.
`<ul id="srchrslt-adtable">` closes right after the genuine hits, so the boundary
is exact, and everything past it is dropped.
"""

import html as html_module
import json
import logging
import re

logger = logging.getLogger(__name__)

LIST_OPEN_RE = re.compile(r'<ul[^>]*id="srchrslt-adtable"[^>]*>')
CARD_RE = re.compile(r'data-adid="(\d+)"\s+data-href="([^"]+)"')
LD_JSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
TOTAL_RE = re.compile(r"([\d.]+)\s+Ergebnisse?")

# "<title> <Bundesland> - <Ort> Vorschau" — the state name anchors the split, so
# a title that itself contains a hyphen cannot be mistaken for the location.
ALT_LOCATION_RE = re.compile(
    r'alt="[^"]*?\b('
    r"Baden-Württemberg|Bayern|Berlin|Brandenburg|Bremen|Hamburg|Hessen|"
    r"Mecklenburg-Vorpommern|Niedersachsen|Nordrhein-Westfalen|Rheinland-Pfalz|"
    r"Saarland|Sachsen-Anhalt|Sachsen|Schleswig-Holstein|Thüringen"
    r')\s*-\s*([^"]+?)\s+Vorschau"'
)
PRICE_RE = re.compile(r">\s*([\d.]+)\s*€(\s*VB)?\s*<")


EMPTY_RE = re.compile(
    r"Es wurden keine Ergebnisse|leider keine Ergebnisse", re.IGNORECASE
)


def is_empty_result_page(page_html):
    """Whether the page states outright that the search found nothing.

    A search with no hits renders no result list at all, which is otherwise
    indistinguishable from a page that failed to load or was blocked. Both then
    yield zero listings, and reporting them the same way hides a real fault
    behind an ordinary one — so the page's own wording decides which it is.
    """
    return bool(EMPTY_RE.search(page_html))


def result_list_html(page_html):
    """The genuine result list, with the suggestion carousel cut off.

    Returns an empty string when the list element is absent — a blocked page or a
    changed layout should read as "no results found here", never as the whole
    page's worth of unrelated cards.
    """
    opening = LIST_OPEN_RE.search(page_html)
    if not opening:
        if not is_empty_result_page(page_html):
            logger.warning(
                "No result list on this page, and it does not say the search was "
                "empty. The layout may have changed, or the request was blocked."
            )
        return ""

    start = opening.end()
    depth = 1
    for token in re.finditer(r"<(/?)ul\b", page_html[start:]):
        depth += -1 if token.group(1) else 1
        if depth == 0:
            return page_html[start : start + token.start()]

    logger.warning("Result list is not closed; reading to the end of the page.")
    return page_html[start:]


def total_results(page_html):
    """The count the site reports, or None."""
    match = TOTAL_RE.search(page_html)
    if not match:
        return None
    return int(match.group(1).replace(".", ""))


def _card_segments(list_html):
    """Splits the list into one chunk per card."""
    positions = [
        (m.start(), m.group(1), m.group(2)) for m in CARD_RE.finditer(list_html)
    ]
    for index, (start, adid, href) in enumerate(positions):
        end = positions[index + 1][0] if index + 1 < len(positions) else len(list_html)
        yield adid, href, list_html[start:end]


def _title_and_description(segment):
    """From the card's JSON-LD, which holds them as data rather than markup."""
    for raw in LD_JSON_RE.findall(segment):
        try:
            block = json.loads(raw)
        except ValueError:
            continue
        if block.get("title"):
            return block.get("title"), block.get("description")
    return None, None


def parse(page_html):
    """Listings from one result page, excluding the suggestion carousel."""
    listings = []
    for adid, href, segment in _card_segments(result_list_html(page_html)):
        title, description = _title_and_description(segment)

        location, state = None, None
        match = ALT_LOCATION_RE.search(segment)
        if match:
            state, location = (
                match.group(1),
                html_module.unescape(match.group(2)).strip(),
            )

        price = None
        price_match = PRICE_RE.search(segment)
        if price_match:
            price = int(price_match.group(1).replace(".", ""))

        listings.append(
            {
                "id": adid,
                "url": "https://www.kleinanzeigen.de" + href,
                "title": title,
                "description": description,
                "price_eur": price,
                "location": location,
                "state": state,
            }
        )
    return listings
