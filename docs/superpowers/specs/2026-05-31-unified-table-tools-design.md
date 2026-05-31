# Unified Table Tools: client-side sort & filter across all tables

**Date:** 2026-05-31
**Status:** Approved (design)
**Author:** brainstorming session

## Problem

The dashboard renders tables on ~22 templates (orchestration runs, findings,
ideas, plans, tech-debt, topics, notes, evolutions, contracts, sessions, AI-usage
summaries, …). Only **one** of them — `project_findings.html` — has interactive
sorting and filtering. Everything else renders a static `<table>` with a
server-fixed order and no way to narrow rows in the UI.

The user wants **sorting and filtering on every table**, delivered through a
**single reusable mechanism** rather than copy-pasted per page.

## What already exists (verified)

`project_findings.html` contains a complete, polished **client-side** sort + filter
implementation, inlined as bespoke `<script>`/`<style>` in that one file:

- Sortable headers (`.td-th-sort`, `data-col`, `data-type`) — click toggles
  asc/desc with an indicator. A custom `prio` comparator ranks
  `critical > high > medium > low`.
- A per-column **filter row** (`data-td-filter`): text inputs match as substrings,
  `<select>`s match exactly, plus a special "refs" predicate over derived
  `data-has-gh` / `data-has-run` / `data-has-jira` row attributes.
- `localStorage` persistence keyed per project, a "shown N of M" counter, an
  empty-state message, and a `bulk:rows-changed` event that the bulk-selection
  script listens to.

This is effectively a reference implementation. The work is to **extract it into a
reusable component and roll it out**, not to invent it.

Other relevant facts:

- The full sort/filter machinery is inlined (under different attribute names) in
  **three** templates: `project_findings.html` (`data-td-*`),
  `project_ideas.html` (`data-ideas-*`), and `project_evolutions.html`
  (`data-evo-*`). All three must be converted to the component and have their
  inline JS deleted — a bare `data-table-tools` opt-in on these would run two
  implementations concurrently.
- The `bulk:rows-changed` event therefore has **three** existing consumers
  (findings, ideas, evolutions). The component re-emits it for back-compat; the
  alias may only be removed once all three are migrated.
- Server-side filtering exists only on `project_findings.py` and
  `project_ideas.py` (`selected_status` / `selected_module` query params).
- Several routes cap rows server-side: `project_orchestration.py`
  (`list_runs(limit=50)`), plus session-log, dashboard, kanban, cascade-costs,
  questions, ai-radar. A purely client-side enhancer can only sort/filter rows
  already present on the page — this is where the "hybrid" requirement applies.
- Table markup is **inconsistent** across templates (`.data-table`, ad-hoc
  Tailwind, custom cells containing forms/buttons/links). A generic
  "render the whole table from data" macro would fight this; an enhancer that
  decorates existing markup does not.

## Decisions (from brainstorming)

- **Scope:** all tables, one unified mechanism.
- **Approach:** reusable data-attribute **enhancer** (chosen over a Jinja
  render-table macro and over a third-party grid library).
- **Behaviour:** hybrid — client-side by default; server-side `?sort=&q=` added
  only point-wise where a table is genuinely large/paginated (deferred, not first
  wave).
- **Coverage:** literally every table, including small summary/KPI tables. Trivial
  tables get the minimum treatment (sortable headers + one global search box);
  rich list tables get the full per-column filter row.

## Architecture

### Component: `dreaming/static/table_tools.js` + `table_tools.css`

A single static module, loaded globally from the base layout, that
**auto-initializes** on `DOMContentLoaded` over every `table[data-table-tools]`.
Initialization is idempotent (guarded so double-loading is safe).

```html
<table data-table-tools data-tt-key="findings.{{ project.slug }}">
```

- `data-tt-key` — optional `localStorage` key for persisting sort + filter state.
  Omit it to disable persistence (appropriate for trivial tables).

#### Sorting

Mark headers:

```html
<th data-sort-col="title" data-sort-type="text">Title</th>
```

- Types: `text` (`localeCompare`), `num` (`parseFloat`), `date` (ISO strings,
  compared lexicographically — `YYYY-MM-DD` sorts correctly), `prio`
  (`critical>high>medium>low`), `status` (custom rank). Default `text`.
  Note: `date` sorting is only correct over ISO `YYYY-MM-DD…` values. Columns that
  render localized or relative timestamps MUST expose an ISO value via a
  `data-<col>` row attribute (or `data-sort-value` on the cell); cell text alone
  will not sort correctly.
