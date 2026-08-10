"""Category playbooks: what is extractable in a category, independent of any buyer.

A playbook defines the *canonical fact sheet* for a category — every fact worth
pulling out of a listing, with its type and units. It deliberately says nothing
about what a buyer wants; that lives in the buyer's intent profile and is merged
in at scoring time by `resolve_scoring_fields`.

The separation is what keeps extraction cheap. A fact sheet is extracted once per
listing and reused for every buyer, so the cost of the pipeline grows with the
size of the market rather than with the number of users. Extraction driven by a
buyer's criteria would instead cost one model call per (buyer x listing) pair.

Playbook field keys:
    id          stable identifier, referenced by intent profiles
    type        boolean | number | enum | tier | text
    label       human label, also shown to the extraction model
    description guidance for the extraction model; the place to be precise
                about units and edge cases
    unit        optional unit, appended to the extraction spec
    options     enum only: the exact allowed values
    tier_scale  tier only: what 1 and 5 mean, so the model can calibrate
"""

import re

_PLAYBOOKS = {}


def register(playbook):
    _PLAYBOOKS[playbook["key"]] = playbook
    return playbook


def get_playbook(key):
    return _PLAYBOOKS.get(key)


def all_playbooks():
    return dict(_PLAYBOOKS)


def playbook_for_category_code(code):
    """Maps a Kleinanzeigen category code (e.g. "c278") to a playbook."""
    for playbook in _PLAYBOOKS.values():
        if code in playbook.get("category_codes", ()):
            return playbook
    return None


def playbook_for_url(url):
    """Best-effort playbook lookup from a search or listing URL.

    Kleinanzeigen encodes the category as a /cNNN or /kNcNNN path segment.
    Returns None when the category is unknown, which callers must treat as
    "no canonical field set" rather than as an error.
    """
    if not url:
        return None

    # Kleinanzeigen packs the category into a path segment that is not always
    # delimited, e.g. ".../laptop/k0c278l6411" carries c278 between k0 and l6411.
    # Candidates are only accepted when a playbook claims them, so an incidental
    # match inside a slug is harmless.
    for match in re.finditer(r"c(\d+)", url):
        found = playbook_for_category_code("c" + match.group(1))
        if found:
            return found
    return None


def extraction_fields(playbook):
    """The field definitions the extraction prompt should ask for."""
    return playbook.get("fields", [])


def resolve_scoring_fields(playbook, intent_fields):
    """Merges a buyer's intent onto the playbook's canonical field definitions.

    The intent supplies importance, buyer_wants, missing_behavior and polarity;
    the playbook supplies id, type and label. Intent entries referencing an
    unknown field id are dropped, because nothing will have been extracted for
    them and a silently unscoreable field would drag every score down.

    Returns (fields, unknown_ids).
    """
    by_id = {f["id"]: f for f in playbook.get("fields", [])}
    resolved = []
    unknown = []

    for wanted in intent_fields:
        fid = wanted.get("id")
        base = by_id.get(fid)
        if base is None:
            unknown.append(fid)
            continue

        merged = {
            "id": fid,
            "type": base.get("type", "boolean"),
            "label": base.get("label", fid),
        }
        for key in ("importance", "buyer_wants", "missing_behavior", "polarity"):
            if key in wanted:
                merged[key] = wanted[key]
        resolved.append(merged)

    return resolved, unknown


