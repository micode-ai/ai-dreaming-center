# Design System Foundation: token layer, component layer, template migration

**Date:** 2026-08-16
**Status:** Approved (design)
**Author:** brainstorming session

## Problem

The user asked to "improve the app design" and, when offered a choice, selected
all four directions at once: tidy up the system, change the look, deepen the key
screens, and improve navigation/ergonomics. That is a programme of work, not one
task. This spec covers the first two waves — **D1 (foundation)** and
**D2 (template migration)**. D3 (visual direction) and D4 (key screens +
ergonomics) get their own specs once this one lands.

The underlying problem is that the dashboard has *tokens* but no *component
layer*. `dreaming/static/app.css` defines a coherent dark palette in `:root`, and
almost nothing uses it. Templates encode visuals directly — as Tailwind utility
classes written for a light theme, or as inline `style="…"` — and a block of
`!important` overrides at the bottom of `app.css` retro-fits the dark theme onto
whichever utilities someone remembered to patch.

The consequence is that changing how the app looks means editing fifty templates,
and any utility nobody thought to patch renders as a light-theme artefact in a
dark app.

## What already exists (verified 2026-08-16)

Measured over `dreaming/templates/` (51 `.html` files) and
`dreaming/static/app.css` (404 lines):

- **496 inline `style="…"` attributes.** Only **5** interpolate Jinja
  (`{{ … }}`) and are therefore legitimately dynamic; the other **491** are
  static visuals that belong in a stylesheet.
- **96 uses of light-theme Tailwind background utilities**
  (`bg-white`, `bg-slate-50/100`, `bg-gray-50/100`, `bg-amber-50/100`,
  `bg-red-50`, `bg-green-50`, `bg-blue-50`, `bg-sky-50`).
- **No button class exists.** Every button is a bespoke utility string plus an
  inline style. The single most common one —
  `class="text-xs px-2 py-1 border border-slate-300 rounded text-slate-600 hover:bg-slate-100"`
  (the table "reset" button) — is duplicated verbatim **27 times**.
- **Template inheritance is already centralized**, which makes the migration
  tractable: 32 templates extend `_project_layout.html`, 6 extend `base.html`
  directly, the rest are includes/partials.

### Two rendering bugs this causes

These are not aesthetic complaints; they are broken output:

1. **Light islands.** `bg-sky-50` (8 uses) and `bg-amber-50` (10 uses) are *not*
   in the `!important` override block. Those banners render near-white on the
   dark app — in `project_dashboard.html`, `project_orchestration_list.html`,
   `project_questions.html`, `project_rotation.html`, `project_topics.html`,
   `session_log.html`, `_autoconfig_banner.html`.
2. **Contrast failure.** Buttons styled `border-purple-500 text-purple-700`
   (8 uses) put dark purple text on a dark card. Purple is not in the override
   block either.

Other unpatched utilities in active use: `text-sky-900` (18), `text-amber-900`
(13), `bg-amber-600` (6), `border-sky-300` (8), `border-amber-400` (6),
`text-emerald-500/600` (3).

### Existing conventions this work must follow

- Verification is by hand-written scripts, not a test suite:
  `scripts/check_i18n.py`, `scripts/check_no_native_dialogs.py`, and ~25
  `scripts/smoke_*.py`. New checks join this convention.
- `table_tools.css` already reads tokens with fallbacks
  (`var(--border-subtle, #1e293b)`) — the pattern to generalize.
- Per CLAUDE.md: user-facing strings go through `| t(locale=locale)`; files with
  Cyrillic content are written via Write/Edit (UTF-8), never PowerShell
  `Set-Content`.

## Decisions (from brainstorming)

- **Foundation:** keep Tailwind via CDN, add a hand-written component layer.
  Rejected: compiling Tailwind locally (adds npm + a build step to a Python
  project), and dropping Tailwind entirely (would require rewriting layout in all
  51 templates — the largest mechanical churn and the highest risk).
- **Theme:** dark only. No light theme, no toggle.
- **Visual direction:** direction A ("clean console") as the base language —
  the current indigo, quieter borders, fewer nested frames — combined with the
  row density of direction B for tables and lists. Rejected: direction B whole
  (too terminal for text-heavy screens like wiki and notes) and direction C
  (gradients and 16px radii cost vertical space and tire the eye in a tool viewed
  many times a day).
