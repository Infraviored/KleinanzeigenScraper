# Plan: one visual identity, and a type scale that is actually used

**Owner of this plan:** one agent, working in everything under `frontend/src`
**except** these three files:

    frontend/src/components/RouteResultsView.tsx      ← the other plan
    frontend/src/components/RouteCorridorMap.tsx      ← the other plan
    frontend/src/components/CorridorPlanner.tsx       ← the other plan

`docs/plan-mobile-results.md` is rebuilding those at the same time. Leave them
alone entirely. In `i18n/translations.ts` the `routeResults.*` and `corridor.*`
groups belong to that plan; everything else in the file is yours.

In `index.css` you may **add** tokens. Do not rename or remove an existing one —
the other agent's new code is written against them.

---

## Why

`index.css` declares an identity: deep teal `#011F1F`, coral `#E87967`, a warm
dark ground. The components ignore it. Counted across `frontend/src`:

| | | | |
|---|---|---|---|
| `slate-*` | **173** | `border-subtle` | 112 |
| `emerald-*` | **164** | `brand-accent` | 54 |
| `rose-*` | **75** | `border-brand` | 17 |
| `indigo-*` | **34** | `brand-primary` | 5 |
| `amber-*` | 27 | `bg-base` | 1 |
| `sky-*` | 11 | | |

487 uses of a palette nobody chose, against a declared one that barely appears.
The result is not one design done badly — it is two designs wearing each other's
clothes. Cold blue-grey cards sit on a warm teal ground; a price is emerald
green in one view and coral red in another, which in Western interfaces means
*bargain* and *warning* respectively, for the same number.

The debt is unevenly spread, which makes this tractable:

    116  App.tsx              41  SettingsView.tsx
     90  ListingDetailCard    29  ScraperProgressCard
     47  GuidelinesWizard      7  PlaceInput
     44  CriteriaTuner         8  ui/{Button,Input,Select}

### And the type scale is decorative

`index.css` defines nine steps from 13 px to 40 px. Of 287 size declarations:

    text-2xs (13px)  143   ─┐
    text-xs  (14px)   86   ─┴─ 79.8% of all text
    text-sm  (15px)   27
    text-base(16px)   11
    text-lg  (19px)    8
    text-xl  (23px)    6
    text-2xl and up    6

Four fifths of the interface is set at two sizes that the eye cannot tell apart.
Hierarchy was then faked with `uppercase` (65×), `tracking-wider` (56×) and
`font-mono` (48×) — so a listing's title carries the same optical weight as the
badges around it, and scanning a list is tiring.

---

## What to do

### 1. Teal and coral win; slate and emerald go

Mechanical, and the bulk of the work:

| from | to |
|---|---|
| `bg-slate-950`, `bg-slate-900` | `bg-bg-base`, `bg-bg-surface` |
| `border-slate-800/700/600` | `border-border-subtle` |
| `text-slate-100/200` | `text-text-primary` |
| `text-slate-300/400` | `text-text-secondary` |
| `text-slate-500/600` | `text-text-muted` |

Then judge each `emerald-*` rather than replacing it blindly:

- **Status that genuinely means "good"** — on route, connected, a scrape that
  succeeded — keeps a green. Add **one** token for it (`--color-status-good`)
  and use only that. One green, one meaning.
- **Everything decorative** — glows, gradient washes, accents on things that are
  not statuses — becomes `brand-accent` or disappears.

`rose-*` (75) is mostly destructive actions and errors; give it a
`--color-status-danger` token. `indigo-*`, `sky-*` and `amber-*` have no meaning
at all — remove them.

**A price must be one colour everywhere.** Pick it, apply it in
`ListingDetailCard.tsx`, and say which it is in a comment so the other views
follow.

### 2. Fix the primitives first

`ui/Button.tsx` has variants named `action-emerald` and `mini-emerald` whose
styles were half-rewritten to coral — so `<Button variant="mini-emerald">`
renders a coral button. Rename the variants for what they *do* (`primary`,
`danger`, `quiet`, …), not for a colour, and fix every call site.

Do this before the sweep: a corrected primitive removes dozens of one-off
classes on its own.

### 3. Make the type scale carry the hierarchy

Per screen, decide what the largest thing is and let it be large:

- A **headline fact** — "58 listings along this corridor", a campaign name — at
  `text-2xl` or `text-xl`. There are zero uses of `text-2xl` today.
- **Body and titles** at `text-base` or `text-sm`, not 13 px.
- `text-2xs` is for genuine fine print, not for half the interface.

Then delete the props that were standing in for hierarchy. **Remove the
all-caps eyebrow labels entirely** — `AI-DRIVEN DEAL INTELLIGENCE`,
`CAMPAIGN HUNT PROFILE`, `TARGETS & GUIDELINES CONFIGURATION`,
`CAMPAIGN TARGET CONFIGURATION`, `DEMO RESEARCH PROMPT`. They add no
information; they are there because nothing else established rank.

Keep `font-mono` for figures that are read as figures — prices, minutes, postal
codes — and take it off prose.

### 4. Touch targets and the copy

- Icon buttons are `h-7 w-7` (28 px) with a 4 px gap. On the campaign cards that
  puts **delete one thumb-width from settings**. Minimum 44 × 44 px, and move
  destructive actions away from routine ones.
- Strip the decorative trailing arrows: `Open Dashboard →`, `Save →`,
  `Proceed to Step 2 →`. A button that looks like a button needs no arrow.
- Remove the blurred colour blobs (`blur-3xl` at 5–10 % opacity) and the
  gradient washes used as decoration.
- **`"1 Targets"`** — `App.tsx` interpolates a count against a fixed plural.
  Fix pluralisation in both languages.
- The product hunts German classifieds for German towns. `Hunt Campaigns`,
  `Campaign Hunt Profile`, `AI-Driven Deal Intelligence`, `Deep Specification &
  Risk Research` address the user as though they were running reconnaissance
  drones. Rename to what they are: *Searches*, *Criteria*, *My routes*.
  Both languages.

---

## Constraints

- **No behaviour changes.** Nothing about what the app does, only how it looks
  and what it calls things.
- Every user-facing string goes through `useTranslation` with `de` **and** `en`.
- The lint rules already reject invented Tailwind shades and hardcoded
  `text-[Npx]`. They are errors, not warnings — a build that lints clean is part
  of done.
- Never rename or remove an existing `@theme` token.

---

## Done means

1. `slate-*`, `indigo-*`, `sky-*` and `amber-*` are **zero** in `frontend/src`
   outside the three files the other plan owns. `emerald-*` and `rose-*` survive
   only behind a named status token.
2. `text-2xs` is under 30 % of size declarations, and `text-xl`/`text-2xl`
   actually appear.
3. No all-caps eyebrow labels remain. No decorative trailing arrows.
4. Every interactive element is at least 44 × 44 px.
5. You have **opened the screenshots before and after and compared them**:
   `./venv/bin/python scripts/ui_shots.py --width 390` and `--width 1440`,
   against the committed sets in `logs/ui-shots-390/` and `logs/ui-shots-1440/`.
   This plan exists because the interface was built without anyone looking at
   it. Describing the intended result is not evidence of it.
6. `npm run build`, `npm run lint`, `npm test` and
   `buildlock ./venv/bin/pytest scraper/ -q` are clean.
