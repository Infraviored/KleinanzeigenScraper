# Frontend Assessment: Why the UI Degraded and How to Stop It

## 1. The Diagnosis: It Is Not "No Framework"

The application already runs modern tools: **React 19, Tailwind v4, Vite 8, and TypeScript ~6**. The diagnosis is not "no framework" or "wrong stack." 

The frontend degraded because of two structural failures:
1. **The God-File Trap (`App.tsx` at 1,992 lines):** Without view boundaries, new features are appended inline rather than composed from primitives.
2. **Total Blindness in the Feedback Loop:** Every screen sits behind authentication. Neither agents nor automated tools could see the UI. The only feedback loop was `tsc -b` (TypeScript compilation). If code compiled, it shipped.

---

## 2. Evidenced UI Anti-Patterns

### Zombie Palettes and Hallucinated Classes
The design system in `frontend/src/index.css` defines a dark teal and coral identity (`--color-brand-primary: #011F1F`, `--color-brand-accent: #E87967`, `--color-bg-surface: #012828`). Yet the codebase is saturated with an obsolete slate and emerald palette (`slate-800`, `slate-950`, `emerald-400`, `emerald-500`, `indigo-400`, `sky-400`).

Worse, agents hallucinated nonexistent Tailwind classes that silently do nothing:
- `border-slate-855`: 6 occurrences (`PlaceInput.tsx:183`, `App.tsx:1338, 1352, 1686, 1708, 1815`).
- `text-slate-550`: 5 occurrences (`SettingsView.tsx:169, 197, 225, 270`, `ScraperProgressCard.tsx:48`).
Tailwind ignores these invalid utility classes, producing unstyled borders and text.

### Primitive Abandonment and Incomplete Primitives
Only 4 UI primitives exist in `src/components/ui/` (`Button`, `Card`, `Input`, `Select`):
- **Raw `<button>` elements bypass `Button`:** 6 in `App.tsx`, 3 in `GuidelinesWizard.tsx`, 2 in `ListingDetailCard.tsx`, 2 in `SettingsView.tsx`.
- **Primitive self-contradiction:** In `Button.tsx`, variants are named `action-emerald` and `mini-emerald`, but their CSS was partially search-and-replaced with `brand-accent` (coral) and hardcoded `#f09587`.
- **CSS specificity collisions in primitives:** `Card.tsx` concatenates class names via string template (`${baseStyle} ${interactiveStyle} ${className}`) rather than `cn()` (`tailwind-merge`). Passing custom backgrounds like `bg-slate-900/20` clashes directly with `bg-bg-surface/50` in non-deterministic cascade order.

### Uncalibrated Typography and Breakpoint Neglect
- Until commit `eb028b1`, 175 of 218 font sizes were $\le$ 12px, including 119 hardcoded pixel declarations down to 8px.
- Across 1,992 lines of `App.tsx`, there are barely 30 responsive breakpoint classes (`sm:`, `md:`, `lg:`). Whole panels (like the route corridor planner) were built assuming desktop viewports ($\ge$ 1440px), causing severe overflow and truncation on narrower screens.

---

## 3. The Split: What Machines Catch vs. What Only Eyes Catch

| Defect Category | Example from Repo | Caught By | Why / How |
| :--- | :--- | :--- | :--- |
| **Invalid Design Tokens** | `border-slate-855`, `text-slate-550` | Linter / Style rule | Static regex or ESLint rule banning unrecognized color/token patterns. |
| **Unlocalized Copy** | Hardcoded strings in JSX bypassing `useTranslation` | Linter | ESLint AST inspection (`react/jsx-no-literals` or custom rule). |
| **State & Interaction Bugs** | `PlaceInput` debounce race, stale selection, keynav | Unit test (Vitest + RTL) | Simulating user interactions, timers, and prop updates without a browser. |
| **Architectural Bloat** | `App.tsx` growing to 1,992 lines, 30+ `useState` calls | Linter / Complexity metrics | `max-lines` (warning at 500) and `complexity` limits in CI. |
| **Legibility Collapse** | 8px and 9px body text across the interface | **Eyes / Visual CI only** | Valid CSS, passes TypeScript, renders in DOM. Only a rendered screenshot exposes unreadability. |
| **Layout Truncation** | 220px combobox truncating "Landsberg am Lech" to "Landsberg ..." | **Eyes / Visual CI only** | Text fits DOM nodes; only bounding-box rendering and pixel review reveal the clipping. |
| **Color Clashing & Visual Noise** | Teal ground clashing with dark slate cards and amber badges | **Eyes / Visual CI only** | Color contrast algorithms pass WCAG AA, but the holistic palette looks discordant. |

---

## 4. Why AI Agents Specifically Fail Here

1. **Infinite Context Tolerance:** Humans experience physical and mental strain scrolling a 2,000-line file, which naturally triggers refactoring. An LLM with a 200k token window treats a 2,000-line file as easily as a 50-line file. It happily appends a 35th `useState` hook and another 100-line nested `div`.
2. **Retinal Blindness:** An agent predicts tokens based on syntax, not geometry. It cannot see that an element with `overflow-hidden` cuts off a combobox dropdown or that an 8px label is illegible on a standard monitor.
3. **Optimizing for Green Compiles:** Without visual regression tests or component unit tests, the only feedback signal was `tsc -b && vite build`. An agent will happily produce visually broken UI as long as the types check out.

The missing feedback loop is **Automated Visual Capture & Regression in CI** paired with **pre-commit lint guardrails**.

---

## 5. Deconstruction Plan for `App.tsx`

`App.tsx` should not be rewritten in a single pass while active feature work is underway. When scheduled, cut along these clean seams in this exact order:

1. **Seam 1 — Extract Route Views (`frontend/src/views/`):**
   - `LandingView.tsx` (~140 lines): Campaign cards, create card, summary statistics.
   - `DashboardView.tsx` (~215 lines): Deal Matcher listing feed, status filters, search selector, detail drawer.
   - `CampaignEditView.tsx` (~325 lines): Search URL list, fast scrape triggers, corridor planner.
   - `CreateCampaignView.tsx` (~70 lines): Initial campaign creation form.
   *(SettingsView is already extracted).*
2. **Seam 2 — Extract App Header & Navigation (`frontend/src/components/layout/Navbar.tsx`):**
   - Extract lines 1035–1240: Logo, auth indicator, login modal, language toggle, and mobile menu.
3. **Seam 3 — Extract Route Corridor Panel (`frontend/src/components/RouteCorridorPanel.tsx`):**
   - Extract the route search form (inputs, radius/corridor sliders, planning trigger) from the edit view.
4. **Seam 4 — Extract Business State into Custom Hooks (`frontend/src/hooks/`):**
   - `useCampaigns.ts`: CRUD operations and naming validation for campaigns.
   - `useListingsFeed.ts`: Listings query, status filtering, and fast scrape polling.
   - `useAuthSession.ts`: Session check, login, logout state.