# --------------------------------------------------------------------------
# Laptops. The easiest category in the market: the model name is almost a
# primary key, so most facts are spec lookups rather than judgement calls.
# --------------------------------------------------------------------------
register(
    {
        "key": "electronics/laptops",
        "version": 2,
        "label": "Laptops & Notebooks",
        "category_codes": ("c278",),
        "dossier_relevant": False,
        "vision_weight": "low",
        "geo_constraint": "soft",
        "fields": [
            {
                "id": "brand",
                "type": "text",
                "label": "Hersteller",
                "description": "Manufacturer, e.g. Apple, Lenovo, Dell.",
            },
            {
                "id": "modelName",
                "type": "text",
                "label": "Modellbezeichnung",
                "description": "Full model designation as stated, e.g. 'MacBook Pro 15 2019' or 'ThinkPad T480s'.",
            },
            {
                "id": "modelYear",
                "type": "number",
                "label": "Modelljahr",
                "unit": "Jahr",
                "description": "Model or build year as a four-digit year.",
            },
            {
                "id": "cpuModel",
                "type": "text",
                "label": "Prozessor",
                "description": "Processor as stated, e.g. 'i7-8750H', 'Ryzen 5 5600U', 'Apple M1'.",
            },
            {
                "id": "cpuTier",
                "type": "tier",
                "label": "Prozessorklasse",
                "tier_scale": "1 = Atom/Celeron or pre-2012 CPU, 3 = mid-range i5/Ryzen 5 of its generation, 5 = current i7/i9/Ryzen 7+ or Apple M-series",
                "description": "Relative performance class of the CPU, judged against today's market.",
            },
            {
                "id": "ramGb",
                "type": "number",
                "label": "Arbeitsspeicher",
                "unit": "GB",
                "description": "Total installed RAM in GB. Sum the modules if listed separately.",
            },
            {
                "id": "storageGb",
                "type": "number",
                "label": "Speicher",
                "unit": "GB",
                "description": "Primary drive capacity in GB. Convert TB to GB (1 TB = 1000 GB).",
            },
            {
                "id": "storageType",
                "type": "enum",
                "label": "Speichertyp",
                "options": ["ssd", "hdd", "hybrid"],
                "description": "Type of the primary drive.",
            },
            {
                "id": "screenInches",
                "type": "number",
                "label": "Bildschirmgröße",
                "unit": "Zoll",
                "description": "Display diagonal in inches.",
            },
            {
                "id": "conditionGrade",
                "type": "enum",
                "label": "Zustand",
                "options": ["neuwertig", "gut", "gebraucht", "defekt"],
                "description": "Overall condition. Use 'defekt' whenever any functional defect is admitted.",
            },
            {
                "id": "batteryCondition",
                "type": "text",
                "label": "Akkuzustand",
                "description": "Any statement about battery health, cycle count or runtime. Empty if not mentioned.",
            },
            {
                "id": "hasFunctionalDefect",
                "type": "boolean",
                "label": "Funktionsdefekt",
                "description": "yes only if something does not work as intended: failing battery, dead pixels, broken port, overheating, no boot. Purely cosmetic wear is NOT a functional defect.",
            },
            {
                "id": "hasCosmeticDamage",
                "type": "boolean",
                "label": "Gebrauchsspuren",
                "description": "yes if scratches, dents, worn keys or discolouration are mentioned. Appearance only, nothing that affects function.",
            },
            {
                "id": "hasCharger",
                "type": "boolean",
                "label": "Netzteil dabei",
                "description": "yes if a charger or power supply is included.",
            },
            {
                "id": "accountLocked",
                "type": "boolean",
                "label": "Konto-Sperre",
                "description": "yes if the device is stated or implied to be locked to an account (iCloud lock, Google FRP, BIOS password). This is a fraud signal.",
            },
            {
                "id": "warrantyRemaining",
                "type": "boolean",
                "label": "Restgarantie",
                "description": "yes if remaining warranty or an invoice is offered.",
            },
        ],
    }
)


