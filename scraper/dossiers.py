"""Model dossiers: product knowledge that is not in the listing.

A seller never writes that their engine has a known timing-chain weakness. That
knowledge exists publicly, but it is per *model*, not per listing — which is what
makes it affordable. One dossier is researched once and then applies to every
listing of that model, so the most expensive component in the system is also the
best amortised.

Two rules hold this together and are enforced here rather than left to prompt
wording:

1. Every claim carries a source and a date. A claim without a source is dropped,
   not softened — a model asserting engine failures from memory is a liability.
2. Claims expire on their own clock. A construction weakness is stable for years;
   a price band is stale in days. A single TTL for both would be either wasteful
   or wrong.

A dossier's payoff is `check_fields`: extra extraction fields, in the same shape
as playbook fields, that only make sense for this model. They extend the category
fact sheet for matching listings and stay buyer-independent.
"""

import datetime
import json
import logging
import re

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS dossiers (
    identity_key    TEXT PRIMARY KEY,
    category_key    TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    payload_json    TEXT NOT NULL,
    researched_at   TEXT NOT NULL,
    approved        INTEGER NOT NULL DEFAULT 0
);
"""

# How long a claim of each kind stays trustworthy.
TTL_DAYS = {
    "construction_defect": 730,
    "recall": 730,
    "maintenance_interval": 365,
    "typical_failure": 365,
    "price_band": 7,
    "market_note": 30,
}
DEFAULT_TTL_DAYS = 180

CLAIM_KINDS = tuple(TTL_DAYS)


def ensure_schema(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def identity_key(*parts):
    """Builds the stable lookup key, e.g. bmw/3er/e90/320d/n47.

    Empty parts are dropped so a partially resolved identity still yields a
    usable, if coarser, key.
    """
    cleaned = [
        str(p).strip().lower().replace(" ", "-")
        for p in parts
        if p and str(p).strip() and str(p).strip().lower() != "unknown"
    ]
    return "/".join(cleaned)


_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


def source_urls(claim):
    """The retrievable URLs among a claim's sources."""
    found = []
    for source in claim.get("sources") or []:
        if isinstance(source, str):
            found.extend(_URL_RE.findall(source))
    return found


def validate_claim(claim):
    """Returns (ok, reason). Enforces the sourcing rule.

    A source must be a URL somebody can open. This is stricter than it looks
    necessary, and deliberately so: a model without retrieval will happily emit
    citation-shaped strings like "BMW Service Bulletin #11 01 12" or
    "SomeForum - timing chain thread" that are entirely invented. Measured against
    deepseek-v4-flash without tools, every one of nine claims carried such a
    source and an existence check on the string alone accepted all of them. Only
    requiring a retrievable URL separates researched claims from remembered ones.
    """
    if not isinstance(claim, dict):
        return False, "claim is not an object"
    if not claim.get("statement"):
        return False, "claim has no statement"
    if claim.get("kind") not in CLAIM_KINDS:
        return False, f"claim kind {claim.get('kind')!r} is not recognised"

    sources = claim.get("sources") or []
    if not sources:
        return False, "claim has no sources"
    if not source_urls(claim):
        return False, "claim has no retrievable source URL"
    return True, ""


def default_url_checker(timeout=8):
    """Returns a callable that reports whether a URL actually resolves.

    Checking the shape of a URL is not the same as checking that it exists: a
    model that invents "https://www.motor-talk.de/forum/n47-t9999999.html" clears
    every syntactic test. Network failures are treated as "unknown" rather than
    "dead", so a flaky connection does not silently strip a good dossier.
    """
    import requests

    session = requests.Session()

    def check(url):
        try:
            response = session.head(
                url, timeout=timeout, allow_redirects=True, headers=BROWSER_HEADERS
            )
            if response.status_code >= 400:
                # Some hosts reject HEAD but serve GET.
                response = session.get(
                    url, timeout=timeout, allow_redirects=True, headers=BROWSER_HEADERS
                )
            return classify_status(response.status_code)
        except Exception as exc:
            logger.info("Could not verify %s (%s); treating as unknown.", url, exc)
            return None

    return check


# Only an explicit "this resource does not exist" counts as dead. Measured
# against motor-talk.de, whose real homepage answers 403 to a plain client: bot
# protection, a rate limit or an outage would otherwise strip legitimate forum
# sources, which are exactly where used-vehicle knowledge lives.
DEAD_STATUSES = frozenset({404, 410})

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


def classify_status(status_code):
    """True = resolves, False = definitively gone, None = could not be determined."""
    if status_code < 400:
        return True
    if status_code in DEAD_STATUSES:
        return False
    return None


def verify_sources(payload, url_checker):
    """Drops claims whose every source URL is confirmed dead.

    A claim survives if at least one source resolves, or if none could be checked
    — the aim is to remove inventions, not to punish an unreachable network.
    Returns (payload, removed).
    """
    kept, removed = [], []

    for claim in payload.get("claims", []):
        urls = source_urls(claim)
        results = [url_checker(url) for url in urls]

        if any(result is True for result in results):
            kept.append(claim)
        elif all(result is False for result in results) and results:
            removed.append({"claim": claim, "reason": "no source URL resolves"})
            logger.warning(
                "Dropping claim %r: none of its %d source URL(s) resolve.",
                (claim.get("statement") or "")[:60],
                len(urls),
            )
        else:
            # Inconclusive: keep, but say so rather than pretending it is verified.
            claim = dict(claim, sources_unverified=True)
            kept.append(claim)

    cleaned = dict(payload)
    cleaned["claims"] = kept
    return cleaned, removed


