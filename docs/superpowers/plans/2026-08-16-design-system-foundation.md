# Design System Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the dashboard a real component layer so its appearance lives in CSS tokens instead of 491 inline styles and 96 light-theme Tailwind utilities scattered across 51 templates.

**Architecture:** `app.css` splits into three files with enforced boundaries — `tokens.css` (only `:root`, the single source of visual truth), `components.css` (semantic classes, no hex literals), and a slimmed `app.css` (base elements, sidebar shell, markdown). Templates then migrate off inline styles and colour utilities in batches, each batch a commit that leaves the app running. Two new scripts make the migration measurable and catch Jinja typos.

**Tech Stack:** Jinja2 templates, Tailwind via CDN (layout utilities only), hand-written CSS, Python check/smoke scripts in the existing `scripts/` convention. No build step, no new runtime dependency.

**Spec:** `docs/superpowers/specs/2026-08-16-design-system-foundation-design.md`

---

## Global Constraints

These apply to **every** task. They are not repeated per task.

- **No build step.** Plain CSS only. Do not add npm, PostCSS, or a Tailwind config file.
- **Tailwind keeps layout only:** `grid`, `flex`, `gap-*`, `col-span-*`, `space-*`, `w-*`, `max-w-*`, every margin utility (`mb-*`, `mt-*`, `ml-*`, `mr-*`, `mx-*`, `my-*`), padding utilities where no component sets the padding, list utilities (`list-disc`, `list-none`), responsive prefixes, `hidden`, `truncate`, `whitespace-nowrap`, `text-left/center/right`.
- **Colour utilities leave the templates entirely** — a utility carrying a palette colour name (`bg-white`, `text-slate-600`, `border-amber-400`, `bg-white/85`) is what `COLOUR_UTILITY` in `check_css_tokens.py` matches, and it is what this wave is measured on.
- **Un-suffixed `border`, `rounded`, and `shadow` are NOT gated** — the linter's regex requires a colour-name suffix, so those never match it. Drop them where a component already supersedes them (`.btn`, `.banner`, `.card`, `.data-table` all set their own border and radius); leave them on elements no component covers, such as the bare filter inputs inside a `table_tools` filter row. Do not hunt them down for their own sake, and do not treat an earlier task's decision to leave one as a defect — Tasks 7 and 8 both settled this the same way.
- **Font-size utilities (`text-xs`, `text-sm`, …) are tolerated** where no component already sets the size. They are not gated by the linter and the replacement table does not cover them, so claiming they all disappear would be promising more than this wave delivers. Prefer a component class when one fits; leave the utility when none does. Tightening this is a follow-up once font size becomes a gated metric.
- **Existing token names are never renamed.** `--bg-app`, `--bg-card`, `--brand`, `--status-*`, `--border-subtle`, `--text-*` are load-bearing for `table_tools.css`, `orchestration_swimlane.css`, and every not-yet-migrated inline style. Add new tokens alongside; never rename or delete an existing one during this wave.
- **`components.css` contains no hex literal.** Colour arrives via `var(--token)`. `rgba(0, 0, 0, …)` is permitted for shadows — the rule targets palette colour, not black alpha. Enforced by `scripts/check_css_tokens.py`.
- **The `!important` compatibility block at the bottom of `app.css` is deleted in Task 17 and not before.** It is the only thing keeping unmigrated screens readable.
- **Migrate a template completely or not at all.** A half-migrated file mixes `.btn` with `.text-slate-600 !important` and renders worse than either state.
- **Cyrillic content is written via the Write/Edit tool (UTF-8).** PowerShell `Set-Content` defaults to UTF-16 LE and breaks the parser (CLAUDE.md).
- **User-facing strings keep `{{ "key" | t(locale=locale) }}`.** Migration must not change any string, key, `data-*` attribute, `hx-*` attribute, form `action`, or `data-confirm` payload. This wave changes appearance only. `scripts/check_i18n.py` must stay green.
- **Dynamic `style="{{ … }}"` stays.** 5 occurrences (bar widths and similar) are legitimate and exempt from the linter.
- **Per-file counts written in prose in this plan are approximate; the linter is authoritative.** The prose figures (e.g. "`project_ai_usage.html` (92 inline styles)") were taken from a line-oriented grep, so a line carrying two `style=` attributes was counted once. `check_css_tokens.py` counts attributes, and reports one or two more for such files. Only the two totals — **464** colour utilities and **491** static inline styles — are exact gates. A per-file disagreement of one or two is expected and is not a sign you miscounted.
- **Do not introduce single-quoted `style='…'` attributes.** The linter only matches double-quoted ones, so a single-quoted attribute would escape both the counter and the exemption check. There are none in the tree today, and migration should be removing these attributes, not adding them.
- **`smoke_templates_render.py` covers both tiers here — do not settle for tier 1.** This worktree's `data/dreaming.db` is gitignored, throwaway, and separate from the main checkout's development database. It was seeded during Task 2 (`python scripts/smoke_seed_one.py smoke "D:/Work/micode/ai-dreaming-center/.worktrees/design-system"`), so the route walk now runs automatically and covers **45 parameter-free GET routes**. Every migration task should therefore see `OK all 45 parameter-free GET routes render`, not a `SKIP` notice. **A SKIP means the seeded project is gone — re-seed with the command above rather than accepting the weaker tier-1-only result.** Tier 2 is what catches a runtime template error (undefined variable, bad filter argument) that tier 1's compile pass cannot see; on a wave that edits 51 templates it is the more valuable of the two.

### Canonical replacement table

Every migration task (5–16) applies these. Left column is what exists in the tree today; right column is the replacement.

| Existing markup | Replace with |
|---|---|
| `class="text-xs px-2 py-1 border border-slate-300 rounded text-slate-600 hover:bg-slate-100"` (27×, the table reset button) | `class="btn btn-sm"` |
| `class="text-sm bg-blue-600 text-white rounded px-3 py-1"` | `class="btn btn-primary"` |
| `class="text-sm px-3 py-1 rounded bg-purple-600 text-white font-semibold"` | `class="btn btn-primary"` |
| `class="text-xs px-2 py-1 border border-slate-500 text-slate-700 rounded"` | `class="btn btn-sm"` |
| `class="text-xs px-2 py-1 border border-purple-500 text-purple-700 rounded"` | `class="btn btn-sm"` |
| `class="text-xs px-2 py-1 border rounded text-red-600"` / `border-red-200 bg-red-50 text-red-700` | `class="btn btn-sm btn-danger"` |
| `class="… border-amber-300 bg-amber-50 text-amber-700 …"` (Stop / Force-close) | `class="btn btn-sm btn-warn"` |
| `class="text-sm bg-amber-600 text-white rounded px-4 py-2 font-semibold"` | `class="btn btn-warn"` |
| `<button …>` styled with inline `style="background: var(--bg-hover); color: …; border:1px solid …"` | `class="btn btn-sm"` |
| `<div class="… p-4 border border-amber-400 bg-amber-50 rounded">` | `<div class="banner banner-warn">` |
| `<div class="… bg-sky-50 … text-sky-900 …">` | `<div class="banner banner-info">` |
| `<div class="… bg-red-50 border-red-200 …">` | `<div class="banner banner-danger">` |
| `<div class="rounded-lg p-4" style="background: var(--bg-card); border:1px solid var(--border-subtle);">` | `<div class="card">` |
| `<h1 class="text-2xl font-bold mb-4" style="color: var(--text-strong);">X</h1>` | `<div class="page-header"><div class="page-header__titles"><h1 class="page-header__title">X</h1></div></div>` |
| `<h2 class="font-semibold text-slate-900 mb-2">` / `<h2 class="font-semibold …" style="color: var(--text-strong);">` | `<h2 class="section-title">` |
| `<p class="muted">…nothing here…</p>` | `<p class="empty-state">…</p>` |
| `<div class="mb-2 flex items-center gap-2">` wrapping `[data-tt-search]` + `[data-tt-reset]` | `<div class="toolbar">` (keep `.tt-search` on the input — it is owned by `table_tools.css`) |
| `class="text-xs font-mono"` on a numeric/timestamp/id cell | `class="num"` |
| `<ul class="bg-white rounded-lg border border-slate-200 shadow-sm divide-y divide-slate-100">` | `<ul class="card card--flush list-rows">` |
| any `style="color: var(--text-*)"` | drop it — the component class already sets it |

Tables that are scanned rather than read (`sessions`, orchestration runs, findings, ideas, evolutions, AI usage) additionally get `class="data-table is-dense"`.

---

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `dreaming/static/tokens.css` | Only `:root { --… }`. The single place the app's look is defined. |
| `dreaming/static/components.css` | Semantic component classes. Depends on tokens; knows nothing about pages. |
| `scripts/check_css_tokens.py` | Enforces the boundaries; prints per-file counters so migration progress is a number. |
| `scripts/smoke_templates_render.py` | Compiles all 51 templates; best-effort walk of parameter-free GET routes. |

**Modified:**

| File | Change |
|---|---|
| `dreaming/templates/base.html` | Load the new stylesheets in order; migrate the flash banner. |
| `dreaming/static/app.css` | Components move out to `components.css`; tokens move out to `tokens.css`; keeps base elements, sidebar shell, `.md-content`, and (until Task 17) the `!important` block. |
| 51 templates under `dreaming/templates/` | Migrated in batches, Tasks 5–16. |

**Untouched:** `dreaming/static/table_tools.css`, `dreaming/static/table_tools.js`, `dreaming/static/orchestration_stream.js` — already token-driven and feature-scoped.

**Correction (mid-wave).** `dreaming/static/orchestration_swimlane.css` was originally listed as untouched on the same grounds. Reading it during Task 7 showed the claim was false: nine hardcoded light-theme foreground colours and a reference to `--bg-surface`, a token that has never existed. Task 7A now fixes it. The lesson generalizes — "already token-driven" was asserted about all four files from their filenames and roles, not from reading them.

---

### Task 1: Design-system linter

The linter is the test for this whole wave. It is built first so every later task has a pass/fail signal and a progress counter.

