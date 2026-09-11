# Plan: the results view, built for a phone

**Owner of this plan:** one agent, working only in these three files.

    frontend/src/components/RouteResultsView.tsx
    frontend/src/components/RouteCorridorMap.tsx
    frontend/src/components/CorridorPlanner.tsx

Everything else in `frontend/src` belongs to `docs/plan-visual-identity.md`,
which runs at the same time. Do not touch `App.tsx`, `index.css`, the `ui/`
primitives, or any other component — not even to fix an obvious colour. In
`i18n/translations.ts` you own the `routeResults.*` and `corridor.*` groups and
nothing else.

---

## Why

This is the screen the product exists for: what is on my route, and what does it
cost me in minutes. On a phone it currently fails at that.

Measured on the committed screenshot `logs/ui-shots-390/04-corridor-dashboard-3.png`:

| | |
|---|---|
| Page height at 390 px | **3857 px — 5.8 phone screens** |
| First listing begins at | **y ≈ 936 px** |
| Listings visible on load | **none** |

Above the first listing sit: the nav bar (64 px), a back row (48 px), the
overview card (~260 px), the filter card (~170 px, its four detour chips
wrapping onto two lines) and a 360 px map.

And the map is a trap. `RouteCorridorMap.tsx` never disables Leaflet's touch
dragging, so a thumb swiping up to reach the listings lands on the map and pans
it instead of scrolling the page. There is no way past it by swiping.

Opening **Corridor settings** makes it worse: `CorridorPlanner` renders a second
full `RouteCorridorMap` inline, so two live Leaflet instances sit within 400 px
of each other and the page grows by roughly 850 px.

---

## What to build

### 1. A segmented switch, not a stack

Below `lg` (1024 px), the results view shows **either** the list **or** the map,
never both. A segmented control sits directly under the page header:

    [ Listings (58) │ Map ]

- **List** is the default. The map must not be mounted in the DOM at all — not
  hidden with CSS. A mounted Leaflet instance still captures touches and still
  fetches tiles.
- **Map**, when chosen, fills the viewport below the header rather than sitting
  in a 360 px letterbox. A single selected listing appears as a floating card
  over the bottom of it.
- At `lg` and above, keep today's side-by-side layout. It works there.

### 2. The listing row, rebuilt around the number that matters

Today a listing is a card roughly 150 px tall whose loudest elements are badges.
The detour — the one thing this product knows that others do not — is a small
pill sharing a row with the price.

Make it a row of about 76 px:

    ┌──────┬────────────────────────────────┬──────────┐
    │      │  IKEA PAX Hosenhalter          │     +6m  │   ← detour, 18 px bold
    │ 64px │  Leutkirch im Allgäu · 1,1 km  │    20 €  │   ← price, 15 px
    └──────┴────────────────────────────────┴──────────┘

- The whole row is one tap target, opening the listing on Kleinanzeigen. Drop
  the separate 22 px external-link icon; a 76 px row is the target.
- Title: one line, clamped. Place and off-route distance beneath, muted.
- **Detour is the largest text in the row.** A listing on the route reads
  `on route`, not `+0m`.
- Keep the AI score only when one exists, and small. A listing without one must
  look complete, not unfinished.

### 3. Markers that can be told apart and tapped

62 listings cluster in a handful of towns. Each is currently a ~60 px pill, so
they overlap into an unreadable clump where a tap hits whichever of three or
four elements happens to be on top.

- Unselected: an 8 px dot.
- Selected or hovered: the full pill with its minutes.
- Cluster markers that overlap at the current zoom, showing a count.

### 4. Corridor settings as a drawer

On mobile, open `CorridorPlanner` as a full-screen overlay (`fixed inset-0`)
that locks background scrolling, rather than expanding it inline. Two live maps
on one page is never the answer. On desktop the inline card is fine.

---

## Constraints

- **No behaviour changes.** Filtering, sorting, the redraw call, detour figures
  and the AI hand-off all work; this is how they are presented.
- A listing with no AI score, no image, or no detour (`geo_status` `too_far`,
  `unplaceable`, `failed`) must render correctly. Those states exist in the data.
- Keep every user-facing string going through `useTranslation`, `de` and `en`.
- Do not reach for `slate-*` or `emerald-*` in new markup. Use the `@theme`
  tokens — `bg-base`, `bg-surface`, `border-subtle`, `text-primary`,
  `text-secondary`, `text-muted`, `brand-accent`. The other plan is removing the
  old palette everywhere else; do not add to it here.
- Minimum tap target 44 × 44 px for anything interactive.

---

## Done means

1. `./venv/bin/python scripts/ui_shots.py --width 390` produces a corridor
   dashboard where **listings are visible without scrolling**, and the page is
   under 2000 px tall with the list tab active.
2. Swiping anywhere on that page scrolls it. No element captures the gesture.
3. You have **opened the screenshots and looked at them**. This plan exists
   because the interface was built without anyone seeing it. A description of
   what the code should render is not evidence.
4. `npm run build`, `npm run lint`, `npm test` and
   `buildlock ./venv/bin/pytest scraper/ -q` are clean.
5. The screenshots at 768 px and 1440 px show no regression against
   `logs/ui-shots-768/` and `logs/ui-shots-1440/`.