def sanitize(payload):
    """Drops unsourced or malformed claims. Returns (payload, dropped).

    Dropping rather than downgrading is deliberate: a claim we cannot attribute
    should not influence thousands of listings at any weight.
    """
    claims = payload.get("claims") or []
    kept, dropped = [], []

    for claim in claims:
        ok, reason = validate_claim(claim)
        if ok:
            kept.append(claim)
        else:
            dropped.append({"claim": claim, "reason": reason})
            logger.warning("Dropping dossier claim: %s", reason)

    cleaned = dict(payload)
    cleaned["claims"] = kept
    return cleaned, dropped


def claim_is_fresh(claim, researched_at, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if isinstance(researched_at, str):
        try:
            researched_at = datetime.datetime.fromisoformat(researched_at)
        except ValueError:
            return False
    if researched_at.tzinfo is None:
        researched_at = researched_at.replace(tzinfo=datetime.timezone.utc)

    ttl = TTL_DAYS.get(claim.get("kind"), DEFAULT_TTL_DAYS)
    return (now - researched_at).days <= ttl


def fresh_claims(payload, researched_at, now=None):
    return [
        c
        for c in payload.get("claims", [])
        if claim_is_fresh(c, researched_at, now=now)
    ]


def check_fields(payload):
    """Extraction fields contributed by this dossier.

    Shaped exactly like playbook fields so they can be concatenated onto the
    category field set without any special handling downstream.
    """
    return payload.get("check_fields", [])


def get(conn, key, require_approved=False):
    row = conn.execute(
        "SELECT payload_json, version, researched_at, approved FROM dossiers "
        "WHERE identity_key = ?",
        (key,),
    ).fetchone()
    if not row:
        return None
    if require_approved and not row[3]:
        logger.info("Dossier %s exists but is not approved; ignoring.", key)
        return None
    try:
        payload = json.loads(row[0])
    except (ValueError, TypeError):
        logger.warning("Corrupt dossier payload for %s", key)
        return None
    return {
        "payload": payload,
        "version": row[1],
        "researched_at": row[2],
        "approved": bool(row[3]),
    }


def put(conn, key, category_key, payload, approved=False, version=1):
    cleaned, dropped = sanitize(payload)
    conn.execute(
        "INSERT INTO dossiers "
        "(identity_key, category_key, version, payload_json, researched_at, approved) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(identity_key) DO UPDATE SET "
        "category_key = excluded.category_key, "
        "version = excluded.version, "
        "payload_json = excluded.payload_json, "
        "researched_at = excluded.researched_at, "
        "approved = excluded.approved",
        (
            key,
            category_key,
            version,
            json.dumps(cleaned, ensure_ascii=False),
            datetime.datetime.now(datetime.timezone.utc).isoformat(),
            1 if approved else 0,
        ),
    )
    conn.commit()
    return cleaned, dropped


RESEARCH_PROMPT = """You are a used-goods research analyst. Research the product below \
and produce a dossier a prospective buyer could not assemble themselves.

PRODUCT
{identity}

CATEGORY
{category}

Every claim must carry at least one full retrievable URL that you actually \
consulted, starting with http:// or https://. A publication name, forum name, \
or bulletin number without a URL is not a source and the claim will be discarded. \
If you cannot supply a URL, omit the claim entirely — an unsourced claim is worse \
than a missing one, because it will be applied to thousands of listings.

Do not reconstruct sources from memory. If you have no retrieval tool available, \
return an empty claims array rather than plausible-looking citations.

Concentrate on what a seller would not volunteer:
- known construction weaknesses and the mileage or age at which they appear
- manufacturer recalls and goodwill programmes
- maintenance that is due at a predictable point and is expensive when skipped
- what distinguishes a well-kept example from a neglected one in this model

Then derive the checks a buyer should apply to a listing. Each check must be \
answerable from a listing text alone.

Return JSON only, between START_JSON and END_JSON:

START_JSON
{{
  "summary": "two sentences on what decides a good example of this model",
  "claims": [
    {{
      "kind": "construction_defect | recall | maintenance_interval | typical_failure | price_band | market_note",
      "statement": "specific, checkable statement",
      "detail": "mileage, years, or figures where applicable",
      "sources": ["url or named publication"]
    }}
  ],
  "check_fields": [
    {{
      "id": "camelCaseId",
      "type": "boolean | number | enum | tier | text",
      "label": "short German label",
      "description": "what the extraction model should look for in the listing",
      "options": ["only for enum"],
      "rationale": "which claim this check follows from"
    }}
  ]
}}
END_JSON"""


def build_research_prompt(identity, category_label):
    return RESEARCH_PROMPT.format(identity=identity, category=category_label)


def get_or_research(
    conn,
    key,
    identity,
    category_key,
    category_label,
    research_fn,
    require_approved=False,
    force=False,
):
    """Returns (payload, from_cache) or (None, False) when research yields nothing.

    Research runs asynchronously in production and must never sit in a user's
    request path; this function is the worker-side entry point.
    """
    if not force:
        existing = get(conn, key, require_approved=require_approved)
        if existing:
            return existing["payload"], True

    prompt = build_research_prompt(identity, category_label)
    payload = research_fn(prompt)
    if not payload:
        logger.warning("Research produced no dossier for %s", key)
        return None, False

    cleaned, dropped = put(conn, key, category_key, payload)
    if dropped:
        logger.info(
            "Dossier %s: %d claim(s) dropped for missing sources", key, len(dropped)
        )
    return cleaned, False