**Files:**
- Create: `scripts/check_css_tokens.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: a CLI, `python scripts/check_css_tokens.py`. Exit `0` when clean, `1` on any violation. Every later task runs it. `components.css` not existing yet is *not* an error — the file check is skipped with a notice so this task can be verified before Task 4 exists.

- [ ] **Step 1: Write the linter**

Create `scripts/check_css_tokens.py`:

```python
"""Design-system linter: keeps colour out of templates and hex out of components.

Three assertions, each with a per-file counter so migration progress is a number
rather than a feeling:

  1. components.css contains no hex colour literal (#abc / #aabbcc). Colour must
     come from tokens.css via var(). rgba(0, 0, 0, ...) is permitted for shadows
     -- the rule targets palette colour, not black alpha.
  2. No template uses a light-theme Tailwind colour utility.
  3. No template carries a static inline style= attribute. Dynamic
     style="{{ ... }}" is exempt (bar widths and similar).

Run it for its counters during migration; it becomes a gate once it exits 0.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "dreaming" / "templates"
COMPONENTS = ROOT / "dreaming" / "static" / "components.css"

HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")

# A Tailwind utility carrying a palette colour. Requires a colour name, so
# layout/size utilities (text-xs, border, bg-none) never match.
COLOUR_UTILITY = re.compile(
    r"\b(?:bg|text|border|divide|ring|from|to|via)-"
    r"(?:white|black|slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|"
    r"green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)"
    r"(?:-\d{2,3})?(?:/\d{1,3})?\b"
)

INLINE_STYLE = re.compile(r'style\s*=\s*"([^"]*)"')


def _hex_in_components() -> list[str]:
    if not COMPONENTS.exists():
        print("SKIP components.css hex check (file does not exist yet)")
        return []
    bad = []
    for i, line in enumerate(COMPONENTS.read_text(encoding="utf-8").splitlines(), 1):
        for m in HEX.finditer(line):
            bad.append(f"components.css:{i}: {m.group(0)}  ({line.strip()[:60]})")
    return bad


def _scan_templates() -> tuple[dict[str, int], dict[str, int]]:
    utilities: dict[str, int] = {}
    inline: dict[str, int] = {}
    for tpl in sorted(TEMPLATES.rglob("*.html")):
        rel = tpl.relative_to(TEMPLATES).as_posix()
        text = tpl.read_text(encoding="utf-8")
        u = len(COLOUR_UTILITY.findall(text))
        # Dynamic styles carry Jinja interpolation and are exempt.
        s = sum(1 for m in INLINE_STYLE.finditer(text) if "{{" not in m.group(1))
        if u:
            utilities[rel] = u
        if s:
            inline[rel] = s
    return utilities, inline


def _report(title: str, counts: dict[str, int]) -> int:
    total = sum(counts.values())
    if not total:
        print(f"OK {title}: 0")
        return 0
    print(f"{title}: {total} across {len(counts)} file(s)")
    for name, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:5d}  {name}")
    return total


def main() -> int:
    failed = False

    hex_bad = _hex_in_components()
    if hex_bad:
        print(f"Hex literals in components.css: {len(hex_bad)}")
        for line in hex_bad:
            print("  " + line)
        failed = True
    elif COMPONENTS.exists():
        # Only claim OK for a file actually read. Before Task 4 creates it,
        # _hex_in_components has already printed its SKIP notice.
        print("OK components.css: no hex literals")

    utilities, inline = _scan_templates()
    if _report("Light-theme colour utilities in templates", utilities):
        failed = True
    if _report("Static inline style= in templates", inline):
        failed = True

    print("FAIL" if failed else "ALL OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it to capture the baseline**

Run: `python scripts/check_css_tokens.py`

Expected: exit code 1 and **exactly** these totals — they were measured against the tree on 2026-08-16 and are the baseline this wave drives to zero:

```
SKIP components.css hex check (file does not exist yet)
Light-theme colour utilities in templates: 464 across 35 file(s)
   39  project_dashboard.html
   31  index_dashboard.html
   27  _app_modal.html
   27  project_findings.html
   25  project_evolutions.html
   ...
Static inline style= in templates: 491 across 30 file(s)
   92  project_ai_usage.html
   78  global_ai_usage.html
   54  project_orchestration_list.html
   ...
FAIL
```

Both totals **must match exactly: 464 and 491**. If either differs, the regex is wrong — fix it before continuing, because every later task trusts these numbers. (Total `style="` occurrences are 496; 5 contain `{{` and are exempt.)

If the working tree has drifted since 2026-08-16 the numbers may differ legitimately; in that case record the new baseline in the commit message and use it instead.

- [ ] **Step 3: Verify the exemption works**

Run: `python -c "import re,pathlib; p=pathlib.Path('dreaming/templates'); r=re.compile(r'style\s*=\s*\"([^\"]*)\"'); print(sum(1 for f in p.rglob('*.html') for m in r.finditer(f.read_text(encoding='utf-8')) if '{{' in m.group(1)))"`

Expected: `5`

- [ ] **Step 4: Verify no false positives on layout utilities**

Run: `python -c "from scripts.check_css_tokens import COLOUR_UTILITY as C; print([C.search(s) is None for s in ['text-xs','border','flex gap-2','grid-cols-3','whitespace-nowrap','bg-white','text-slate-600','border-amber-400','bg-white/85']])"`

Expected: `[True, True, True, True, True, False, False, False, False]` — the first five are layout/size and must not match; the last four are colour and must match.

- [ ] **Step 5: Commit**

```bash
git add scripts/check_css_tokens.py
git commit -m "chore(design): add design-system linter with migration counters

Baseline: 491 static inline style= attributes across 30 files and 464
light-theme colour utilities across 35 files in dreaming/templates/. This
script drives both to zero over the design-system wave and becomes a gate at
the end of it."
```

---

### Task 2: Template compile smoke

This wave edits 51 templates. There is currently no coverage at all against a Jinja typo on a page nobody opens.

**Files:**
- Create: `scripts/smoke_templates_render.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a CLI, `python scripts/smoke_templates_render.py`. Exit `0` when all templates compile. Every migration task (5–16) runs it.

**Honest scope:** Tier 1 catches **syntax** errors (unclosed `{% block %}`, bad `{{ }}`), which is the failure mode bulk editing actually causes. It does **not** catch runtime errors such as an undefined variable — those need a real render with a real context, which Tier 2 covers only for routes the local DB can serve.

- [ ] **Step 1: Write the smoke script**

Create `scripts/smoke_templates_render.py`:

```python
"""Compile every Jinja template; then best-effort GET every simple route.

Tier 1 (deterministic, always runs): compile all *.html under
dreaming/templates through a Jinja environment matching the app's. Catches the
failure mode this design wave risks -- a syntax typo introduced while bulk
editing 51 templates. Does NOT catch runtime errors (undefined variable, bad
filter argument).

Tier 2 (best effort): boot the app through its real lifespan and GET every
registered GET route that needs no path parameter other than a project slug.
Skipped with a printed notice when no project is configured, so the script
stays useful on a fresh checkout.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TEMPLATES = ROOT / "dreaming" / "templates"

# SSE endpoints never complete -- a plain GET would hang the run.
SSE = re.compile(r"/stream(/|$)")


def compile_all() -> int:
    from jinja2 import Environment, FileSystemLoader, TemplateSyntaxError

    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    env.filters["t"] = lambda k, **kw: k  # runtime filter; stubbed for compile

    failures: list[str] = []
    names = sorted(p.relative_to(TEMPLATES).as_posix() for p in TEMPLATES.rglob("*.html"))
    for name in names:
        try:
            env.get_template(name)
        except TemplateSyntaxError as exc:
            failures.append(f"  {name}:{exc.lineno}: {exc.message}")

    if failures:
        print(f"Template compile FAILED ({len(failures)} of {len(names)}):")
        print("\n".join(failures))
        return 1
    print(f"OK all {len(names)} templates compile")
    return 0


def walk_routes() -> int:
    # Only a missing dependency is an environment problem worth skipping over.
    # Any other import failure is a real regression and must not be swallowed.
    try:
        from fastapi.testclient import TestClient
        from dreaming.main import app
    except ImportError as exc:
        print(f"SKIP route walk (dependency unavailable: {exc})")
        return 0

    with TestClient(app) as client:
        # The /projects probe is itself a route render. If it raises or 500s,
        # that IS the failure this script exists to catch -- reporting it as
        # "no project configured" would turn a broken page into a green run.
        try:
            rows = client.get("/projects")
        except Exception as exc:  # noqa: BLE001 - reported as failure, not swallowed
            print(f"Route walk FAILED: GET /projects raised {type(exc).__name__}: {exc}")
            return 1
        if rows.status_code >= 500:
            print(f"Route walk FAILED: GET /projects returned HTTP {rows.status_code}")
            return 1

        m = re.search(r'name="slug" value="([a-z0-9-]+)"', rows.text)
        slug = m.group(1) if m else None
        if not slug:
            print("SKIP route walk (no project configured in the local DB)")
            return 0
        print(f"Route walk using project slug: {slug}")

        paths: list[str] = []
        for route in app.routes:
            methods = getattr(route, "methods", None) or set()
            path = getattr(route, "path", "")
            if "GET" not in methods or not path:
                continue
            if SSE.search(path):
                continue
            candidate = path.replace("{slug}", slug)
            if "{" in candidate:  # needs an id we do not have
                continue
            paths.append(candidate)

        bad: list[str] = []
        for path in sorted(set(paths)):
            try:
                r = client.get(path, follow_redirects=True)
            except Exception as exc:  # noqa: BLE001
                bad.append(f"  {path}: raised {type(exc).__name__}: {exc}")
                continue
            if r.status_code >= 500:
                bad.append(f"  {path}: HTTP {r.status_code}")

        if bad:
            print(f"Route walk FAILED ({len(bad)} of {len(set(paths))}):")
            print("\n".join(bad))
            return 1
        print(f"OK all {len(set(paths))} parameter-free GET routes render")
    return 0


def main() -> int:
    rc = compile_all()
    rc |= walk_routes()
    print("FAIL" if rc else "ALL OK")
    return rc


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it against the current tree**

Run: `python scripts/smoke_templates_render.py`

Expected: `OK all 51 templates compile`, then either the route walk result or a `SKIP` notice. Exit `0`. If a template already fails to compile, that is a pre-existing bug — fix it in this task and say so in the commit message.

- [ ] **Step 3: Verify the check actually catches a break**

Deliberately break a template, confirm the script fails, then restore it:

```bash
python -c "import pathlib; p=pathlib.Path('dreaming/templates/project_help.html'); p.write_text(p.read_text(encoding='utf-8') + '{% block oops %}', encoding='utf-8')"
python scripts/smoke_templates_render.py
git checkout -- dreaming/templates/project_help.html
```

Expected: the middle command prints `Template compile FAILED` naming `project_help.html` and exits 1. Then `python scripts/smoke_templates_render.py` passes again after the checkout. A check that cannot fail is not a check.

- [ ] **Step 4: Commit**

```bash
git add scripts/smoke_templates_render.py
git commit -m "chore(design): add template compile smoke + best-effort route walk

Nothing currently guards against a Jinja typo on a rarely-opened page, and the
design-system wave edits all 51 templates. Tier 1 compiles every template
deterministically; tier 2 GETs every parameter-free route when the local DB has
a project, skipping SSE endpoints that never complete."
```

---

### Task 3: Token layer

**Files:**
- Create: `dreaming/static/tokens.css`
- Modify: `dreaming/static/app.css:7-48` (delete the `:root` block that moves out)
- Modify: `dreaming/templates/base.html:22-23` (stylesheet load order)

**Interfaces:**
- Consumes: nothing.
- Produces: the token vocabulary every later task uses. New names introduced here and relied on by Task 4: `--brand-on`, `--brand-fg`, `--status-{success,failed,timeout,running}-border`, `--status-{failed,timeout}-strong`, `--space-1..6`, `--radius-sm`, `--radius`, `--radius-lg`, `--radius-pill`, `--font-sans`, `--font-mono`, `--text-xs`, `--text-sm`, `--text-base`, `--text-md`, `--text-lg`, `--text-h2`, `--text-h1`, `--row-pad-y`, `--row-pad-x`, `--row-font`, `--row-pad-y-dense`, `--row-pad-x-dense`, `--row-font-dense`, `--control-h`, `--control-h-sm`, `--shadow-modal`.

- [ ] **Step 1: Create `dreaming/static/tokens.css`**

Existing names keep their meaning; several surface and text values are retuned toward visual direction A (quieter borders, slightly deeper surfaces).

