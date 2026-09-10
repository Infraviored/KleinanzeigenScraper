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

Produktiv verdrahtet in `main.py --mode process` über `scraper/pipeline.py`.
Kategorien ohne Playbook fallen unverändert auf den Legacy-Worker zurück.

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
| P2 | Kategorie-Playbooks für alle Kernkategorien | 4 von 8 |
| P3 | Identitäts-Auflösung (Kategorie + Modell → Dossier-Schlüssel) | **erledigt** |
| P4 | Recherche-Agent mit Retrieval | Speicher steht, Agent offen |
| P5 | Kaufabsicht im Gespräch erheben, harte Constraints | Constraints erledigt, Gespräch offen |
| P6 | Preis- und Marktmodell aus Vergleichsanzeigen | offen |
| P7 | Vision (Rost, Gebrauchsspuren, Maße, Bild-Text-Abgleich) | offen |
| P8 | Alarm in Minuten, Verhandlungsentwurf aus Dossier-Lücken | offen |
| P9 | Evaluationsrahmen: Goldstandard, Regression, Kostenbudget | offen |
| P10 | **Korridorsuche entlang einer Route, Rang nach Umweg** | **erledigt** |

### P2 — offene Playbooks
Fertig: Laptops (v2), Autos, Motorräder, Handys.
Offen: Wohnwagen, E-Bikes, Konsolen, Kameras. Vorlage:
`playbooks.py`. Jedes Feld braucht `label` und `description`; `enum` braucht
`options`, `tier` braucht `tier_scale` — erzwungen durch
`test_every_playbook_field_is_well_formed`.

### P3 — Identitäts-Auflösung
`scraper/identity.py`. Läuft nach der Extraktion, nicht auf dem Titel — Marke,
Modell und Motorkennung sind dann bereits getrennte Felder, es bleibt reine
Normalisierung. Verweigert die Auflösung bei fehlendem Pflichtteil: lieber
„nicht aufgelöst" als falsch aufgelöst.

### P4 — Recherche-Agent
**Blocker:** ein Modell ohne Retrieval erfindet Quellen. Gemessen an
deepseek-v4-flash: alle 9 Behauptungen zum BMW N47 waren inhaltlich korrekt,
alle 9 Quellenangaben erfunden („BMW Service Bulletin #11 01 12"). Der Validator
verlangt deshalb eine abrufbare http(s)-URL. Der Agent braucht zwingend ein
Suchwerkzeug — ohne das liefert er nichts Verwertbares.

`verify_sources` prüft die Erreichbarkeit inzwischen tatsächlich. Zwei
bewusste Asymmetrien: eine Behauptung überlebt, wenn *eine* Quelle auflöst oder
keine prüfbar war (unbestätigte werden als `sources_unverified` markiert), und
nur 404/410 gelten als tot — 403 ist Bot-Schutz, kein toter Link. Ohne diese
Unterscheidung hätte die echte motor-talk-Startseite als tot gegolten.

Weiter offen: der Agent selbst. Er braucht ein Suchwerkzeug.

### P5 — harte Constraints (erledigt) und Gesprächs-Intent (offen)
Intent-Felder mit `"hard": true` setzen den Score auf 0. Verletzung und
fehlender Wert werden getrennt: eine angegebene Überschreitung schließt aus,
Schweigen des Verkäufers landet in `unverified_constraints` und ist eine
Rückfrage wert.

Offen: die Kaufabsicht im Gespräch erheben. Bis dahin erzeugt
`scripts/make_intent.py` ein editierbares Startprofil aus einem Playbook.

### P10 — Korridorsuche entlang einer Route
Eine Plattformsuche hängt an einem Ort, eine Fahrt ist eine Linie. Die
verbindende Größe ist nicht die Entfernung, sondern der Umweg:
`Fahrt(A→Anzeige→B) − Fahrt(A→B)`.

Gemessen Landsberg am Lech → Konstanz: ein Schrank in Salem liegt 15,6 km von
der Route und 74 km per Straße — die Strecke läuft am Südufer des Bodensees,
Salem am Nordufer. Ein Radiusfilter nennt das nah und kostet 2,5 Stunden.

Den Korridor überdecken statt die Route abtasten: aus Radius `r` und Halbbreite
`w` folgt `d = 2·√(r²−w²)`, der Punkt mittig zwischen zwei Kreisen am
Korridorrand liegt dann exakt auf beiden. Für diese Route: **5 Suchen statt 14**
— gegen einen Bot-Schutz, der nach einer Handvoll Abrufe greift, ist das die
eigentliche Währung.

Drei Messungen tragen die Umsetzung:
- Der Radius in der URL ist frei wählbar, nicht auf die Dropdown-Werte
  beschränkt (`r17` wird so bereitwillig geliefert wie `r25`). Deshalb kann
  jeder Kreis seine eigene Einrast-Verschiebung bezahlen — pro Kreis, denn der
  Mittelpunkt bei Lindau landet im Bodensee und schnappt 12 km.
- Nur das Endsegment `k…c…l…r…` entscheidet, was gesucht wird; der lesbare Pfad
  ist Dekoration.
- Es gibt **keine offene Such-API** (`api.kleinanzeigen.de` → 401, kein
  eingebetteter State), also HTML — verankert an `data-adid` und JSON-LD statt
  an CSS-Klassen.

Eine Routensuche ist N gewöhnliche Suchen mit einem Knowledge-Set. Planung und
Umweg-Berechnung sind getrennt, damit der Routing-Dienst nie im Pfad des
Scrapers liegt.

**Offen:** Darstellung im Frontend. Die Karte existiert bisher nur als
Artifact: <https://claude.ai/code/artifact/03e86861-1899-4194-8442-a320092913e4>

---

## Risiken

- **Parser-Bruch.** Die Trefferliste hing an CSS-Klassen und brach beim
  Tailwind-Umbau still: `.aditem-main--top--left` kommt auf einer aktuellen
  Seite null Mal vor. Dazu kam eine falsche Zeichenkodierung — die Seite sendet
  `text/html` ohne charset, HTTP-Standard ist dann latin-1, die Seite ist UTF-8.
  Beides lief lange unbemerkt, weil kein Test gegen eine echte Seite prüfte.
  Deshalb liegen jetzt getrimmte Live-Seiten als Fixtures im Repo.
- **Plattformzugang.** Der Bot-Schutz greift nach wenigen Abrufen. Vor P6 muss
  geklärt sein, wie Zugang im nötigen Umfang legitim erfolgt.
- **Haftung.** Prüfpunkte und Belege liefern, keine Urteile fällen.
- **Dossier-Qualität.** Ein falsches Dossier ist schlimmer als keines. Quellen-
  pflicht und menschliche Freigabe der ersten Dossiers je Kategorie.
- **Kaltstart.** Zwei Kategorien vollständig statt zwölf halb.