- **Division of labour:** Tailwind keeps *layout only* (`grid`, `flex`, `gap`,
  `col-span`, responsive prefixes). Colour, size, border, radius, and shadow
  leave the templates entirely.

## Architecture

### Stylesheet split

`app.css` splits into three files with enforced boundaries, loaded from
`base.html` in this fixed order:

| File | Contains | Must not contain |
|---|---|---|
| `dreaming/static/tokens.css` | only `:root { --… }` — colour, surfaces, borders, radii, shadows, spacing scale, typography, density | any selector other than `:root` |
| `dreaming/static/components.css` | semantic classes (`.btn`, `.card`, `.toolbar`, `.banner`, …) | any hex literal — `var(…)` only |
| `dreaming/static/app.css` | base only: `body`, scrollbar, native form elements, `.md-content`, the sidebar shell | components and token definitions |

The "no hex in `components.css`" rule is the load-bearing invariant: it is what
makes a future look change (D3) cost a token edit rather than another sweep of
the codebase. It is enforced by `scripts/check_css_tokens.py`, not by discipline.

`table_tools.css` and `orchestration_swimlane.css` stay as they are — they are
already token-driven and scoped to their features.

### Token layer

Extends the existing `:root` block rather than replacing it. Current token names
(`--bg-app`, `--brand`, `--status-*`, …) are **kept**, because `table_tools.css`,
`orchestration_swimlane.css`, and ~491 inline styles reference them; renaming
them would be a flag-day. New tokens are added alongside:

- **Surfaces / borders** — retuned per direction A: quieter borders
  (`--border-subtle` moves toward `#1d2534`), slightly deeper surfaces, less
  visual noise from frames.
- **Spacing scale** — one ramp (4 / 8 / 12 / 16 / 24 / 32px) as
  `--space-1 … --space-6`, ending the `mb-5`-next-to-`mb-6` drift.
- **Radii** — `--radius-sm` / `--radius` / `--radius-lg`.
- **Density** — row padding and font size for two modes (see below).
- **Numerics** — JetBrains Mono with `font-variant-numeric: tabular-nums` for
  numbers, identifiers, and timestamps, so counter and time columns stop
  shifting between rows.

### Density

Two modes, selected per table by the template, not globally:

- **Default** — current comfortable rows (~40px), for text-heavy content
  (wiki, notes, plans, contracts).
- **`.is-dense`** — direction B's compact rows (~28px) plus mono numerics, for
  scanning-oriented tables (sessions, orchestration runs, findings, ideas,
  evolutions, AI usage).

`.is-dense` is a modifier on `.data-table`; it changes cell padding and font size
via tokens only.

### Component inventory

Derived from measured usage, not invented:

| Class | Replaces | Current state in code |
|---|---|---|
| `.btn`, `.btn-primary`, `.btn-danger`, `.btn-ghost`, `.btn-sm` | every button | 100+ variations; one string duplicated 27× |
| `.toolbar` | the "search + reset + count" strip above tables | 27 hand-copied instances |
| `.banner`, `.banner-info`, `.banner-warn`, `.banner-danger` | the light sky/amber islands | 7 files, `bg-sky-50` / `bg-amber-50` |
| `.page-header` | ad-hoc `h1`/`h2` plus inline `style="color: …"` | different in every template |
| `.card`, `.panel` | inline `style="background: var(--bg-card); border: 1px solid …"` | part of the 491 static inline styles |
| `.empty-state` | ad-hoc "nothing here" paragraphs | inconsistent |
| `.field` | label + input pairs in settings/setup forms | inconsistent |
| `.metric`, `.badge`, `.pill`, `.tile`, `.data-table` | — already exist; realigned to the shared scale, not rewritten | in `app.css` today |

Every component is plain CSS. No build step, no new runtime dependency.

### Boundaries

- **`tokens.css`** — the only place the app's look is defined. Changing D3 means
  editing this file.
- **`components.css`** — the only place component appearance is defined. Depends
  on `tokens.css`; knows nothing about pages.
- **Templates** — structure, content, and layout utilities only. A template that
  needs a new visual affordance gets a new component class, not an inline style.
- **`check_css_tokens.py`** — enforces the boundaries above; its counters make
  migration progress a number rather than a feeling.

## Migration plan (D2)

General to specific, so each step makes the next cheaper. Each batch is a
separate commit and the app runs after every one.