# --------------------------------------------------------------------------
# Cars. The opposite extreme: identity resolves, but value is dominated by
# condition and by model-specific weaknesses that no seller volunteers. This
# playbook is deliberately the one that carries dossier fields.
# --------------------------------------------------------------------------
register(
    {
        "key": "vehicles/cars",
        "version": 1,
        "label": "Autos",
        "category_codes": ("c216",),
        "dossier_relevant": True,
        "vision_weight": "high",
        "geo_constraint": "soft",
        "fields": [
            {
                "id": "make",
                "type": "text",
                "label": "Marke",
                "description": "Manufacturer, e.g. BMW, Volkswagen.",
            },
            {
                "id": "model",
                "type": "text",
                "label": "Modell",
                "description": "Model and trim as stated, e.g. '320d Touring'.",
            },
            {
                "id": "generationCode",
                "type": "text",
                "label": "Baureihe",
                "description": "Internal series or platform code if stated, e.g. 'E90', 'Golf VII'. Empty if absent.",
            },
            {
                "id": "engineCode",
                "type": "text",
                "label": "Motorkennung",
                "description": "Engine code if stated, e.g. 'N47', 'TSI', 'TDI CR'. Empty if absent.",
            },
            {
                "id": "firstRegistrationYear",
                "type": "number",
                "label": "Erstzulassung",
                "unit": "Jahr",
                "description": "Year of first registration as a four-digit year.",
            },
            {
                "id": "mileageKm",
                "type": "number",
                "label": "Laufleistung",
                "unit": "km",
                "description": "Odometer reading in kilometres. Convert any 'tkm' notation (e.g. '190tkm' = 190000).",
            },
            {
                "id": "fuelType",
                "type": "enum",
                "label": "Kraftstoff",
                "options": ["benzin", "diesel", "hybrid", "elektro", "gas"],
                "description": "Fuel type.",
            },
            {
                "id": "transmission",
                "type": "enum",
                "label": "Getriebe",
                "options": ["manuell", "automatik"],
                "description": "Transmission type.",
            },
            {
                "id": "powerKw",
                "type": "number",
                "label": "Leistung",
                "unit": "kW",
                "description": "Engine power in kW. Convert PS to kW (1 PS = 0.7355 kW) and report kW.",
            },
            {
                "id": "tuvUntil",
                "type": "text",
                "label": "TÜV bis",
                "description": "Roadworthiness certificate validity as stated, e.g. '03/2027'. Empty if not stated.",
            },
            {
                "id": "previousOwners",
                "type": "number",
                "label": "Vorbesitzer",
                "description": "Number of previous owners.",
            },
            {
                "id": "accidentFree",
                "type": "boolean",
                "label": "Unfallfrei",
                "description": "yes only if explicitly stated accident-free. Do not infer from silence.",
            },
            {
                "id": "serviceHistoryDocumented",
                "type": "boolean",
                "label": "Scheckheft",
                "description": "yes only if a documented service history or invoices are claimed. An unbacked 'gut gepflegt' is not enough.",
            },
            {
                "id": "rustMentioned",
                "type": "boolean",
                "label": "Rost erwähnt",
                "description": "yes if rust or corrosion is mentioned anywhere, however minor.",
            },
            {
                "id": "knownDefectAddressed",
                "type": "boolean",
                "label": "Bekannte Schwachstelle behoben",
                "description": "yes if the listing states that a known weak point of this model (e.g. timing chain, DSG mechatronics, DPF) has been repaired or replaced. Dossier-driven field.",
            },
            {
                "id": "timingChainReplaced",
                "type": "boolean",
                "label": "Steuerkette erneuert",
                "description": "yes if timing chain or timing belt replacement is explicitly claimed. Dossier-driven field.",
            },
            {
                "id": "conditionGrade",
                "type": "enum",
                "label": "Zustand",
                "options": ["sehr gut", "gut", "gebraucht", "bastler"],
                "description": "Overall condition. Use 'bastler' for any car sold as a project, for parts, or as non-running.",
            },
            {
                "id": "sellerType",
                "type": "enum",
                "label": "Anbieter",
                "options": ["privat", "haendler"],
                "description": "Whether the seller presents as private or as a dealer.",
            },
        ],
    }
)


