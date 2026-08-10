# prismdeals — Produktarchitektur und Ausbauplan

Stand: 11. August 2026. Ausführliche Fassung mit Marktanalyse, Kategoriebewertung
und Fallbeispielen als Artifact:
<https://claude.ai/code/artifact/67a9de19-ccf6-496e-8067-17ac8dd27994>

---

## Das Problem

Ein Gebrauchtwarenmarkt ist ein Markt mit asymmetrischer Information. Zwischen
einer Anzeige und einer Kaufentscheidung liegen drei Lücken:

| Lücke | Inhalt | Wer schließt sie |
|---|---|---|
| Struktur | Prosa → Felder | Extraktion (Playbook) |
| Wissen | Was man über *dieses Produkt* wissen muss | Recherche (Dossier) |
| Absicht | „zuverlässiges Pendlerauto" → Kriterien | Intent-Erhebung |

Suchfilter schließen nur die erste. Der Produktwert liegt nicht im Finden,
sondern im Beurteilen.

---

## Die Konstruktionsregel

**Kein Modellaufruf darf von einem einzelnen Käufer abhängen** — einzige
Ausnahme: das Gespräch, in dem seine Absicht entsteht.

Vorher hing die Extraktion am Knowledge-Set des Käufers: N Käufer × M Anzeigen
Modellaufrufe. Jetzt: Faktenblatt einmal pro Anzeige, Scoring als reine Funktion.

Gemessen an der Kategorie Notebooks (71.373 Anzeigen, ~0,0023 € je Durchlauf):

| Szenario | Aufrufe | Kosten |
|---|---:|---:|
| gekoppelt, 1 Käufer | 71.373 | 164 € |
| gekoppelt, 100 Käufer | 7.137.300 | 16.417 € |
| entkoppelt, 100 Käufer | 71.373 | 164 € |
| entkoppelt, 10.000 Käufer | 71.373 | 164 € |

Kosten wachsen mit dem Markt, nicht mit der Nutzerzahl.

---

## Schichten

```
Adapter → Identitäts-Auflösung → Faktenblatt-Extraktion → [Faktenblatt]
                    ↑                      ↑                    ↓
              Modell-Dossier      Kategorie-Playbook         Scorer ← Kaufabsicht
                    ↑                                          ↓
              Recherche-Agent                          Ranking / Alarm
```

- **Playbook** (`scraper/playbooks.py`) — kanonisches Feldset einer Kategorie.
  Definiert, *was erhebbar ist*, nie was gewünscht ist.
- **Faktenblatt** (`scraper/fact_sheets.py`) — ein Blatt je (Anzeige, Playbook),
  versioniert über Playbook-Version, invalidiert über Textfingerprint.
- **Extraktion** (`scraper/extraction.py`) — `get_or_extract` ruft das Modell nur
  bei Cache-Miss; `score_against_intent` bewertet ohne jeden Modellaufruf.
- **Dossier** (`scraper/dossiers.py`) — Produktwissen je Modell, mit Quellenpflicht
  und typspezifischer Gültigkeit.

---

## Kategorien

**Kern** (Identität auflösbar, Beratungswert hoch): Autos, Motorräder,
Wohnwagen, E-Bikes, Laptops, Handys, Konsolen, Kameras.

**Ausbau**: Audio/HiFi, Musikinstrumente, Werkzeug, Haushaltsgeräte,
Designermöbel.

**Bewusst nicht**: Kleidung (Geschmack/Passform, Wert zu niedrig), Tickets
(kein Wissensanteil, nur Betrugsproblem), Möbel ohne Marke (vision-dominiert,
später), Tiere (ethisch/rechtlich ausgeschlossen), Immobilien und Jobs
(anderes Produkt, eigene Regulierung).

Acht Achsen entscheiden die Einordnung: kanonische Identität, Spezifikations-
Lookup, Zustandsdominanz, Risikohöhe, Foto-Verifizierbarkeit, Fungibilität,
Logistik, Preisreferenz.

---

## Phasen

| | Phase | Status |
|---|---|---|
| P0 | Fundament: kanonisches Listing, Taxonomie, Adapter-Schnittstelle | offen |
| P1 | **Extraktion von Kaufabsicht entkoppeln** | **erledigt** |
| P2 | Kategorie-Playbooks für alle Kernkategorien | 2 von 8 |
| P3 | Identitäts-Auflösung (Kategorie + Modell → Dossier-Schlüssel) | offen |
| P4 | Recherche-Agent mit Retrieval | Speicher steht, Agent offen |
| P5 | Kaufabsicht im Gespräch erheben, harte Constraints | offen |
| P6 | Preis- und Marktmodell aus Vergleichsanzeigen | offen |
| P7 | Vision (Rost, Gebrauchsspuren, Maße, Bild-Text-Abgleich) | offen |
| P8 | Alarm in Minuten, Verhandlungsentwurf aus Dossier-Lücken | offen |
| P9 | Evaluationsrahmen: Goldstandard, Regression, Kostenbudget | offen |

### P2 — offene Playbooks
Motorräder, Wohnwagen, E-Bikes, Handys, Konsolen, Kameras. Vorlage:
`playbooks.py`. Jedes Feld braucht `label` und `description`; `enum` braucht
`options`, `tier` braucht `tier_scale` — erzwungen durch
`test_every_playbook_field_is_well_formed`.

### P3 — Identitäts-Auflösung
Muss konservativ sein: lieber „nicht aufgelöst" als falsch aufgelöst, weil ein
falscher Schlüssel das falsche Dossier zieht und dann tausende Anzeigen
gleichsinnig falsch bewertet.

### P4 — Recherche-Agent
**Blocker:** ein Modell ohne Retrieval erfindet Quellen. Gemessen an
deepseek-v4-flash: alle 9 Behauptungen zum BMW N47 waren inhaltlich korrekt,
alle 9 Quellenangaben erfunden („BMW Service Bulletin #11 01 12"). Der Validator
verlangt deshalb eine abrufbare http(s)-URL. Der Agent braucht zwingend ein
Suchwerkzeug — ohne das liefert er nichts Verwertbares.

Weiter offen: URL-Erreichbarkeit tatsächlich prüfen, nicht nur die Form.

### P5 — harte Constraints
Der Scorer kennt heute nur Gewichtungen. Toms A2-Führerschein und Lenas 180-cm-
Nische sind K.-o.-Kriterien, keine Abzüge. Eigener Feldtyp nötig.

---

## Risiken

- **Plattformzugang.** Der Bot-Schutz greift nach wenigen Abrufen. Vor P6 muss
  geklärt sein, wie Zugang im nötigen Umfang legitim erfolgt.
- **Haftung.** Prüfpunkte und Belege liefern, keine Urteile fällen.
- **Dossier-Qualität.** Ein falsches Dossier ist schlimmer als keines. Quellen-
  pflicht und menschliche Freigabe der ersten Dossiers je Kategorie.
- **Kaltstart.** Zwei Kategorien vollständig statt zwölf halb.