```css
/* ============================================================
   tokens.css — the single source of truth for how the app looks.
   ONLY :root lives here. No selectors, no components, no rules.
   Changing the app's visual direction means editing this file
   and nothing else.
   ============================================================ */

:root {
  /* ---------- Surfaces (retuned: direction A) ---------- */
  --bg-app: #0a0e17;
  --bg-card: #10151f;
  --bg-sidebar: #080b12;
  --bg-elevated: #141a26;
  --bg-hover: #161c28;

  /* ---------- Borders (quieter than before) ---------- */
  --border-subtle: #1d2534;
  --border-muted: #2a3444;

  /* ---------- Text ---------- */
  --text-strong: #f1f5f9;
  --text-body: #dbe3ec;
  --text-muted: #8b9bb0;
  --text-faint: #5f6e83;

  /* ---------- Brand ---------- */
  --brand: #6366f1;
  --brand-hover: #818cf8;
  --brand-soft: rgba(99, 102, 241, 0.14);
  --brand-strong: #4f46e5;
  --brand-fg: #c7d2fe;   /* text/icon on --brand-soft */
  --brand-on: #ffffff;   /* text on solid --brand */

  /* ---------- Status: text / soft background / border ---------- */
  --status-success: #4ade80;
  --status-success-soft: rgba(34, 197, 94, 0.18);
  --status-success-border: rgba(34, 197, 94, 0.35);
  --status-failed: #f87171;
  --status-failed-soft: rgba(239, 68, 68, 0.14);
  --status-failed-strong: rgba(239, 68, 68, 0.24);
  --status-failed-border: rgba(239, 68, 68, 0.35);
  --status-timeout: #fbbf24;
  --status-timeout-soft: rgba(245, 158, 11, 0.14);
  --status-timeout-strong: rgba(245, 158, 11, 0.24);
  --status-timeout-border: rgba(245, 158, 11, 0.35);
  --status-running: #60a5fa;
  --status-running-soft: rgba(59, 130, 246, 0.16);
  --status-running-border: rgba(59, 130, 246, 0.35);
  --status-live: #34d399;
  --status-live-soft: rgba(16, 185, 129, 0.18);

  /* ---------- Shadows ---------- */
  --shadow-card: 0 1px 2px 0 rgba(0, 0, 0, 0.35), 0 1px 3px 0 rgba(0, 0, 0, 0.25);
  --shadow-card-hover: 0 6px 18px -8px rgba(0, 0, 0, 0.55), 0 2px 4px rgba(0, 0, 0, 0.35);
  --shadow-modal: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
  --ring: 0 0 0 2px var(--brand-soft), 0 0 0 4px var(--brand);

  /* ---------- Spacing scale (one ramp, no more mb-5 next to mb-6) ---------- */
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-5: 1.5rem;
  --space-6: 2rem;

  /* ---------- Radii ---------- */
  --radius-sm: 0.4375rem;
  --radius: 0.625rem;
  --radius-lg: 0.875rem;
  --radius-pill: 9999px;

  /* ---------- Typography ---------- */
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
  --text-xs: 0.6875rem;
  --text-sm: 0.75rem;
  --text-base: 0.8125rem;
  --text-md: 0.875rem;
  --text-lg: 1rem;
  --text-h2: 1.0625rem;
  --text-h1: 1.375rem;

  /* ---------- Table density (direction B for scanned tables) ---------- */
  --row-pad-y: 0.6rem;
  --row-pad-x: 0.75rem;
  --row-font: 0.8125rem;
  --row-pad-y-dense: 0.35rem;
  --row-pad-x-dense: 0.6rem;
  --row-font-dense: 0.78125rem;

  /* ---------- Controls ---------- */
  --control-h: 2rem;
  --control-h-sm: 1.625rem;
}
```

- [ ] **Step 2: Delete the moved block from `app.css`**

Remove lines 7–48 of `dreaming/static/app.css` — the entire `:root { … }` block, from the `/* Surfaces */` comment through the closing brace after `--ring`. Keep the file's leading banner comment. Leave everything from `html { scroll-behavior: smooth; }` onward untouched.

- [ ] **Step 3: Wire the load order in `base.html`**

Replace line 22 (`<link rel="stylesheet" href="/static/app.css">`) with:

```html
  <link rel="stylesheet" href="/static/tokens.css">
  <link rel="stylesheet" href="/static/app.css">
  <link rel="stylesheet" href="/static/components.css">
```

Order matters: tokens define the vocabulary, `app.css` styles base elements, `components.css` wins over base. Leave the existing `table_tools.css` link on the following line — it loads last and is already scoped to `[data-table-tools]`.

`components.css` does not exist until Task 4; a 404 on it is harmless and expected between these two tasks.

- [ ] **Step 4: Verify nothing regressed**

Run: `python scripts/smoke_templates_render.py`
Expected: `OK all 51 templates compile`, exit 0.

Then start the app and load two pages in a browser:

```bash
python -m uvicorn dreaming.main:app --port 8086 --reload
```

Open `http://localhost:8086/projects` and `http://localhost:8086/p/<slug>/`. Expected: the app still renders as before, marginally quieter borders. Nothing may be unstyled or white-on-white — if it is, a token failed to move across and the `:root` extraction dropped a line.

- [ ] **Step 5: Commit**

```bash
git add dreaming/static/tokens.css dreaming/static/app.css dreaming/templates/base.html
git commit -m "refactor(design): extract tokens.css as the single source of visual truth

Moves the :root block out of app.css and extends it with spacing, radius,
typography, density, and control tokens plus status border/strong variants.
Existing token names are unchanged -- table_tools.css and ~491 inline styles
depend on them. Surfaces and borders are retuned toward visual direction A."
```

---

### Task 4: Component layer

**Files:**
- Create: `dreaming/static/components.css`
- Modify: `dreaming/static/app.css` (move `.card-link`, `.pill-nav`/`.pill`, `.badge-*`, `.dot`, `.metric`, `.data-table`, `dialog.note-modal` out; keep base elements, sidebar shell, `.md-content`, and the `!important` block; refresh the stale banner comment, which still claims this file holds the component classes)
- Modify: `dreaming/static/tokens.css` (add `--shadow-brand` and `--metric-bar-w`, see Step 1)

**Interfaces:**
- Consumes: every token from Task 3.
- Produces: the class vocabulary Tasks 5–16 migrate templates onto — `.page-header` (+ `__titles`, `__title`, `__slug`, `__sub`, `__actions`), `.section-title`, `.btn` (+ `.btn-primary`, `.btn-danger`, `.btn-warn`, `.btn-ghost`, `.btn-sm`), `.toolbar` (+ `__spacer`, `__count`), `.banner` (+ `__title`, `__body`, `__actions`, `.banner-info`, `.banner-warn`, `.banner-danger`, `.banner-success`), `.card` (+ `.card--flush`), `.panel`, `.list-rows`, `.empty-state` (+ `__title`), `.field` (+ `__label`, `__hint`, `__control`, `.field-row`), `.num`, `.data-table.is-dense`. Existing class names (`.metric`, `.badge*`, `.pill*`, `.dot*`, `.data-table`, `.card-link`) keep their exact names and behaviour — they are moved, not renamed, because templates already use them.

- [ ] **Step 1: Create `dreaming/static/components.css`**

