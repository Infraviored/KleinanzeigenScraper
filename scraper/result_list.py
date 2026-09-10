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

import geo

logger = logging.getLogger(__name__)

LIST_OPEN_RE = re.compile(r'<ul[^>]*id="srchrslt-adtable"[^>]*>')
# The two attributes anchor a card, in whichever order and however far apart the
# markup puts them: requiring `data-adid` to be immediately followed by
# `data-href` would turn a reordered attribute into zero listings found, silently
# — which is exactly the failure mode this module was written to end.
CARD_OPEN_RE = re.compile(r"<article\b[^>]*>", re.I)
ADID_RE = re.compile(r'data-adid="(\d+)"')
HREF_RE = re.compile(r'data-href="([^"]+)"')
LD_JSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
TOTAL_RE = re.compile(r"([\d.]+)\s+Ergebnisse?")

# "<title> <Bundesland> - <Ort> Vorschau" — the state name anchors the split, so
# a title that itself contains a hyphen cannot be mistaken for the location. The
# names come from geo so this pattern and the gazetteer cannot drift apart;
# longest-first, or "Sachsen" would match the start of "Sachsen-Anhalt".
ALT_LOCATION_RE = re.compile(
    r'alt="[^"]*?\b('
    + "|".join(sorted(map(re.escape, geo.FEDERAL_STATES), key=len, reverse=True))
    + r')\s*-\s*([^"]+?)\s+Vorschau"'
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

    # Counted with a parser rather than by matching `<ul>` against `</ul>` in the
    # raw text. Depth counting reads tags inside scripts, comments and attribute
    # values as real markup — and this page ships a script that mentions
    # `#srchrslt-adtable` — so one `</ul>` in a JS string would cut the list
    # short and drop every result after it, or one unclosed `<ul>` would run past
    # the end and let the whole nationwide carousel through. Both fail silently,
    # which is the failure this module exists to stop.
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(page_html, "html.parser")
    element = soup.find("ul", id="srchrslt-adtable")
    if element is None:
        # The id is in the page but not on a `<ul>` bs4 will parse — malformed
        # enough that guessing a boundary would be worse than reporting none.
        logger.warning(
            "Found the result list id in the page but could not parse the list "
            "element. Treating the page as empty rather than guessing."
        )
        return ""
    return element.decode_contents()


def total_results(page_html):
    """The count the site reports, or None."""
    match = TOTAL_RE.search(page_html)
    if not match:
        return None
    return int(match.group(1).replace(".", ""))


def _card_segments(list_html):
    """Splits the list into one chunk per card that carries an id and a link."""
    opens = [m for m in CARD_OPEN_RE.finditer(list_html)]

    cards = []
    for index, opening in enumerate(opens):
        adid = ADID_RE.search(opening.group(0))
        href = HREF_RE.search(opening.group(0))
        if not adid or not href:
            continue
        end = opens[index + 1].start() if index + 1 < len(opens) else len(list_html)
        cards.append((adid.group(1), href.group(1), list_html[opening.start() : end]))

    return cards


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


def as_db_listing(parsed):
    """Shapes a parsed card the way the listings table and the legacy code expect.

    The old parser stored `price` and `location` as the strings it scraped off the
    page ("60 €", "Bayern - Landsberg (Lech)"), and the frontend and scoring both
    read them that way. Those strings are rebuilt here rather than changing the
    schema, so repairing the parser stays a repair: the structured fields travel
    alongside under their own keys, for the code that wants numbers.
    """
    price = parsed.get("price_eur")
    location = parsed.get("location") or ""
    state = parsed.get("state")

    return {
        "id": parsed["id"],
        "title": parsed.get("title") or "",
        "price": f"{price} €" if price is not None else "",
        "short_description": parsed.get("description") or "",
        "location": f"{state} - {location}" if state and location else location,
        "url": parsed["url"],
        "detailed_description": "",
        "llm_processed": False,
        # Structured forms, for anything that would otherwise re-parse the above.
        "price_eur": price,
        "place": parsed.get("location"),
        "state": state,
    }
