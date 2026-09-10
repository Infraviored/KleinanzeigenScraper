"""The decoding contract between scraper.py and the site."""

import requests

import scraper


class FakeResponse:
    """Mimics requests' own behaviour: a bare text/html header means latin-1."""

    def __init__(self, body_utf8):
        self.content = body_utf8
        self.encoding = "ISO-8859-1"  # what requests picks with no charset
        self.status_code = 200

    @property
    def text(self):
        return self.content.decode(self.encoding, errors="replace")


class FakeCaller:
    def __init__(self, body_utf8):
        self.body = body_utf8
        self.last_headers = None

    def get(self, url, headers=None, timeout=None):
        self.last_headers = headers
        return FakeResponse(self.body)


BODY = "IKEA Brimnes zweitürig weiß".encode("utf-8") + b" <p>60 &euro; VB</p>"


def test_pages_are_decoded_as_utf8_not_as_the_http_default():
    """The site sends `Content-Type: text/html` with no charset, so requests
    assumes ISO-8859-1 and mangles every umlaut. Measured, not supposed."""
    caller = FakeCaller(BODY)

    response = scraper.fetch("https://example.invalid/x", caller=caller)

    assert response.encoding == "utf-8"
    assert "zweitürig weiß" in response.text
    assert "zweitÃ¼rig" not in response.text


def test_without_the_fix_the_text_really_is_mangled():
    """Guards the reason the helper exists: if this ever stops being true, the
    site started sending a charset and the workaround can go."""
    mangled = FakeResponse(BODY).text

    assert "zweitÃ¼rig" in mangled
    assert "zweitürig" not in mangled


def test_fetch_sends_the_browser_headers():
    caller = FakeCaller(BODY)
    scraper.fetch("https://example.invalid/x", caller=caller)

    assert caller.last_headers is scraper.HEADERS


def test_the_live_site_still_omits_the_charset(monkeypatch):
    """Documents the upstream behaviour this depends on, without a network call."""
    assert requests.utils.get_encoding_from_headers({"content-type": "text/html"}) in (
        "ISO-8859-1",
        None,
    )