```css
/* ============================================================
   components.css — semantic component classes.

   RULE: no hex literal in this file. Colour arrives via var() from
   tokens.css. rgba(0,0,0,...) is allowed for shadows only.
   Enforced by scripts/check_css_tokens.py.
   ============================================================ */

/* ---------- Page header ---------- */
.page-header {
  display: flex; align-items: flex-end; justify-content: space-between;
  gap: var(--space-4); flex-wrap: wrap; margin-bottom: var(--space-5);
}
.page-header__titles { display: flex; align-items: baseline; gap: var(--space-3); flex-wrap: wrap; min-width: 0; }
.page-header__title { margin: 0; font-size: var(--text-h1); font-weight: 600; letter-spacing: -0.015em; color: var(--text-strong); }
.page-header__slug { font-family: var(--font-mono); font-size: var(--text-sm); color: var(--text-faint); }
.page-header__sub { margin: var(--space-1) 0 0; font-size: var(--text-base); color: var(--text-muted); }
.page-header__actions { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }

/* ---------- Section heading ---------- */
.section-title {
  margin: var(--space-5) 0 var(--space-2);
  font-size: var(--text-h2); font-weight: 600; color: var(--text-strong);
  display: flex; align-items: center; gap: var(--space-2);
}
.section-title:first-child { margin-top: 0; }

/* ---------- Buttons ---------- */
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: var(--space-1);
  font-family: inherit; font-size: var(--text-base); font-weight: 500; line-height: 1;
  min-height: var(--control-h); padding: 0 var(--space-3);
  border: 1px solid var(--border-muted); border-radius: var(--radius-sm);
  background: var(--bg-elevated); color: var(--text-body);
  white-space: nowrap; text-decoration: none; cursor: pointer;
  transition: background-color 120ms ease, border-color 120ms ease, color 120ms ease;
}
.btn:hover { background: var(--bg-hover); color: var(--text-strong); }
.btn:disabled, .btn[aria-disabled="true"] { cursor: not-allowed; opacity: 0.55; }

.btn-primary { background: var(--brand); border-color: transparent; color: var(--brand-on); font-weight: 600; }
.btn-primary:hover { background: var(--brand-hover); color: var(--brand-on); }

.btn-danger { background: var(--status-failed-soft); border-color: var(--status-failed-border); color: var(--status-failed); }
.btn-danger:hover { background: var(--status-failed-strong); color: var(--status-failed); }

.btn-warn { background: var(--status-timeout-soft); border-color: var(--status-timeout-border); color: var(--status-timeout); }
.btn-warn:hover { background: var(--status-timeout-strong); color: var(--status-timeout); }

.btn-ghost { background: transparent; border-color: transparent; color: var(--text-muted); }
.btn-ghost:hover { background: var(--bg-hover); color: var(--text-strong); }

.btn-sm { min-height: var(--control-h-sm); font-size: var(--text-sm); padding: 0 var(--space-2); }

/* ---------- Toolbar (search + reset + count above a table) ---------- */
.toolbar { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; margin-bottom: var(--space-2); }
.toolbar__spacer { flex: 1 1 auto; }
.toolbar__count { font-size: var(--text-sm); color: var(--text-faint); }

/* ---------- Banners ---------- */
.banner {
  display: flex; align-items: flex-start; gap: var(--space-3);
  padding: var(--space-3) var(--space-4); margin-bottom: var(--space-4);
  border: 1px solid var(--border-subtle); border-radius: var(--radius);
  background: var(--bg-card); color: var(--text-body);
  font-size: var(--text-base); line-height: 1.55;
}
.banner__body { flex: 1 1 auto; min-width: 0; }
.banner__title { margin: 0 0 var(--space-1); font-weight: 600; color: var(--text-strong); }
.banner__actions { flex: 0 0 auto; display: flex; align-items: center; gap: var(--space-2); }
.banner p { margin: 0 0 var(--space-1); }
.banner p:last-child { margin-bottom: 0; }

.banner-info { background: var(--status-running-soft); border-color: var(--status-running-border); }
.banner-info .banner__title { color: var(--status-running); }
.banner-warn { background: var(--status-timeout-soft); border-color: var(--status-timeout-border); }
.banner-warn .banner__title { color: var(--status-timeout); }
.banner-danger { background: var(--status-failed-soft); border-color: var(--status-failed-border); }
.banner-danger .banner__title { color: var(--status-failed); }
.banner-success { background: var(--status-success-soft); border-color: var(--status-success-border); }
.banner-success .banner__title { color: var(--status-success); }

/* ---------- Cards, panels, row lists ---------- */
.card {
  background: var(--bg-card); border: 1px solid var(--border-subtle);
  border-radius: var(--radius); padding: var(--space-4);
}
.card--flush { padding: 0; overflow: hidden; }
.panel {
  background: var(--bg-elevated); border: 1px solid var(--border-subtle);
  border-radius: var(--radius); padding: var(--space-3) var(--space-4);
}
.list-rows { list-style: none; margin: 0; padding: 0; }
.list-rows > li {
  display: flex; align-items: center; justify-content: space-between; gap: var(--space-3);
  padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--border-subtle);
}
.list-rows > li:last-child { border-bottom: 0; }

/* ---------- Empty state ---------- */
.empty-state {
  padding: var(--space-6) var(--space-4); text-align: center;
  border: 1px dashed var(--border-subtle); border-radius: var(--radius);
  background: var(--bg-card); color: var(--text-muted); font-size: var(--text-base);
}
.empty-state__title { margin: 0 0 var(--space-1); font-weight: 600; color: var(--text-body); }

/* ---------- Form fields ---------- */
.field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
.field__label { font-size: var(--text-sm); font-weight: 500; color: var(--text-muted); }
.field__hint { font-size: var(--text-sm); color: var(--text-faint); }
.field__control { width: 100%; min-height: var(--control-h); padding: 0 var(--space-2); border-radius: var(--radius-sm); }
.field-row { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }

/* ---------- Numerics: stop columns dancing between rows ---------- */
.num { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }

/* ============================================================
   Moved verbatim from app.css (same class names, tokenized).
   ============================================================ */

/* ---------- Card hover lift ---------- */
.card-link { border: 1px solid var(--border-subtle); transition: transform 150ms ease, box-shadow 150ms ease, border-color 150ms ease; }
.card-link:hover { transform: translateY(-1px); box-shadow: var(--shadow-card-hover); border-color: var(--border-muted); }

/* ---------- Pill nav ---------- */
.pill-nav {
  display: flex; flex-wrap: wrap; gap: var(--space-1); padding: var(--space-1);
  background: var(--bg-card); border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg); box-shadow: var(--shadow-card);
}
.pill {
  display: inline-flex; align-items: center; gap: var(--space-1);
  padding: var(--space-1) var(--space-3); border-radius: var(--radius-sm);
  font-size: var(--text-base); font-weight: 500; color: var(--text-muted);
  white-space: nowrap; transition: background-color 150ms ease, color 150ms ease;
}
.pill:hover { background: var(--bg-hover); color: var(--text-strong); }
.pill.is-active { background: var(--brand); color: var(--brand-on); font-weight: 600; box-shadow: var(--shadow-brand); }
.pill.is-active:hover { background: var(--brand-hover); color: var(--brand-on); }

/* ---------- Status badges ---------- */
.badge {
  display: inline-flex; align-items: center; gap: var(--space-1);
  padding: 0.125rem var(--space-2); border-radius: var(--radius-pill);
  font-size: var(--text-xs); font-weight: 600; letter-spacing: 0.01em;
}
.badge-success { background: var(--status-success-soft); color: var(--status-success); }
.badge-failed  { background: var(--status-failed-soft);  color: var(--status-failed); }
.badge-timeout { background: var(--status-timeout-soft); color: var(--status-timeout); }
.badge-running { background: var(--status-running-soft); color: var(--status-running); }
.badge-live    { background: var(--status-live-soft);    color: var(--status-live); }
.badge-neutral { background: var(--bg-hover); color: var(--text-muted); }

/* ---------- Live dot ---------- */
.dot { display: inline-block; width: var(--space-2); height: var(--space-2); border-radius: var(--radius-pill); background: currentColor; }
@media (prefers-reduced-motion: no-preference) {
  .dot-pulse { animation: dot-pulse 1.6s ease-in-out infinite; }
}
@keyframes dot-pulse {
  0%, 100% { box-shadow: 0 0 0 0 currentColor; opacity: 1; }
  50% { box-shadow: 0 0 0 4px transparent; opacity: 0.6; }
}

/* ---------- Metric tile ---------- */
.metric {
  position: relative; overflow: hidden;
  background: var(--bg-card); border: 1px solid var(--border-subtle);
  border-radius: var(--radius);
  /* Left inset clears the status bar so text never crowds it. Expressed as a
     relationship rather than a magic number: the bar's own width is the token. */
  padding: var(--space-3) var(--space-4) var(--space-3) calc(var(--space-4) + var(--metric-bar-w));
  box-shadow: var(--shadow-card);
}
.metric::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: var(--metric-bar-w); background: var(--text-faint); }
.metric.metric-success::before { background: var(--status-success); }
.metric.metric-failed::before  { background: var(--status-failed); }
.metric.metric-timeout::before { background: var(--status-timeout); }
.metric.metric-running::before { background: var(--status-running); }
.metric.metric-info::before    { background: var(--brand); }
.metric__label { font-size: var(--text-xs); text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-faint); font-weight: 500; }
.metric__value { margin-top: var(--space-1); font-size: 1.75rem; font-weight: 600; letter-spacing: -0.02em; color: var(--text-strong); font-variant-numeric: tabular-nums; }

/* ---------- Tables ---------- */
.data-table {
  width: 100%; background: var(--bg-card);
  border: 1px solid var(--border-subtle); border-radius: var(--radius);
  overflow: hidden; border-collapse: separate; border-spacing: 0;
  font-size: var(--row-font); color: var(--text-body);
}
.data-table thead th {
  text-align: left; font-size: var(--text-xs); font-weight: 600;
  letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-faint);
  padding: var(--row-pad-y) var(--row-pad-x);
  background: var(--bg-elevated); border-bottom: 1px solid var(--border-subtle);
}
.data-table tbody td { padding: var(--row-pad-y) var(--row-pad-x); border-bottom: 1px solid var(--border-subtle); vertical-align: middle; }
.data-table tbody tr:last-child td { border-bottom: 0; }
.data-table tbody tr:hover { background: var(--bg-hover); }

/* Dense mode: for tables that are scanned, not read. */
.data-table.is-dense { font-size: var(--row-font-dense); }
.data-table.is-dense thead th,
.data-table.is-dense tbody td { padding: var(--row-pad-y-dense) var(--row-pad-x-dense); }

/* ---------- Modal dialog ---------- */
dialog.note-modal {
  padding: 0; max-width: 56rem; width: calc(100% - 2rem);
  border: 1px solid var(--border-subtle); border-radius: var(--radius);
  background: var(--bg-card); color: var(--text-body); box-shadow: var(--shadow-modal);
}
dialog.note-modal::backdrop { background: rgba(0, 0, 0, 0.65); backdrop-filter: blur(2px); }
```

- [ ] **Step 2: Delete the moved rules from `app.css`**

Remove from `dreaming/static/app.css` exactly these blocks, which now live in `components.css`:

- `/* ---------- Card hover lift ---------- */` (`.card-link`, `.card-link:hover`)
- `/* ---------- Pill nav … ---------- */` (`.pill-nav`, `.pill`, `.pill:hover`, `.pill.is-active`, `.pill.is-active:hover`)
- `/* ---------- Status badges ---------- */` (`.badge`, all `.badge-*`)
- The `.dot`, `.dot-pulse` media query, and `@keyframes dot-pulse`
- `/* ---------- Metric tile ---------- */` (`.metric`, `.metric::before`, all `.metric.metric-*::before`)
- `/* ---------- Table polish ---------- */` (`.data-table` and its descendants)
- `dialog.note-modal` and `dialog.note-modal::backdrop`

**Keep** in `app.css`: the banner comment, `html`, `body`, `code/pre/.font-mono`, `.muted`, the focus rules, the form-element block, the scrollbar rules, the whole `/* ---------- Sidebar shell ---------- */` section including its media query, `button, [role="button"] { cursor: pointer; }` and the disabled rule, the `.md-content` section, and the `!important` compatibility block.

- [ ] **Step 3: Run the linter — the hex rule must now be live**

Run: `python scripts/check_css_tokens.py`

Expected: `OK components.css: no hex literals` (no longer the SKIP line). Template counters are unchanged from the Task 1 baseline — nothing has been migrated yet. Exit 1 is still correct at this point.

If hex literals are reported, replace each with the matching token. Do not add an exemption.

- [ ] **Step 4: Verify the app is visually unchanged**

Run: `python scripts/smoke_templates_render.py` — expected exit 0.

Then with the app running, open `http://localhost:8086/p/<slug>/` and confirm: metric tiles keep their coloured left bar, status badges keep their colours, the sessions table keeps its header and hover, the active pill keeps its indigo glow, and the confirm modal still opens (click any Delete).

**What may and may not change on screen.** This task moves rules onto the shared scale, so 1–2px shifts in spacing, radius, and table density are *expected* — that is the spacing ramp and the density tokens doing their job, and the plan's component inventory calls for exactly this realignment. What must **not** change is any *affordance*: a dropped shadow, a lost border, a vanished hover state, or a renamed class. If a value moved, check it landed on a scale token deliberately; if a declaration disappeared entirely, that is a defect.

**One qualification on "dropped affordance", added after Task 6.** The test is whether a *perceptible* affordance is lost, not whether a declaration vanished from the source. Light-theme leftovers that never rendered on this dark background are not affordances — they are the artifacts this wave exists to remove. The worked example: `shadow-sm` is `0 1px 2px rgb(0 0 0 / 0.05)`; composited over `--bg-app` (`#0a0e17`) it shifts each channel by less than one unit, below display quantization, and it arrived as part of the `bg-white … border-slate-200 shadow-sm divide-slate-100` light-theme cluster. Removing it with the rest of that cluster is the task working, not failing. When invoking this qualification, do the arithmetic and show it — "probably invisible" is not the same claim as "sub-perceptual, here is the composite".

- [ ] **Step 5: Commit**

```bash
git add dreaming/static/components.css dreaming/static/app.css
git commit -m "feat(design): add components.css with the semantic component layer

New: page-header, section-title, btn (+primary/danger/warn/ghost/sm), toolbar,
banner (+info/warn/danger/success), card, panel, list-rows, empty-state, field,
num, and data-table.is-dense.

Moved from app.css unchanged in name and behaviour: card-link, pill-nav/pill,
badge-*, dot, metric, data-table, dialog.note-modal -- now tokenized. app.css
keeps base elements, the sidebar shell, .md-content, and the !important
compatibility block (removed in the final task of this wave)."
```

---

### Task 5: Migrate the shell

The shell establishes `.page-header` for all 32 templates that extend `_project_layout.html`. It goes first so every later batch inherits it.

**Files:**
- Modify: `dreaming/templates/base.html` (flash banner, lines 54-60)
- Modify: `dreaming/templates/_project_layout.html` (whole file)
- Modify: `dreaming/templates/_sidebar.html`
- Modify: `dreaming/static/app.css` (sidebar active-item colours → tokens, Step 4)

**Interfaces:**
- Consumes: `.banner`, `.page-header*` from Task 4.
- Produces: the `.page-header` markup shape every page-level template copies.

- [ ] **Step 1: Record the before-counts for these three files**

Run: `python scripts/check_css_tokens.py`
Note the rows for `base.html`, `_project_layout.html`, `_sidebar.html`. They must reach 0 by Step 4.

- [ ] **Step 2: Migrate `base.html`'s flash banner**

Replace lines 54–60:

```html
      {% if flash %}
      <div class="px-8 pt-4">
        <div class="rounded-lg border p-4" style="background: var(--brand-soft); border-color: rgba(99,102,241,0.35);">
          <p class="text-sm" style="color: #c7d2fe;">{{ flash.message }}</p>
        </div>
      </div>
      {% endif %}
```

with:

```html
      {% if flash %}
      <div class="px-8 pt-4">
        <div class="banner banner-info">
          <div class="banner__body">{{ flash.message }}</div>
        </div>
      </div>
      {% endif %}
```

- [ ] **Step 3: Migrate `_project_layout.html`**

Replace the whole file with:

```html
{% extends "base.html" %}
{% block content %}
<header class="page-header">
  <div class="page-header__titles">
    <h1 class="page-header__title">{{ project.label }}</h1>
    <span class="page-header__slug">{{ project.slug }}</span>
  </div>
</header>
{% block project_content %}{% endblock %}
{% endblock %}
```

