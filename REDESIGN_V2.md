# ReturnIQ — Redesign v2

Visual upgrade of the ReturnIQ frontend, executed across all 14 planned
phases. **The golden rule was applied to every edit: visual layer only.**

---

## Verified untouched

Diffed byte-for-byte against the original archive:

| Area | Result |
| --- | --- |
| `backend/` (all ~90 files) | **identical** |
| ML artifacts + `data/` | **identical** |
| All 7 video assets | **identical** |
| `frontend/src/utils/api.js` | **identical** |
| `frontend/src/store/AuthContext.jsx` | **identical** |
| `infra/` | **identical** |
| Route paths in `App.jsx` | **identical** |
| Every `api.*` call across all pages | **identical** |

The landing page scroll→video scrub engine is carried over unchanged:
same `requestAnimationFrame` throttle, same `loadedmetadata` listener,
same `currentTime` math, same cleanup.

---

## Bugs found and fixed

Three pre-existing defects surfaced while reading the code. None were in
the brief; all are fixed.

1. **The landing page was unreadable.** Panels were filled
   `rgba(22,20,16,0.82)` (near-black) with `#15171B` text set on top —
   dark on dark. The hero, the stats block, the tracking panel and the
   contact form were all effectively invisible. The page now inverts
   properly: light type on the dark scrim.

2. **A malformed CSS value.** The hero vignette read
   `background: 'transparent 0%, rgba(21,23,27,0.82) 100%)'` — missing
   the `linear-gradient(` opener, so the declaration was invalid and that
   layer rendered as nothing at all.

3. **`--r-md` was never defined.** Eleven components referenced it for
   border radius. Every one silently fell back to square corners. Now
   defined in `tokens.css` as an alias of `--r`.

Two further bugs were introduced during this redesign and caught in
review before packaging: inline `display` styles were overriding the
mobile visibility classes (the drawer and hamburger would have appeared
on desktop), and the uncertainty band in the landing plot contained a
degenerate path segment.

---

## Phase log

**1 · Backup** — originals preserved in `_backup_v1/`.

**2 · Design system** — new `src/styles/`: `tokens.css`,
`typography.css`, `motion.css`, `layout.css`. `index.css` is now an entry
point that imports the four in dependency order, plus the reset.
Graphite · Bone · Vermillion · Iron · Sulphur · Ash. Cabinet Grotesk /
Switzer / Martian Mono. No gradients, no blue, no purple, no glass.

**3 · App shell** — `AppShell` composing `Sidebar` + `Topbar` + page +
`StatusBar`. The `ErrorBoundary` sits inside the page region so the
sidebar survives a page crash. Routes, auth and API untouched.

**4 · Sidebar** — same links, same icons, same routes. Heavy highlight
cards replaced with a quiet editorial list; the active marker is a 2px
Vermillion rule, not a filled box. Sections renamed for what the operator
is doing: Control room / Returns / Intelligence / Operations / Account.

**5 · Landing** — rebuilt around the intended story:
`Returns → Signal → Intelligence → Decision → Recovery`. All parcel,
warehouse, truck and shipping-company language removed. The five stages
drive the nav, the pipeline strip and the section eyebrows from a single
array, so they cannot drift apart. The video assets are kept; the looping
one is demoted to a quiet ambient band.

**6 · Components** — `Panel`, `Metric`, `MetricRow`, `MonoValue`,
`SignalBar`, `DataTable`, `Badge`, `StatusDot`, `Divider`, `Button`,
`Input`, `Select`, `Textarea`, `Checkbox`, `Tabs`. All reusable; none
page-specific. `Card`, `StatCard` and `RiskBar` are kept as thin aliases
so pages not individually restyled still render correctly.

**7 · Dashboard** — control room. Metrics sit in one ruled strip rather
than six floating cards, so a row reads as a single instrument panel.
Same APIs, same chart data.

**8 · Returns** — search, filters, pagination and API unchanged. New
table design, risk as a signal bar, a detail panel that reads
measurement → estimate. Iron marks unresolved rows; Vermillion marks the
decision.

**9 · New Return** — restructured as Input → Analysis → Decision. The
payload, validation, `createReturn` call and demo-fill helper are the
previous logic verbatim.

**10 · AI Platform** — ML API, model data and statistics unchanged.
Added a pipeline visualisation showing the five inference stages;
improved model status and performance views.

**11 · Analytics** — Recharts and data APIs unchanged. Iron = raw,
Vermillion = resolved, Ash = grid, Bone = background. No rainbow charts:
where more than two tones are needed the series steps through a
noise→signal ramp.

**12 · Workflows** — deliberately left as-is per the plan; it inherits
the new component styling.

**13 · Reports** — export logic, PDF and CSV paths untouched. New report
builder UI and filters.

**14 · Animation + responsive** — page transitions, staggered entry,
scroll reveals, hover micro-interactions. All easings decelerate; nothing
bounces, floats or loops decoratively. `prefers-reduced-motion` honoured.
Three breakpoints (1180 / 900 / 680), with the sidebar becoming an
off-canvas drawer on mobile.

---

## Running it

Nothing about setup changed.

```bash
cd frontend
npm install
npm run dev
```

Backend as before. `vite build` passes clean — 2,463 modules, no errors.

**Verification caveat:** no browser was available in the build
environment, so checking was static — production build, symbol
resolution across every import, and diffs against the original. It was
not visually confirmed in a browser. Check the landing page and dashboard
first; those changed most.

If anything looks wrong, `_backup_v1/` holds the original `Landing.jsx`,
`Dashboard.jsx`, `Sidebar.jsx`, `index.css`, `App.jsx` and the old UI kit.