1. **Shell** — `base.html`, `_sidebar.html`, `_project_layout.html`. Establishes
   `.page-header` and the shell tokens every other template inherits.
2. **Top three screens** — `project_dashboard.html`,
   `project_orchestration_list.html` (54 inline styles),
   `project_findings.html`. These exercise every component in the inventory and
   act as the acceptance gate for the component API: if a component is wrong,
   it is wrong here, before 48 more templates depend on it.
3. **Heaviest remainder** — `project_ai_usage.html` (92),
   `global_ai_usage.html` (78), `project_review.html` (27),
   `project_kanban.html` (23), `project_loops_template_view.html` (21),
   `project_evolutions.html` (20), `project_cascade_costs.html` (19),
   `_ai_radar_card.html` (19).
4. **The rest** — in batches of 5–8, grouped by similarity (detail views,
   settings/setup forms, list views).
5. **Remove the compatibility block** — the `!important` overrides at the bottom
   of `app.css` are deleted **last**, as the final commit of the wave. Until the
   last template is migrated they are the only thing keeping unmigrated screens
   readable. Deleting them early would break every screen not yet converted.

**Definition of done for a template:** zero static inline `style=` and zero
light-theme utility classes — exactly the two conditions
`check_css_tokens.py` asserts over templates. Dynamic `style="{{ … }}"` (5
occurrences, e.g. bar widths) is permitted and explicitly exempted by the linter.
(The no-hex rule applies to `components.css`, not to templates, which after
migration carry no colour at all.)

## Error handling and risk

- **Risk: a component API mistake propagates to 51 templates.** Mitigated by
  step 2 — the three most complex screens are converted first and reviewed before
  the bulk migration begins.
- **Risk: removing the `!important` block breaks unmigrated screens.** Mitigated
  by ordering: it is the last commit, gated on the linter reporting zero
  remaining light-theme utilities.
- **Risk: a Jinja typo during a bulk edit yields a 500 on a page nobody opens.**
  There is currently no coverage for this at all, while this wave edits 51
  templates. Mitigated by `smoke_render_all.py` (below).
- **Risk: token rename breaks `table_tools.css` / inline styles mid-migration.**
  Avoided by decision: existing token names are kept, new ones added alongside.
- Unknown or missing tokens degrade rather than break: component CSS uses
  `var(--token, <fallback>)` for anything introduced in this wave, matching the
  existing `table_tools.css` pattern.

## Testing

No unit-test suite exists (by project design). Verification is:

- **`scripts/check_css_tokens.py`** (new) — three assertions plus counters:
  1. no hex literal in `components.css`;
  2. no light-theme utility class in `dreaming/templates/**`;
  3. no static inline `style=` in `dreaming/templates/**` (dynamic
     `style="{{ … }}"` exempt).
  It always prints per-file counts, so the migration reads as `491 → … → 0`.
  It exits non-zero on any violation, which means it only passes once the wave is
  complete; while the wave is in progress it is run for its counters, and it
  becomes a gate at the final commit.
- **`scripts/smoke_render_all.py`** (new) — walks the app's routes with FastAPI
  `TestClient` against a seeded DB and asserts none returns 500. This is the
  safety net for editing 51 templates, and it outlives this wave.
- **`scripts/check_i18n.py`** (existing) — any new user-facing string keeps RU/EN
  parity.
- **Manual browser check** — one screen per migration batch, plus a narrow-window
  pass, plus explicit re-checks of the two known bugs (the sky/amber banners and
  the purple buttons).

## Out of scope (YAGNI)

- **Light theme** and a theme toggle — explicitly declined.
- **Compiling Tailwind locally / dropping Tailwind** — both rejected above.
  Tailwind stays on the CDN for layout utilities.
- **Renaming existing tokens** — additive only, to avoid a flag-day.
- **D3 (visual direction application)** — this wave builds the mechanism and
  retunes tokens toward direction A + B density. A fuller look change is a
  separate, cheap follow-up once `components.css` is hex-free.
- **D4 (key screens and ergonomics)** — information hierarchy, sidebar structure,
  narrow-screen behaviour, loading/error states, and a unified confirmation
  pattern are deferred to their own spec. They depend on the components existing.
- **A Jinja macro library for components** — plain CSS classes on existing markup
  are enough; macros would fight the heterogeneous table/cell markup, the same
  conclusion the table-tools spec reached.