- [ ] **Step 4: Migrate `_sidebar.html`**

Apply the canonical replacement table from Global Constraints. The sidebar's own `.app-sidebar__*` classes stay — they live in `app.css` and are already tokenized. Only remove inline `style="…"` attributes and colour utilities, replacing each with the sidebar class that already covers it (or a `.btn`/`.badge` where the element is genuinely a button or badge).

Then, in `dreaming/static/app.css`, replace the two hardcoded hexes in the sidebar's active-item rules with tokens. `--brand-fg` (`#c7d2fe`, Task 3) already holds the text colour exactly. The icon colour `#a5b4fc` has **no** existing token — add one to `tokens.css` in the Brand group rather than reaching for `--brand-hover`, which is `#818cf8` and visibly darker:

```css
  --brand-fg-dim: #a5b4fc;   /* active icon: one step down from --brand-fg */
```

```css
.app-sidebar__nav-link.is-active { background: var(--brand-soft); color: var(--brand-fg); }
.app-sidebar__nav-link.is-active svg { opacity: 1; color: var(--brand-fg-dim); }
```

Also add a `.faint` utility next to the existing `.muted` in `app.css`, since migration keeps meeting text that was `--text-faint` and there is no class for it:

```css
.faint { color: var(--text-faint); }
```

Use it for the sidebar's "pick a project" hint, which is `--text-faint` today — `.muted` is a different, lighter grey and would drift the colour.