# --------------------------------------------------------------------------
# Motorcycles. Like cars, with three differences that change the field set:
# storage and maintenance matter more than odometer reading, prices swing with
# the season, and licence class is a legal hard limit rather than a preference.
# --------------------------------------------------------------------------
register(
    {
        "key": "vehicles/motorcycles",
        "version": 1,
        "label": "Motorräder & Motorroller",
        "category_codes": ("c305",),
        "dossier_relevant": True,
        "vision_weight": "high",
        "geo_constraint": "soft",
        "fields": [
            {
                "id": "make",
                "type": "text",
                "label": "Marke",
                "description": "Manufacturer, e.g. Honda, Yamaha, KTM.",
            },
            {
                "id": "model",
                "type": "text",
                "label": "Modell",
                "description": "Model designation as stated, e.g. 'MT-07', 'CB500F'.",
            },
            {
                "id": "firstRegistrationYear",
                "type": "number",
                "label": "Erstzulassung",
                "unit": "Jahr",
                "description": "Year of first registration as a four-digit year.",
            },
            {
                "id": "mileageKm",
                "type": "number",
                "label": "Laufleistung",
                "unit": "km",
                "description": "Odometer reading in kilometres.",
            },
            {
                "id": "powerKw",
                "type": "number",
                "label": "Leistung",
                "unit": "kW",
                "description": "Power in kW. Convert PS to kW (1 PS = 0.7355 kW). Decisive for licence class: A2 is capped at 35 kW.",
            },
            {
                "id": "a2Compatible",
                "type": "boolean",
                "label": "A2-tauglich",
                "description": "yes if the bike is at or below 35 kW, or is stated to be restrictable ('drosselbar') to 35 kW. This is a legal limit, not a preference.",
            },
            {
                "id": "displacementCcm",
                "type": "number",
                "label": "Hubraum",
                "unit": "ccm",
                "description": "Engine displacement in cubic centimetres.",
            },
            {
                "id": "lastServiceDocumented",
                "type": "boolean",
                "label": "Inspektion dokumentiert",
                "description": "yes only if a documented service or invoice is claimed.",
            },
            {
                "id": "storageCondition",
                "type": "enum",
                "label": "Unterstellung",
                "options": ["garage", "carport", "draussen", "unbekannt"],
                "description": "Where the bike was kept. Outdoor storage predicts corrosion more reliably than mileage does.",
            },
            {
                "id": "crashDamage",
                "type": "boolean",
                "label": "Sturzschaden",
                "description": "yes if a fall, crash or related damage is mentioned, including 'Sturzschaden nur optisch'.",
            },
            {
                "id": "tyreCondition",
                "type": "text",
                "label": "Reifenzustand",
                "description": "Any statement about tyre age, profile depth or recent replacement.",
            },
            {
                "id": "conditionGrade",
                "type": "enum",
                "label": "Zustand",
                "options": ["sehr gut", "gut", "gebraucht", "bastler"],
                "description": "Overall condition. Use 'bastler' for project bikes or non-runners.",
            },
        ],
    }
)


# --------------------------------------------------------------------------
# Smartphones. The most fungible category in the market: identity is exact,
# specs follow from the model name, and the real risks are fraud-shaped rather
# than mechanical.
# --------------------------------------------------------------------------
register(
    {
        "key": "electronics/phones",
        "version": 1,
        "label": "Handy & Telefon",
        "category_codes": ("c173",),
        "dossier_relevant": False,
        "vision_weight": "medium",
        "geo_constraint": "none",
        "fields": [
            {
                "id": "brand",
                "type": "text",
                "label": "Hersteller",
                "description": "Manufacturer, e.g. Apple, Samsung.",
            },
            {
                "id": "modelName",
                "type": "text",
                "label": "Modell",
                "description": "Full model designation, e.g. 'iPhone 13 Pro', 'Galaxy S22 Ultra'.",
            },
            {
                "id": "storageGb",
                "type": "number",
                "label": "Speicher",
                "unit": "GB",
                "description": "Internal storage in GB. Convert TB to GB.",
            },
            {
                "id": "batteryHealthPercent",
                "type": "number",
                "label": "Akkukapazität",
                "unit": "%",
                "description": "Battery health percentage if stated, e.g. from iOS battery health. Null if not mentioned.",
            },
            {
                "id": "displayCondition",
                "type": "enum",
                "label": "Displayzustand",
                "options": ["makellos", "kratzer", "riss", "defekt"],
                "description": "Screen condition. Use 'riss' for any crack, however small.",
            },
            {
                "id": "accountLocked",
                "type": "boolean",
                "label": "Konto-Sperre",
                "description": "yes if locked to an account (iCloud, Google FRP) or if activation lock is implied. Primary fraud signal in this category.",
            },
            {
                "id": "simLocked",
                "type": "boolean",
                "label": "SIM-Lock",
                "description": "yes if the device is bound to a carrier ('Netlock', 'SIM-Lock', 'nur mit Vertrag').",
            },
            {
                "id": "hasOriginalPackaging",
                "type": "boolean",
                "label": "OVP vorhanden",
                "description": "yes if original box and accessories are included.",
            },
            {
                "id": "hasInvoice",
                "type": "boolean",
                "label": "Rechnung vorhanden",
                "description": "yes if a purchase invoice is offered. Proof of legitimate ownership and a warranty basis.",
            },
            {
                "id": "repairHistory",
                "type": "text",
                "label": "Reparaturen",
                "description": "Any mention of repairs, replaced parts or third-party service. Empty if none.",
            },
            {
                "id": "conditionGrade",
                "type": "enum",
                "label": "Zustand",
                "options": ["neuwertig", "gut", "gebraucht", "defekt"],
                "description": "Overall condition. Use 'defekt' whenever any functional fault is admitted.",
            },
        ],
    }
)