- **Sort-value resolution order** (this is what makes rollout cheap):
  1. `td[data-sort-value]` in the cell (explicit override),
  2. the row's `data-<col>` attribute (where `<col>` = the header's
     `data-sort-col`),
  3. the cell's `textContent`, located by the header's column index.

  Simple tables annotate **only the `<th>`** and rely on cell text. Complex tables
  whose cells contain widgets (e.g. findings' status `<select>`) supply explicit
  `data-<col>` row attributes.
- Click, `Enter`, or `Space` cycles asc ↔ desc. The component renders the
  indicator (↑/↓/↕), toggles `sort-asc`/`sort-desc` classes, and updates
  `aria-sort` on the header.

#### Filtering

Two opt-in modes, combinable:

- **Global search** — `<input data-tt-search>` (the component injects one above the
  table if the table requests it but none is present). Matches the query as a
  substring against the concatenated cell text of each row. This is the minimal
  uniform filter for small tables.
- **Per-column filter row** — `<tr data-tt-filter-row>` whose controls carry
  `data-filter-col="<col>"`. `<input>` matches as a substring; `<select>` matches
  exactly. Value source mirrors the sort resolution (`data-<col>` → cell text).
- **Custom-predicate escape hatch** — a table may register
  `window.tableToolsFilters['<col>'] = (rowEl, value) => boolean` for non-standard
  columns. This is how findings' "refs" filter (over `data-has-gh` etc.) is
  preserved without special-casing the component.

Rows are marked `data-filter-row`. After every sort/filter pass the component:

- updates a `[data-tt-count]` element ("shown N of M"), shown only while a filter
  is active,
- toggles a `[data-tt-empty]` empty-state message when nothing matches,
- dispatches a `table-tools:changed` event on the `<table>`.

Count/empty texts come from `data-tt-*` attributes (so templates pass i18n
strings) with English fallbacks baked into the component.

#### Persistence, events, a11y

- State (active sort column+direction, all filter values) is serialized to
  `localStorage` under `data-tt-key` and restored on load.
- `table-tools:changed` generalizes findings' existing `bulk:rows-changed`. The
  bulk-selection script is updated to listen to the new event (old name kept as an
  alias during migration to avoid a flag-day).
- Sortable headers are keyboard-operable and expose `aria-sort`.

### Global wiring

`table_tools.js` (deferred) and `table_tools.css` are included once from the base
layout (`_project_layout.html` / `base.html` — exact insertion point chosen during
implementation), so every page receives them. Static assets are already served
from `dreaming/static/`.

### Hybrid / server-capped tables

For routes that cap rows (orchestration `limit=50`, session-log, dashboard,
kanban, cascade-costs, questions, ai-radar):

- **Default:** client-side enhancement over the rows already rendered. Where the
  full dataset is small, raise/remove the cap so the client sees everything. The
  implementation plan must **enumerate each capped route explicitly** and state
  whether its cap is relaxed or left as-is — so no capped table is silently
  skipped.
- **Point-wise server-side** (`?sort=&q=` → SQL `ORDER BY`/`WHERE`): added only
  for a table that is genuinely large or paginated. Deferred out of the first
  wave. Such a table carries an explicit "filtering current page only" caption so
  the scope is honest.

## Rollout plan

1. **Component** — build `table_tools.js` + `table_tools.css`; wire into the base
   layout.
2. **Findings refactor (parity proof)** — convert `project_findings.html` to the
   component and delete its inline JS/CSS. Verify sort, per-column filter, the refs
   predicate, persistence, shown-count, empty-state, and bulk integration all still
   work. This is the acceptance gate for the component design.
3. **Large list tables** — roll out to ideas, plans, tech-debt, topics, notes,
   evolutions, contracts, orchestration list (full per-column filter where it
   helps).
4. **Small / summary tables** — minimum treatment: sortable headers + a global
   search box.
5. **i18n** — shared keys `table.search`, `table.reset`, `table.shown_count`,
   `table.empty`; RU and EN mirrored, written via the Write/Edit tool (UTF-8) per
   CLAUDE.md. Verified by `scripts/check_i18n.py`.
6. **Smoke** — `scripts/smoke_table_tools.py`: load representative pages, assert
   `data-table-tools` is present and the JS/CSS assets are served; plus manual
   browser verification of sort + filter on key pages.

## Components & boundaries

- **`table_tools.js`** — owns all DOM behaviour (sort, filter, persistence, events,
  a11y). Pure client-side, no per-table knowledge beyond the data-attribute
  contract. Testable by loading any page that has a `data-table-tools` table.
- **`table_tools.css`** — sort indicators and filter-row styling, themed to match
  the existing dark UI.
- **Templates** — declarative opt-in only: add `data-table-tools`, annotate
  headers, optionally add a filter row / search box / row data-attributes. No
  per-template JS.
- **Routes (capped tables only)** — optionally relax row caps; server-side
  `?sort=&q=` is a later, isolated change per route.

## Error handling

- A table with `data-table-tools` but no sortable headers and no filter controls is
  a no-op (the enhancer simply finds nothing to wire) — safe.
- `localStorage` access is wrapped in try/catch (quota / privacy mode) and fails
  silently, matching the current findings behaviour.
- Unknown `data-sort-type` falls back to `text`.
- A registered custom predicate that throws is caught per-row and treated as
  "no match excluded" (does not break the whole filter pass).

## Testing

No unit-test suite exists (by project design). Verification is:

- `scripts/smoke_table_tools.py` (asset + attribute presence),
- `scripts/check_i18n.py` (RU/EN key parity),
- manual browser checks of sort/filter/persistence on findings (parity) and at
  least one newly-converted table per wave.

## Out of scope (YAGNI)

- A generic data-driven table macro (approach B) — rejected.
- A third-party grid library (approach C) — rejected.
- Full server-side pagination UI. Server-side sort/filter is added only per-table,
  on demand, and is not part of the first wave.
- Multi-column / stable secondary sort — single active sort column, like the
  current findings implementation.