(`app.css` is not covered by the linter's no-hex rule, so this is a deliberate tidy-up in the task that already owns the shell, not a linter requirement.)

- [ ] **Step 5: Verify**

Run: `python scripts/check_css_tokens.py`
Expected: `base.html`, `_project_layout.html`, `_sidebar.html` no longer appear in either counter list. The grand totals dropped by the amounts noted in Step 1.

Run: `python scripts/smoke_templates_render.py` — expected exit 0.

In a browser, open `http://localhost:8086/p/<slug>/` and check: the sidebar renders with its icons and active-item highlight, and the project title and slug sit on one baseline.

**Do not try to verify the flash banner here.** `base.html`'s `{% if flash %}` block is unreachable: `dreaming/lib/flash.py` sets a cookie, `read_flash` is called by nothing, no route puts `flash` in a template context, and `main.py` registers no context processor. Flash messages are consumed entirely client-side by `_app_modal.html`. The block is migrated for consistency, not because it renders. Its `.banner-info` styling is blue rather than the brand indigo the original markup used — correct for the class, whose real consumers from Task 6 onward are the `bg-sky-50` informational banners, and moot for a block that cannot render.

- [ ] **Step 6: Commit**

```bash
git add dreaming/templates/base.html dreaming/templates/_project_layout.html dreaming/templates/_sidebar.html dreaming/static/app.css
git commit -m "refactor(design): migrate the shell to the component layer

base.html flash banner -> .banner-info, _project_layout.html header ->
.page-header, _sidebar.html off inline styles. Establishes the page-header
shape the 32 templates extending _project_layout inherit.

app.css sidebar active-item colours move to --brand-fg / --brand-hover,
removing the last hardcoded hexes from the shell."
```

---

### Task 6: Migrate `project_dashboard.html`

First of the three acceptance-gate screens. It exercises banners, metrics, tiles, toolbars, dense tables, and every button variant at once.

**Files:**
- Modify: `dreaming/templates/project_dashboard.html`

**Interfaces:**
- Consumes: everything from Task 4; the `.page-header` shape from Task 5.
- Produces: nothing new. If a component turns out to be missing or wrong, fix it in `components.css` as part of *this* task rather than working around it in the template.

- [ ] **Step 1: Record the before-count**

Run: `python scripts/check_css_tokens.py` and note the `project_dashboard.html` rows.

- [ ] **Step 2: Migrate the bootstrap banner (lines 5-31)**

The `border-amber-400 bg-amber-50` block is one of the two known rendering bugs — it currently paints a near-white box on the dark app. Convert the wrapper to `<div class="banner banner-warn">` with a `<div class="banner__body">`, give the heading `class="banner__title"`, drop every `text-amber-900` and `text-blue-600` utility (the banner and `.md-content`-style link colours cover them), and turn the submit into `class="btn btn-warn"`.

- [ ] **Step 3: Migrate the metric row (lines 34-56)**

Each tile becomes:

```html
  <div class="metric metric-success">
    <div class="metric__label">{{ "p.metrics.success" | t(locale=locale) }}</div>
    <div class="metric__value" style="color: var(--status-success);">{{ stats.success or 0 }}</div>
  </div>
```

except the inline `style` must go too — add these one-line rules to `components.css` instead and use them:

```css
.metric.metric-success .metric__value { color: var(--status-success); }
.metric.metric-failed  .metric__value { color: var(--status-failed); }
.metric.metric-timeout .metric__value { color: var(--status-timeout); }
.metric.metric-running .metric__value { color: var(--status-running); }
```

so the markup is just `<div class="metric__value">{{ stats.success or 0 }}</div>`.

- [ ] **Step 4: Migrate the stale-orphans banner (lines 72-84)**

`border-amber-400 bg-amber-50` → `<div class="banner banner-warn">`, with the message in `.banner__body`, the form in `.banner__actions`, and the button as `class="btn btn-sm btn-warn"`.

- [ ] **Step 5: Migrate the headings, toolbar, and table (lines 86-162)**

- `<h2 class="font-semibold text-slate-900 mb-2">` → `<h2 class="section-title">` (both occurrences, lines 86 and 164).
- The search/reset wrapper `<div class="mb-2 flex items-center gap-2">` → `<div class="toolbar">`; the reset button → `class="btn btn-sm"`.
- `<table class="data-table" …>` → `<table class="data-table is-dense" …>` — this table is scanned, not read.
- The `started_at` cell: `class="text-xs muted whitespace-nowrap"` → `class="num muted whitespace-nowrap"`. Reuse the existing `.muted` from `app.css` — do **not** add a second class with the same declaration.
- The `log` link → `class="btn btn-sm"`; `Stop`/`Force-close` → `class="btn btn-sm btn-warn"`; `Delete` → `class="btn btn-sm btn-danger"`.
- Leave every `data-*`, `data-confirm`, `action`, and `| t(…)` call byte-for-byte unchanged.

- [ ] **Step 6: Migrate the active-runs list (lines 168-185)**

`<ul class="bg-white rounded-lg border border-slate-200 shadow-sm divide-y divide-slate-100">` → `<ul class="card card--flush list-rows">`; drop the per-`li` flex utilities (`.list-rows > li` covers them); the key span → `class="num"`; the Stop button → `class="btn btn-sm btn-warn"`. The `{% else %}` branch's `<p class="muted">` → `<p class="empty-state">`.

- [ ] **Step 7: Verify**

Run: `python scripts/check_css_tokens.py`
Expected: `project_dashboard.html` appears in neither counter list.

Run: `python scripts/smoke_templates_render.py` — expected exit 0.

In a browser at `http://localhost:8086/p/<slug>/`, confirm each of these:
- No light/white box anywhere on the page (the bootstrap and stale-orphan banners are now dark amber).
- Metric values keep their status colours.
- The sessions table is visibly denser than before, and the timestamp column no longer shifts between rows.
- Sorting and the search box still work (`table_tools.js` must be unaffected).
- `log`, `Stop`, and `Delete` are three visually distinct buttons of the same height and shape.
- Clicking `Delete` still opens the confirm modal with the same text.

- [ ] **Step 8: Commit**

```bash
git add dreaming/templates/project_dashboard.html dreaming/static/components.css
git commit -m "refactor(design): migrate project_dashboard.html to the component layer

Fixes the light bg-amber-50 banners that rendered as white boxes on the dark
app. Sessions table moves to is-dense with mono timestamps. Adds the four
metric__value status colours to components.css so the template carries no
colour of its own."
```

---

### Task 7: Migrate `project_orchestration_list.html`

The single heaviest interactive template: 54 inline styles, 28KB, and the run-detail UI lives here (`project_orchestration_detail.html` is dead — see Task 13).

**Files:**
- Modify: `dreaming/templates/project_orchestration_list.html`

**Interfaces:**
- Consumes: everything from Task 4. Do not touch `orchestration_swimlane.css` or `orchestration_stream.js`.
- Produces: nothing new.

- [ ] **Step 1: Record the before-count**

Run: `python scripts/check_css_tokens.py` and note the `project_orchestration_list.html` rows (expect ~54 inline styles).

- [ ] **Step 2: Migrate the file**

Apply the canonical replacement table from Global Constraints throughout. Specific to this file:
- The run table gets `class="data-table is-dense"`; run ids, durations, and timestamps get `class="num"`.
- `bg-sky-50` / `text-sky-900` blocks → `<div class="banner banner-info">`.
- Any element already styled through `orchestration_swimlane.css` keeps its swimlane class untouched — remove only inline `style` and colour utilities that duplicate it.
- SSE wiring (`hx-*`, `data-*`, element ids consumed by `orchestration_stream.js`) must survive byte-for-byte. Grep the JS for any id or class it queries before removing a class:
  `grep -oE "(getElementById|querySelector(All)?)\([^)]*\)" dreaming/static/orchestration_stream.js`

- [ ] **Step 3: Verify**

Run: `python scripts/check_css_tokens.py` — `project_orchestration_list.html` gone from both lists.
Run: `python scripts/smoke_templates_render.py` — exit 0.

In a browser at `http://localhost:8086/p/<slug>/orchestration`, confirm: the run list renders, no light boxes remain, and — critically — **start a run and watch the live stream update**. If the SSE view stops updating, a class or id the JS queries was removed in Step 2.

- [ ] **Step 4: Commit**

```bash
git add dreaming/templates/project_orchestration_list.html
git commit -m "refactor(design): migrate project_orchestration_list.html

Heaviest template in the tree (54 inline styles). SSE element ids and hx-*
attributes preserved verbatim; live stream verified against a real run."
```

---

### Task 7A: Fix `orchestration_swimlane.css` — added mid-wave

**Why this task exists.** The spec and this plan both asserted that `orchestration_swimlane.css` is "already token-driven and feature-scoped" and left it untouched. **That assertion was false.** Reading it during Task 7 turned up nine hardcoded light-theme foreground colours and one reference to a token that does not exist. This is the wave's own bug class — the spec's Problem section names exactly this — sitting on the screen Task 7 just migrated. Excluding it was based on a premise, not a reading.

**Files:**
- Modify: `dreaming/static/orchestration_swimlane.css`
- Modify: `dreaming/static/tokens.css` (two new tokens, see below)

**Interfaces:**
- Consumes: the status tokens from Task 3.
- Produces: nothing new for later tasks. Class names, selectors, and every non-colour property stay exactly as they are — `orchestration_stream.js` and `project_orchestration_list.html` both depend on these class names.

- [ ] **Step 1: Add the two missing tokens**

Neither an orange nor a purple foreground exists in `tokens.css`. Add to the status group:

```css
  --status-cancelled: #fb923c;   /* cancelled / stopped pills */
  --skill-fg: #d8b4fe;           /* skill badges under activity chips */
```

- [ ] **Step 2: Replace every light-theme foreground**

These nine colours are all dark text intended for light backgrounds. Each sits on an alpha-tinted overlay over the dark app surface, so each currently fails WCAG AA — `.status-failed` measures about 2.4:1. Replace **only the `color:` values**; leave every `border-color` and `background` exactly as they are, since those are alpha tints that read correctly on dark.

| Selector | Current | Replace with |
|---|---|---|
| `.status-running, .status-active` | `#0369a1` | `var(--status-running)` |
| `.status-completed, .status-done, .status-approved` | `#047857` | `var(--status-success)` |
| `.status-pending, .status-queued` | `#475569` | `var(--text-muted)` |
| `.status-blocked` | `#92400e` | `var(--status-timeout)` |
| `.status-rejected, .status-failed` | `#b91c1c` | `var(--status-failed)` |
| `.status-cancelled, .status-stopped` | `#9a3412` | `var(--status-cancelled)` |
| `.stage-icon` | `#4338ca` | `var(--brand-fg)` |
| `.stage-meta` | `#6b7280` | `var(--text-faint)` |
| `.swim-agent-role` | `#6b7280` | `var(--text-faint)` |
| `.skill-badge` | `#7e22ce` | `var(--skill-fg)` |
| `.sse-indicator.connected` | `#047857` | `var(--status-success)` |
| `.sse-indicator.done` | `#4338ca` | `var(--brand-fg)` |
| `.sse-indicator.disconnected` | `#b91c1c` | `var(--status-failed)` |
| `.sse-indicator.polling` | `#92400e` | `var(--status-timeout)` |

- [ ] **Step 3: Fix the undefined token**

Line 32's `.swimlanes-wrap` sets `background: var(--bg-surface)`. **No such token has ever existed** — the surface token is `--bg-elevated`, and the Tailwind config's `surface` key was never mirrored into CSS. The declaration currently resolves to nothing, leaving the wrapper transparent. Change it to `var(--bg-card)`, which is what a bordered content wrapper uses everywhere else in this app.

- [ ] **Step 4: Verify**

Run `python scripts/check_css_tokens.py` — totals must be **unchanged** at 401 / 421. This task touches no template. `components.css` must still report no hex literals; the two new literals live in `tokens.css`, where literals belong.

Run `python scripts/smoke_templates_render.py` — 51 templates, 45 routes, exit 0.

Then confirm by grep that none of the nine replaced hexes survive anywhere under `dreaming/static/`:

```bash
grep -nE '#(0369a1|047857|475569|92400e|b91c1c|9a3412|4338ca|6b7280|7e22ce)' dreaming/static/
```

Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add dreaming/static/orchestration_swimlane.css dreaming/static/tokens.css
git commit -m "fix(design): stop the swimlane rendering light-theme text on dark

The spec claimed this file was already token-driven. It was not: nine
hardcoded foreground colours meant for light backgrounds, of which
.status-failed measured about 2.4:1 against its own tinted background, well
under the 4.5:1 floor. Backgrounds and borders were already alpha tints and
are untouched.

Also fixes .swimlanes-wrap referencing --bg-surface, a token that has never
existed, which left the wrapper transparent instead of carded."
```

---

### Task 8: Migrate `project_findings.html` — acceptance gate

**Files:**
- Modify: `dreaming/templates/project_findings.html`

**Interfaces:**
- Consumes: everything from Task 4.
- Produces: **the acceptance gate for the component API.** After this task, three of the most complex screens are migrated. Stop and review before the bulk migration begins: if a component is awkward here, fixing it now costs 3 templates instead of 48.

- [ ] **Step 1: Record the before-count**

Run: `python scripts/check_css_tokens.py`, note the `project_findings.html` rows.

- [ ] **Step 2: Migrate the file**

Apply the canonical replacement table. Specific to this file:
- The findings table gets `class="data-table is-dense"`.
- This template is a `table_tools` consumer with a per-column filter row and a custom `refs` predicate. Every `data-tt-*`, `data-filter-col`, `data-has-*`, and `data-filter-row` attribute must survive unchanged.
- Priority badges keep their `.badge-*` classes.
- Bulk-selection checkboxes and their `bulk:rows-changed` wiring must survive.

- [ ] **Step 3: Verify**

Run: `python scripts/check_css_tokens.py` — file gone from both lists.
Run: `python scripts/smoke_templates_render.py` — exit 0.

In a browser at `http://localhost:8086/p/<slug>/findings`, confirm: column sorting, the per-column filter row, the refs filter, the "shown N of M" count, the empty state, bulk selection, and `localStorage` persistence (filter, reload, filter is restored) all still work.

- [ ] **Step 4: Review gate — stop here**

Report to the reviewer:
- current linter totals (started at 491 inline / 464 utilities),
- any component that needed changing while migrating these three screens,
- any markup pattern that had no component and was worked around.

Do not start Task 9 until the component API is confirmed. This is the cheapest moment to change it.

- [ ] **Step 5: Commit**

```bash
git add dreaming/templates/project_findings.html
git commit -m "refactor(design): migrate project_findings.html

Completes the three acceptance-gate screens. table_tools data-attributes,
the custom refs predicate, and bulk-selection wiring preserved and verified."
```

---

### Task 9: Migrate the AI-usage pair

Two templates, 170 inline styles between them — the heaviest remaining pair, and near-identical to each other.

**Files:**
- Modify: `dreaming/templates/project_ai_usage.html` (92 inline styles)
- Modify: `dreaming/templates/global_ai_usage.html` (78 inline styles)

**Interfaces:**
- Consumes: everything from Task 4.
- Produces: nothing new.

- [ ] **Step 1: Record before-counts**

Run: `python scripts/check_css_tokens.py`, note both rows.

- [ ] **Step 2: Migrate both files**

Apply the canonical replacement table. Specific to this pair:
- These are cost/usage dashboards: every number, currency amount, and token count gets `class="num"`.
- Summary tables get `class="data-table is-dense"`.
- Any bar/meter width driven by `style="width: {{ … }}%"` is a **dynamic** style and stays — it is exempt from the linter. Move only its colour and height into a component class.
- Migrate the two files in the same pass so the shared patterns get identical treatment.

- [ ] **Step 3: Verify**

Run: `python scripts/check_css_tokens.py` — both files gone from the utility list; any remaining inline styles on them must be dynamic only (the linter will not report them).
Run: `python scripts/smoke_templates_render.py` — exit 0.

Browser: `http://localhost:8086/ai-usage` and `http://localhost:8086/p/<slug>/ai-usage`. Confirm the bars still show proportional widths and the number columns line up.

- [ ] **Step 4: Commit**

```bash
git add dreaming/templates/project_ai_usage.html dreaming/templates/global_ai_usage.html
git commit -m "refactor(design): migrate the AI-usage templates

170 inline styles between them. Dynamic bar widths (style=\"width: {{ }}%\")
kept as-is; only their colour and height moved into component classes."
```

---

### Task 9A: Teach the linter to catch undefined classes — added mid-wave

**Why this task exists.** Task 9 shipped nine references to a `.strong` class that was never defined. Every verification passed: the colour check saw no palette utility, the compile check saw valid Jinja, the preservation check saw the attributes survive. **A class name is just a string to all three.** With eight migration tasks left, each free to invent component classes, this gap will recur — and it fails silently, which is the worst way to fail.

**Files:**
- Modify: `scripts/check_css_tokens.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: a fourth assertion in the same CLI. Tasks 10-16 gain a check that catches a class they reference but forget to define.

- [ ] **Step 1: Add the assertion**

Append to `scripts/check_css_tokens.py`. The rule: a class token in a template must either be defined in this project's own CSS, or be Tailwind-shaped. Anything else is very likely a class someone meant to write and did not.

```python
# ---------------------------------------------------------------- assertion 4
# Every class a template references must be defined in this project's CSS or be
# a Tailwind utility. The wave's own failure mode was nine references to a
# `.strong` that existed nowhere: the colour check passed (no palette utility),
# the compile check passed (valid Jinja), the preservation check passed
# (attributes survived). A class name is just a string to all of them.

CSS_SOURCES = [
    ROOT / "dreaming" / "static" / "app.css",
    ROOT / "dreaming" / "static" / "components.css",
    ROOT / "dreaming" / "static" / "table_tools.css",
    ROOT / "dreaming" / "static" / "orchestration_swimlane.css",
]

CLASS_ATTR = re.compile(r'class\s*=\s*"([^"]*)"')
CLASS_DEF = re.compile(r"\.(-?[A-Za-z_][\w-]*)")

# Tailwind utilities that stand alone, with no value suffix.
TW_EXACT = {
    "flex", "grid", "block", "inline", "inline-block", "inline-flex", "hidden",
    "table", "contents", "relative", "absolute", "fixed", "sticky", "static",
    "truncate", "italic", "underline", "uppercase", "lowercase", "capitalize",
    "container", "border", "rounded", "shadow", "ring", "outline", "transition",
    "transform", "resize", "invisible", "visible", "antialiased", "sr-only",
    "overflow-auto", "overflow-hidden", "overflow-x-auto", "overflow-y-auto",
}

# Roots Tailwind owns; a token is Tailwind-shaped if it starts with one of
# these followed by "-".
TW_ROOTS = (
    "p", "px", "py", "pt", "pb", "pl", "pr", "m", "mx", "my", "mt", "mb", "ml",
    "mr", "w", "h", "min", "max", "text", "bg", "border", "rounded", "shadow",
    "gap", "space", "grid", "col", "row", "items", "justify", "self", "place",
    "flex", "order", "opacity", "z", "top", "bottom", "left", "right", "inset",
    "overflow", "whitespace", "break", "font", "leading", "tracking", "list",
    "divide", "ring", "cursor", "select", "transition", "duration", "ease",
    "translate", "scale", "rotate", "animate", "aspect", "object", "align",
    "from", "to", "via", "fill", "stroke", "backdrop", "filter", "blur",
)

TW_VARIANTS = (
    "sm:", "md:", "lg:", "xl:", "2xl:", "hover:", "focus:", "focus-visible:",
    "active:", "disabled:", "group-hover:", "dark:", "first:", "last:",
    "odd:", "even:", "print:", "motion-safe:", "motion-reduce:",
)


def _defined_classes() -> set[str]:
    names: set[str] = set()
    for path in CSS_SOURCES:
        if path.exists():
            names |= set(CLASS_DEF.findall(path.read_text(encoding="utf-8")))
    return names


def _is_tailwind(token: str) -> bool:
    for variant in TW_VARIANTS:
        if token.startswith(variant):
            token = token[len(variant):]
            break
    if token in TW_EXACT:
        return True
    head = token.split("-", 1)[0]
    return head in TW_ROOTS


def _undefined_classes(defined: set[str]) -> dict[str, set[str]]:
    offenders: dict[str, set[str]] = {}
    for tpl in sorted(TEMPLATES.rglob("*.html")):
        rel = tpl.relative_to(TEMPLATES).as_posix()
        for attr in CLASS_ATTR.findall(tpl.read_text(encoding="utf-8")):
            if "{{" in attr or "{%" in attr:
                continue  # class list is built by Jinja; not statically knowable
            for token in attr.split():
                if token in defined or _is_tailwind(token):
                    continue
                offenders.setdefault(rel, set()).add(token)
    return offenders
```

Wire it into `main()` after the inline-style report, before the final verdict:

```python
    undefined = _undefined_classes(_defined_classes())
    if undefined:
        total = sum(len(v) for v in undefined.values())
        print(f"Classes referenced but never defined: {total}")
        for name, tokens in sorted(undefined.items()):
            print(f"  {name}: {', '.join(sorted(tokens))}")
        failed = True
    else:
        print("OK every referenced class is defined or a Tailwind utility")
```

- [ ] **Step 2: Prove it catches the real bug**

Temporarily remove the `.strong` rule from `app.css`, run the linter, confirm it names `.strong` in both AI-usage templates, then restore it:

```bash
python -c "import pathlib; p=pathlib.Path('dreaming/static/app.css'); t=p.read_text(encoding='utf-8'); p.write_text(t.replace('.strong { color: var(--text-strong); }\n', ''), encoding='utf-8')"
python scripts/check_css_tokens.py
git checkout -- dreaming/static/app.css
```

Expected: the middle command lists `strong` under both `project_ai_usage.html` and `global_ai_usage.html`. **A check that cannot fail is not a check** — if it stays silent, the wiring is wrong.

- [ ] **Step 3: Run it against the real tree and triage**

```bash
python scripts/check_css_tokens.py
```

The colour and inline-style totals must be unchanged at **356 / 250** — this task touches no template or stylesheet.

The new assertion will very likely report tokens on unmigrated templates. **Read every one before deciding what to do.** Two outcomes are legitimate:

- A genuinely undefined class → a real bug this check was built to find. Report it; do not fix it here, since unmigrated templates belong to later tasks.
- A Tailwind utility whose root is missing from `TW_ROOTS`, or a standalone utility missing from `TW_EXACT` → widen the list and re-run.

Do **not** widen the lists to silence a token you have not identified. The whole value of this check is that it fails loudly on the unknown; an over-broad allowlist turns it back into the silence it was built to replace. List every token you allowlisted and why.

- [ ] **Step 4: Commit**

```bash
git add scripts/check_css_tokens.py
git commit -m "chore(design): fail when a template references an undefined class

Task 9 shipped nine references to a .strong that existed in no stylesheet.
The colour check saw no palette utility, the compile check saw valid Jinja, and
the preservation check saw the attributes survive -- a class name is just a
string to all three, so the emphasis silently vanished.

A class token now has to be defined in this project's own CSS or be
Tailwind-shaped. Jinja-built class lists are skipped, being unknowable
statically."
```

---

### Task 10: Migrate review, kanban, and the loop-template view

**Files:**
- Modify: `dreaming/templates/project_review.html` (27 inline styles)
- Modify: `dreaming/templates/project_kanban.html` (23)
- Modify: `dreaming/templates/project_loops_template_view.html` (21)

**Interfaces:**
- Consumes: everything from Task 4.
- Produces: nothing new.

- [ ] **Step 1: Record before-counts**

Run: `python scripts/check_css_tokens.py`, note the three rows.

- [ ] **Step 2: Migrate all three**

Apply the canonical replacement table. Specific notes:
- `project_kanban.html`: columns are layout — keep the Tailwind grid/flex classes, replace only card chrome with `.card` and column headers with `.section-title`.
- `project_review.html`: verdict/score chips become `.badge-*` by status.
- `project_loops_template_view.html`: the template body preview keeps `.md-content` (owned by `app.css`); wrap it in `.card`.

- [ ] **Step 3: Verify**

Run: `python scripts/check_css_tokens.py` — all three gone from both lists.
Run: `python scripts/smoke_templates_render.py` — exit 0.
Browser: `/p/<slug>/review`, `/p/<slug>/kanban`, `/p/<slug>/loops/templates/<tpl_slug>`.

- [ ] **Step 4: Commit**

```bash
git add dreaming/templates/project_review.html dreaming/templates/project_kanban.html dreaming/templates/project_loops_template_view.html
git commit -m "refactor(design): migrate review, kanban, and loop-template view"
```

---

### Task 11: Migrate evolutions, cascade costs, and the AI-radar card

**Files:**
- Modify: `dreaming/templates/project_evolutions.html` (20 inline styles)
- Modify: `dreaming/templates/project_cascade_costs.html` (19)
- Modify: `dreaming/templates/_ai_radar_card.html` (19)

**Interfaces:**
- Consumes: everything from Task 4.
- Produces: nothing new.

- [ ] **Step 1: Record before-counts**

Run: `python scripts/check_css_tokens.py`, note the three rows.

- [ ] **Step 2: Migrate all three**

Apply the canonical replacement table. Specific notes:
- `project_evolutions.html` is a `table_tools` consumer (`data-evo-*` attributes) — preserve every data attribute and give the table `is-dense`.
- `project_cascade_costs.html`: all cost figures get `class="num"`; the table gets `is-dense`.
- `_ai_radar_card.html` is an include used by `ai_radar.html` and `project_ai_radar.html`; migrating it changes both pages, so check both in Step 3.

- [ ] **Step 3: Verify**

Run: `python scripts/check_css_tokens.py` — all three gone from both lists.
Run: `python scripts/smoke_templates_render.py` — exit 0.
Browser: `/p/<slug>/evolutions` (confirm sort/filter still work), `/p/<slug>/cascade-costs`, `/ai-radar`, and `/p/<slug>/ai-radar`.

- [ ] **Step 4: Commit**

```bash
git add dreaming/templates/project_evolutions.html dreaming/templates/project_cascade_costs.html dreaming/templates/_ai_radar_card.html
git commit -m "refactor(design): migrate evolutions, cascade costs, AI-radar card

_ai_radar_card.html is shared by ai_radar.html and project_ai_radar.html; both
pages verified."
```

---

### Task 12: Migrate the list views

Eight list pages that share one shape: page header, toolbar, table.

**Files:**
- Modify: `dreaming/templates/project_ideas.html`
- Modify: `dreaming/templates/project_plans.html`
- Modify: `dreaming/templates/project_tech_debt.html`
- Modify: `dreaming/templates/project_topics.html`
- Modify: `dreaming/templates/project_notes.html`
- Modify: `dreaming/templates/project_contracts.html`
- Modify: `dreaming/templates/project_sidecar_findings.html`
- Modify: `dreaming/templates/project_wiki.html`

**Interfaces:**
- Consumes: everything from Task 4.
- Produces: nothing new.

- [ ] **Step 1: Record before-counts**

Run: `python scripts/check_css_tokens.py`, note all eight rows.

- [ ] **Step 2: Migrate all eight**

Apply the canonical replacement table. Every table here is scanned, so all eight get `class="data-table is-dense"`. Specific notes:
- `project_ideas.html` is a `table_tools` consumer (`data-ideas-*`) — preserve every data attribute.
- `project_topics.html` contains `bg-amber-*` blocks — those become `.banner-warn` and are part of the known light-island bug.
- Each page's `{% else %}` / no-rows branch becomes `.empty-state`.
- `project_ideas.html` gained a `created` column (sortable date header, `YYYY-MM-DD` filter input, `data-created` row attribute) in commit `d01ea48`, which is already in this branch. Migrate that column like any other: the header keeps `data-sort-col="created" data-sort-type="date"`, the filter input keeps `data-filter-col="created"`, and the cell becomes `class="num muted"`.

- [ ] **Step 3: Verify**

Run: `python scripts/check_css_tokens.py` — all eight gone from both lists.
Run: `python scripts/smoke_templates_render.py` — exit 0.
Run: `python scripts/check_i18n.py` — exit 0 (no string was touched).
Browser: visit all eight — `/p/<slug>/` + `ideas`, `plans`, `tech-debt`, `topics`, `notes`, `contracts`, `sidecar-findings`, `wiki`. On `ideas`, confirm sort/filter still work.

- [ ] **Step 4: Commit**

```bash
git add dreaming/templates/project_ideas.html dreaming/templates/project_plans.html dreaming/templates/project_tech_debt.html dreaming/templates/project_topics.html dreaming/templates/project_notes.html dreaming/templates/project_contracts.html dreaming/templates/project_sidecar_findings.html dreaming/templates/project_wiki.html
git commit -m "refactor(design): migrate the eight list views

All get data-table is-dense and .empty-state. project_topics.html amber blocks
were part of the light-island bug and are now .banner-warn."
```

---

### Task 13: Migrate the detail views

**Files:**
- Modify: `dreaming/templates/project_findings_detail.html`
- Modify: `dreaming/templates/project_ideas_detail.html`
- Modify: `dreaming/templates/project_plans_detail.html`
- Modify: `dreaming/templates/project_contracts_detail.html`
- Modify: `dreaming/templates/project_wiki_health.html`
- Modify: `dreaming/templates/session_log.html`
- Modify: `dreaming/templates/project_orchestration_detail.html`

**Interfaces:**
- Consumes: everything from Task 4.
- Produces: nothing new.

**Note on `project_orchestration_detail.html`:** it is dead code — the run-detail UI lives in `project_orchestration_list.html`, and `scripts/smoke_table_tools.py` already allow-lists it as "Dead/unused template". It is migrated anyway (cheaply) because the linter scans it and the wave's exit condition is zero. Do **not** delete it in this wave; removing dead templates is a separate decision.

- [ ] **Step 1: Record before-counts**

Run: `python scripts/check_css_tokens.py`, note all seven rows.

- [ ] **Step 2: Migrate all seven**

Apply the canonical replacement table. Specific notes:
- Detail bodies rendered from Markdown keep `.md-content` (owned by `app.css`); wrap each in `.card`.
- `session_log.html` contains `bg-amber-*` blocks — part of the light-island bug, now `.banner-warn`. Its log body is preformatted text: keep `<pre>`, give the wrapper `.card card--flush`, and add `class="num"` to any timestamp gutter.
- Back-links and action buttons become `.btn` / `.btn-sm`.

- [ ] **Step 3: Verify**

Run: `python scripts/check_css_tokens.py` — all seven gone from both lists.
Run: `python scripts/smoke_templates_render.py` — exit 0.
Browser: open one finding, one idea, one plan, one contract, `/p/<slug>/wiki-health`, and one session log (via the `log` button on the dashboard). Confirm the log page still scrolls and its monospace body is intact.

- [ ] **Step 4: Commit**

```bash
git add dreaming/templates/project_findings_detail.html dreaming/templates/project_ideas_detail.html dreaming/templates/project_plans_detail.html dreaming/templates/project_contracts_detail.html dreaming/templates/project_wiki_health.html dreaming/templates/session_log.html dreaming/templates/project_orchestration_detail.html
git commit -m "refactor(design): migrate the detail views

session_log.html amber blocks were part of the light-island bug.
project_orchestration_detail.html is dead code (already allow-listed in
smoke_table_tools.py) but is migrated so the linter can reach zero; deleting it
is a separate decision."
```

---

### Task 14: Migrate the forms and entry pages

**Files:**
- Modify: `dreaming/templates/projects.html` (14 inline styles)
- Modify: `dreaming/templates/setup.html`
- Modify: `dreaming/templates/settings.html`
- Modify: `dreaming/templates/project_settings.html`
- Modify: `dreaming/templates/index_dashboard.html`
- Modify: `dreaming/templates/project_not_found.html`

**Interfaces:**
- Consumes: everything from Task 4, especially `.field`, `.field-row`, `.field__label`, `.field__hint`, `.card`, `.empty-state`.
- Produces: nothing new.

- [ ] **Step 1: Record before-counts**

Run: `python scripts/check_css_tokens.py`, note all six rows.

- [ ] **Step 2: Migrate all six**

Apply the canonical replacement table. Specific notes:
- `projects.html`: the inline rename forms become `.field-row`; the `↵` save buttons become `class="btn btn-sm"`; the `working_dir` cell gets `class="num"`; the import block at the bottom becomes `.card` with a `.field-row` inside and `class="btn btn-primary"` on submit. **Do not touch the `js-slug-form` script or its `data-original-slug` / `data-acked` attributes** — the slug-rename confirmation depends on them.
- `setup.html` and `settings.html`: every label/input pair becomes `.field`; helper text becomes `.field__hint`.
- `project_not_found.html`: becomes a single `.empty-state`.

- [ ] **Step 3: Verify**

Run: `python scripts/check_css_tokens.py` — all six gone from both lists.
Run: `python scripts/smoke_templates_render.py` — exit 0.
Browser: `/projects` (rename a project's label and save — the `↵` button must still work; then edit a slug and confirm the danger modal still appears), `/setup`, `/settings`, `/p/<slug>/settings`, and a bad slug like `/p/does-not-exist/`.

- [ ] **Step 4: Commit**

```bash
git add dreaming/templates/projects.html dreaming/templates/setup.html dreaming/templates/settings.html dreaming/templates/project_settings.html dreaming/templates/index_dashboard.html dreaming/templates/project_not_found.html
git commit -m "refactor(design): migrate the forms and entry pages

Label/input pairs move to .field. The js-slug-form confirmation flow in
projects.html is untouched and re-verified."
```

---

### Task 15: Migrate the shared partials

These are includes — each one changes several pages at once, so verification spans more URLs than files.

**Files:**
- Modify: `dreaming/templates/_app_modal.html`
- Modify: `dreaming/templates/_autoconfig_banner.html`
- Modify: `dreaming/templates/_scan_action_bar.html`
- Modify: `dreaming/templates/_markdown_partial.html`
- Modify: `dreaming/templates/partials/dashboard/_tile_orchestration.html`
- Modify: `dreaming/templates/partials/dashboard/_tile_evolutions.html`
- Modify: `dreaming/templates/partials/dashboard/_tile_loops.html`

**Interfaces:**
- Consumes: everything from Task 4.
- Produces: nothing new.

- [ ] **Step 1: Record before-counts**

Run: `python scripts/check_css_tokens.py`, note all seven rows.

- [ ] **Step 2: Migrate all seven**

Apply the canonical replacement table. Specific notes:
- `_app_modal.html` is the shared confirm dialog used by every `data-confirm` form in the app. Its `dialog.note-modal` styling already lives in `components.css`. Migrate the buttons to `.btn` / `.btn-primary` / `.btn-danger` and **do not change `window.appConfirm`, the `data-confirm*` attribute protocol, or the `form.requestSubmit()` re-submit path** — `projects.html` calls `window.appConfirm` directly and `base.html`'s nav-progress bar keys off `data-confirm`.
- `_autoconfig_banner.html` is one of the seven light-island files → `.banner .banner-warn`.
- `_scan_action_bar.html` renders the last-scan badge → `.toolbar` with a `.badge` and `.btn`s.
- The three dashboard tiles → `.card` (or keep `.metric` where they already use it) with `.num` on their figures.

- [ ] **Step 3: Verify**

Run: `python scripts/check_css_tokens.py` — all seven gone from both lists.
Run: `python scripts/smoke_templates_render.py` — exit 0.
Run: `python scripts/smoke_dashboard_tiles.py` — exit 0 (it parses the three tile partials by name).
Browser: `/p/<slug>/` (tiles + autoconfig banner), `/p/<slug>/findings` (scan action bar), and click any `Delete` anywhere to exercise the confirm modal. Then re-run the slug-rename flow on `/projects`, which uses `window.appConfirm` directly.

- [ ] **Step 4: Commit**

```bash
git add dreaming/templates/_app_modal.html dreaming/templates/_autoconfig_banner.html dreaming/templates/_scan_action_bar.html dreaming/templates/_markdown_partial.html dreaming/templates/partials/dashboard/
git commit -m "refactor(design): migrate the shared partials

_app_modal.html buttons move to .btn variants; the appConfirm protocol and
requestSubmit re-submit path are untouched and re-verified from both call
sites (data-confirm forms and projects.html's direct call)."
```

---

### Task 16: Migrate the remaining pages

Everything not yet covered. After this task the linter must report zero.

**Files:**
- Modify: `dreaming/templates/ai_radar.html`
- Modify: `dreaming/templates/project_ai_radar.html`
- Modify: `dreaming/templates/_ai_radar_speak_js.html`
- Modify: `dreaming/templates/project_help.html`
- Modify: `dreaming/templates/project_live.html`
- Modify: `dreaming/templates/project_loops.html`
- Modify: `dreaming/templates/project_loops_templates.html`
- Modify: `dreaming/templates/project_questions.html`
- Modify: `dreaming/templates/project_rotation.html`

**Interfaces:**
- Consumes: everything from Task 4.
- Produces: a tree where the only linter findings left are hex in `components.css` (none) — i.e. both template counters at zero.

- [ ] **Step 1: Record before-counts**

Run: `python scripts/check_css_tokens.py`, note all nine rows. These are the last non-zero rows in the report.

- [ ] **Step 2: Migrate all nine**

Apply the canonical replacement table. Specific notes:
- `project_questions.html` and `project_rotation.html` are two of the seven light-island files (`bg-amber-*`, `bg-sky-*`) → `.banner-warn` / `.banner-info`.
- `project_live.html` renders an SSE stream view — preserve every element id and `data-*` attribute its JavaScript queries.
- `_ai_radar_speak_js.html` is a script partial; it may contain colour strings inside JavaScript rather than in markup. If so, replace them with `getComputedStyle(document.documentElement).getPropertyValue('--token')` reads, or move the styling into a class the script toggles. Do not leave a hard-coded palette colour in JS — that is the same bug this wave exists to remove.
- `project_help.html` is mostly prose → `.card` + `.md-content`.

- [ ] **Step 3: Verify the counters reach zero**

Run: `python scripts/check_css_tokens.py`

Expected:

```
OK components.css: no hex literals
OK Light-theme colour utilities in templates: 0
OK Static inline style= in templates: 0
ALL OK
```

Exit code **0**. This is the first time the linter passes. If any file still appears, it was missed — finish it in this task.

Run: `python scripts/smoke_templates_render.py` — exit 0.
Browser: `/ai-radar`, `/p/<slug>/ai-radar`, `/p/<slug>/help`, `/p/<slug>/live`, `/p/<slug>/loops`, `/p/<slug>/loops/templates`, `/p/<slug>/questions`, `/p/<slug>/rotation`. On `live`, confirm the stream still updates.

- [ ] **Step 4: Commit**

```bash
git add dreaming/templates/
git commit -m "refactor(design): migrate the last nine templates

check_css_tokens.py now exits 0: zero light-theme colour utilities and zero
static inline styles across all 51 templates, down from 464 and 491."
```

---

### Task 17: Remove the compatibility block and lock the gate

The `!important` overrides existed only to retro-fit a dark theme onto light-theme utilities. With zero such utilities left, they are dead weight — and while they remain, a new light utility would be silently absorbed instead of caught.

**Files:**
- Modify: `dreaming/static/app.css` (delete the compatibility block — find it by its comment anchor, not by line number: Tasks 3 and 4 remove ~90 lines above it)
- Modify: `docs/superpowers/plans/2026-08-16-design-system-foundation.md` (tick the boxes)

**Interfaces:**
- Consumes: a green `check_css_tokens.py` from Task 16.
- Produces: the finished wave. D3 (visual direction) and D4 (key screens, ergonomics) build on this.

- [ ] **Step 1: Confirm the gate is green before deleting anything**

Run: `python scripts/check_css_tokens.py`
Expected: exit 0. **If it is not 0, stop.** Deleting the block with unmigrated templates left will break those screens — that is exactly what the ordering rule in the spec prevents.

- [ ] **Step 2: Delete the compatibility block**

Remove from `dreaming/static/app.css` everything from the comment

```css
/* ---------- Compatibility overrides for Tailwind utilities used by existing
   templates that still encode light-theme colors. …
```

down to and including the `.text-green-600, .text-green-700` rule — the whole `!important` section. Keep the `.md-content` section that follows it.

- [ ] **Step 3: Verify nothing depended on it**

Run: `python scripts/check_css_tokens.py` — exit 0.
Run: `python scripts/smoke_templates_render.py` — exit 0.
Run: `python scripts/check_i18n.py` — exit 0.
Run: `python scripts/check_no_native_dialogs.py` — exit 0.
Run: `python scripts/smoke_table_tools.py` — exit 0.
Run: `python scripts/smoke_dashboard_tiles.py` — exit 0.

Then walk the app in a browser with fresh eyes, at both a wide and a narrow window (drag to ~700px so the sidebar collapses to icons): `/projects`, `/p/<slug>/`, `orchestration`, `findings`, `ideas`, `evolutions`, `ai-usage`, `wiki`, `settings`, `/setup`.

Nothing may be unstyled, white-on-white, or invisible. Pay particular attention to the two bugs this wave set out to fix:
- the seven light-island files (`project_dashboard`, `project_orchestration_list`, `project_questions`, `project_rotation`, `project_topics`, `session_log`, `_autoconfig_banner`) — every banner must be dark;
- the eight `border-purple-500 text-purple-700` buttons — every one must now be a legible `.btn`.

- [ ] **Step 4: Commit**

```bash
git add dreaming/static/app.css docs/superpowers/plans/2026-08-16-design-system-foundation.md
git commit -m "refactor(design): drop the !important compatibility block

Nothing needs it: zero light-theme utilities remain in templates. Removing it
means a newly introduced light utility now renders visibly wrong instead of
being silently absorbed -- and check_css_tokens.py catches it first.

Closes the D1/D2 design-system wave: app appearance now lives in tokens.css,
component appearance in components.css, and templates carry structure only."
```

- [ ] **Step 5: Tag the wave**

```bash
git tag design-system
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task(s) |
|---|---|
| Stylesheet split (`tokens.css` / `components.css` / `app.css`) | 3, 4 |
| Token layer: surfaces, spacing, radii, typography, numerics | 3 |
| Density: default + `.is-dense`, chosen per table | 3 (tokens), 4 (class), 6/8/9/11/12 (applied) |
| Component inventory (btn, toolbar, banner, page-header, card, panel, empty-state, field) | 4 |
| Existing components moved not renamed (metric, badge, pill, data-table) | 4 |
| Migration order: shell → top three → heaviest → batches | 5 → 6-8 → 9-11 → 12-16 |
| `!important` block deleted last, gated on the linter | 17 |
| Definition of done per template | Global Constraints + per-task Step 3 |
| `check_css_tokens.py` (3 assertions + counters) | 1 |
| Route/render smoke | 2 |
| `check_i18n.py` stays green | 12, 17 |
| Risk: component API mistake propagates | 8 (review gate) |
| Risk: Jinja typo on an unopened page | 2 |
| Risk: token rename breaks consumers | Global Constraints (no renames) |

All 51 templates are assigned exactly once: Task 5 (3), 6 (1), 7 (1), 8 (1), 9 (2), 10 (3), 11 (3), 12 (8), 13 (7), 14 (6), 15 (7), 16 (9) = 51.

**Deviation from the spec, flagged deliberately:** the spec described the smoke script as "walks the app's routes with FastAPI `TestClient` against a seeded DB". While planning, two facts emerged from the codebase: `smoke_dashboard_tiles.py` already establishes a cheaper Jinja-compile pattern, and a full route walk needs project rows whose `working_dir` exists on disk, which is environment-dependent. Task 2 therefore makes compile-all the deterministic tier and the route walk a best-effort tier that skips cleanly when no project is configured. This is weaker than the spec implied — it catches syntax errors, not undefined variables — and the plan says so at the point of use rather than overselling it.

**Placeholder scan:** no TBD/TODO; every step names exact files, exact commands, and exact expected output. Migration tasks carry file-specific notes rather than "similar to Task N", and the shared replacement table lives in Global Constraints, which every task inherits by definition.

**Type/name consistency:** class names used in Tasks 5–16 (`.page-header__title`, `.banner__body`, `.btn-warn`, `.card--flush`, `.list-rows`, `.num`, `.metric__value`, `.data-table.is-dense`, `.toolbar__count`, `.field-row`, `.empty-state__title`) all trace to definitions in Task 4 — except the four `.metric.metric-* .metric__value` rules, which Task 6 Step 3 adds explicitly to `components.css` as part of that task. `.muted` predates this wave and lives in `app.css`. Token names used in Task 4 all trace to Task 3.
