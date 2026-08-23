# Development Guide

Conventions, checklists for typical tasks, code style, git discipline.

## Contents

- [Code conventions](#code-conventions)
- [Adding a per-project page](#adding-a-per-project-page)
- [Adding a settings key](#adding-a-settings-key)
- [Adding a scheduled job](#adding-a-scheduled-job)
- [Writing a parser service](#writing-a-parser-service)
- [DB conventions](#db-conventions)
- [Testing approach](#testing-approach)
- [Design system](#design-system)
- [i18n discipline](#i18n-discipline)
- [Git conventions](#git-conventions)

## Code conventions

- **Python ≥ 3.10**, `from __future__ import annotations` everywhere — pep604 unions and so on.
- **Async everywhere** there is IO. `aiosqlite`, `asyncio.subprocess`, `httpx.AsyncClient`.
- **User-facing text** in templates and `HTTPException(detail=...)` — **in Russian** (e.g. `"Настройте Jira (email + API token) в /settings"` in [`jira.py:67`](../../dreaming/services/jira.py)).
- **Code identifiers / log messages / docstrings** — English. This makes them greppable.
- **Modern Starlette TemplateResponse signature**: `templates.TemplateResponse(request, "name.html", {ctx})` — request first positional, not in context. The old style `TemplateResponse("name.html", {"request": request, ...})` is deprecated and emits a warning.
- **Type hints**: write them for the public API of services. For private/local — opt-in.
- **Dataclasses** for plain DTOs (Item classes in every parser). NamedTuple — only when a tuple-API is required (see `notes.py:7`).
- **No global singletons** — everything via `app.state`.
- **No fork of workers** — single uvicorn with asyncio.

## Adding a per-project page

Full example — adding the `/p/{slug}/heartbeat` page.

### Checklist

1. **Create the parser service** (if it reads from disk): `dreaming/services/heartbeat.py`. Use `@dataclass` for the Item, signature `def list_heartbeats(dir: str) -> list[Item]`.
2. **Create the route**: `dreaming/routes/project_heartbeat.py`:
   ```python
   from fastapi import APIRouter, Request
   router = APIRouter()

   @router.get("/p/{slug}/heartbeat")
   async def heartbeat_page(request: Request, slug: str):
       project = request.state.project    # already resolved by middleware
       resolver = request.app.state.resolver_factory(request)
       heartbeat_dir = await resolver.get(project, "heartbeat_dir", "")
       items = list_heartbeats(heartbeat_dir) if heartbeat_dir else []
       locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
       projects = await request.app.state.projects.list_all(only_enabled=True)
       return request.app.state.templates.TemplateResponse(
           request, "project_heartbeat.html",
           {"project": project, "items": items,
            "projects": projects, "locale": locale},
       )
   ```
3. **Create the template**: `dreaming/templates/project_heartbeat.html`. Copy structure from `project_loops.html` or similar. Pull `_project_layout.html` if you want the sidebar.
4. **Register the router**: add to `dreaming/routes/project_router.py`:
   ```python
   from dreaming.routes.project_heartbeat import router as heartbeat_router
   ...
   router.include_router(heartbeat_router)
   ```
5. **Add a nav-link**: edit `dreaming/templates/_project_layout.html` (if the page is in the sidebar) or `_navbar.html`. Use the `t("p.heartbeat")` filter.
6. **Add i18n keys** in both `messages_ru.json` and `messages_en.json`:
   ```json
   "p.heartbeat": "Heartbeat"
   ```
7. **Run `scripts/check_i18n.py`** — verifies that keys are matched in RU/EN.
8. **Add the section to the registry**: `dreaming/services/nav_sections.py` — key, title key, path. The registry is shared: the help page is built from it, and `_sidebar.html` is checked against it.
9. **Write the section's guide**: `dreaming/help/ru/heartbeat.md` and `dreaming/help/en/heartbeat.md` — what the section is for, what is on screen, what you can do, what to check when it looks empty. Plus a one-line `help.section.heartbeat` in both `messages_*.json` for the collapsed card.
10. **Run `scripts/smoke_help_sections.py`** — fails if the section is missing from the registry, has no guide, has no caption, exists in one locale only, or has a path that is not a registered route.
11. **Smoke**: `curl http://localhost:8086/p/<slug>/heartbeat` — expect 200.

## Adding a settings key

### Checklist

1. **Declare in `AppSettings`** ([`dreaming/config.py`](../../dreaming/config.py)):
   ```python
   heartbeat_dir: str = ""
   heartbeat_interval_minutes: int = 30
   ```
2. **Add to `SETTINGS_GROUPS`** in the same config.py — pick a fitting group or create a new one:
   ```python
   ("Watchdogs", [
       ...
       "heartbeat_dir", "heartbeat_interval_minutes",
   ]),
   ```
3. **Document** in [`configuration.md`](configuration.md) — add a row to the group's table (default, type, per-proj scope, description, example).
4. **Use through the resolver** in routes:
   ```python
   resolver.get(project, "heartbeat_dir", "")
   ```
5. **Don't forget** that bool fields in the `/settings` HTML are handled via a triple: hidden=`false` + checkbox=`true` (HTML idiom).
6. **If the field is secret** (token/api_key) — the UI auto-renders as `type=password` (logic in `templates/settings.html`). Marker names: contains `token`, `api_key`, `password`.

The changes automatically appear in:
- The `/settings` form (via SETTINGS_GROUPS).
- The `/p/{slug}/settings` form (via the same SETTINGS_GROUPS).

## Adding a scheduled job

### Per-project job

1. **Write the job function** in `dreaming/services/scheduler.py`:
   ```python
   async def _weekly_heartbeat_check(app_state, project_id: int):
       proj = await app_state.projects.get_by_id(project_id)
       if proj is None or not proj.enabled:
           return
       pm = app_state.process_manager
       resolver = ConfigResolver(app_state.projects, app_state.settings)
       try:
           await pm.start_command(proj, command_name="weekly-heartbeat-check",
                                  prompt="/heartbeat", ...)
       except RuntimeError as e:
           log.warning("weekly_heartbeat_check [%s]: %s", proj.slug, e)
   ```
2. **Add to `_PER_PROJECT_JOBS`**:
   ```python
   _PER_PROJECT_JOBS = [
       ...
       ("weekly_heartbeat_check", "weekly_heartbeat_check_cron", "weekly_heartbeat_check_enabled",
        "0 8 * * 1", False, _weekly_heartbeat_check),
   ]
   ```
3. **Add settings keys** in `AppSettings`: `weekly_heartbeat_check_cron` + `weekly_heartbeat_check_enabled` (see [Adding a settings key](#adding-a-settings-key)).
4. **Add to `SETTINGS_GROUPS`** in the `"Scheduling — weekly (opt-in)"` group.

On the next `register_project_jobs(scheduler, app_state, proj)` (called automatically in setup/toggle/import) the job is registered.

### Global job (not per-project)

In `build_scheduler` ([`scheduler.py:219`](../../dreaming/services/scheduler.py)):

```python
def build_scheduler(app_state) -> AsyncIOScheduler:
    sched = AsyncIOScheduler()
    sched.add_job(_reconcile_job, "interval", minutes=5, args=[app_state],
                  id="reconcile_stale_sessions")
    # New:
    sched.add_job(_my_global_job, "cron", hour=3, minute=0, args=[app_state],
                  id="my_global_job")
    return sched
```

## Writing a parser service

The standard form (mirror of `evolutions.py`, `loops.py`, `plans.py`, `contracts.py`):

```python
"""Project-aware <X> parser."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import re

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

@dataclass
class XItem:
    path: str
    name: str
    title: str
    status: str
    raw_frontmatter: dict = field(default_factory=dict)

def _parse_frontmatter(text: str) -> dict[str, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip().strip('"\'')
    return out

def list_x(x_dir: str) -> list[XItem]:
    p = Path(x_dir)
    if not p.exists() or not p.is_dir():
        return []
    items: list[XItem] = []
    for f in sorted(p.glob("*.md")):
        if f.name.startswith("_"):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = _parse_frontmatter(text)
        items.append(XItem(
            path=str(f),
            name=f.stem,
            title=fm.get("title") or f.stem,
            status=fm.get("status") or "draft",
            raw_frontmatter=fm,
        ))
    return items
```

**Discipline**:
- The first argument is a path, not settings. (Project-aware.)
- If the directory does not exist — return `[]`, **do not raise**.
- `OSError` is caught per-file — one broken file must not blow up the whole list.
- If you want YAML instead of a custom regex — use `yaml.safe_load` (see tech_debt.py:108).

## DB conventions

- **Every table with `project_id`** declares it as `INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE`. See examples in `_SCHEMA`.
- **Denormalisation vs JOIN**: we denormalise `project_id` into hot-path tables (`agent_learning_sessions`, `orchestrator_runs`, `orchestrator_nodes`, `orchestrator_messages`, `ai_usage_events`, `ai_usage_files`). We don't denormalise into child tables where project comes via a JOIN to the run (`orchestrator_events`, `orchestrator_stages`, `orchestrator_gate_verdicts`, `orchestrator_artifacts`).
- **Idempotent migrations**: ALWAYS `IF NOT EXISTS` / try/except. Never `ALTER TABLE ADD COLUMN ... NOT NULL` without a default — SQLite hates that. See `_migrate_orchestration` ([`db.py:282`](../../dreaming/services/db.py)).
- **PK rebuild discipline**: SQLite can't `ALTER PRIMARY KEY`. If the PK has to change (as we did for `agent_learning_rotation`):
  1. Create a new table with the right PK.
  2. INSERT INTO ... SELECT FROM old.
  3. DROP TABLE old.
  4. ALTER TABLE new RENAME TO the old name.
  In our case we started greenfield, so there was no rebuild — `_SCHEMA` declares the right PK from the start.
- **Timestamps** are stored as ISO-strings in UTC (`datetime.now(timezone.utc).isoformat()`). Parsed via the `_fmt_dt` Jinja filter in base.html (if present, else inline in the template).
- **UUID v4** for every string PK. Use `uuid.uuid4()` or `str(uuid4())`.

## Testing approach

**There is no test framework** — a deliberate decision inherited from ALC. Reasons:
- Most code is IO (subprocess, DB, FS). Mocking everything is unproductive; a smoke test exercises the real path.
- Schema migrations are idempotent — re-running on a broken DB is caught immediately.
- Routes are curl-testable — the external contract is easy to check.

Smoke scenarios live in [`scripts/`](../../scripts/):

| Script | What it checks |
|---|---|
| `smoke_db_methods.py` | DB CRUD methods (sessions, rotation, topics). |
| `smoke_pm_api.py` | ProcessManager spawn/kill cycle. |
| `smoke_session.py` | Sessions API (POST start/finish). |
| `smoke_pipelines.py` | Parsers (tech-debt, ideas, contracts, ...). |
| `smoke_resolver.py` | ConfigResolver override-with-fallback. |
| `smoke_setup.py` | Setup wizard flow. |
| `smoke_scan.py` | scan_projects_root. |
| `smoke_seed_one.py` | Seed one project in DB. |
| `smoke_i18n.py` | Loading messages + plurals. |
| `check_i18n.py` | RU/EN keys parity. |
| `check_css_tokens.py` | Design system: no colour in templates, no literals in `components.css`, no undefined classes. |
| `smoke_templates_render.py` | Compiles every template, then walks every parameter-free GET route. |
| `smoke_help_sections.py` | The help page and the sidebar list the same sections, each with help text and a real route. |

Run:

```bash
python scripts/smoke_session.py
python scripts/check_i18n.py    # exit 0 if parity OK
```

If you added a feature — add a smoke (or extend an existing one). See `docs/smoke-tests.md`.

## Design system

Introduced by wave D1/D2 (see [`waves.md`](waves.md)). Before it, colour lived in 464 light-theme Tailwind utilities and 491 inline `style=` attributes across 51 templates, with a block of `!important` overrides layered on top to repaint them dark. Templates now carry no colour at all.

### Three files, in this order

`base.html` loads them exactly like this, and the order matters:

| File | Owns | What never appears in it |
|---|---|---|
| `static/tokens.css` | The single source of visual truth: a `:root` block of ~90 custom properties — surfaces, borders, text, brand, statuses, shadows, spacing, radii, typography, table density. | Any selector other than `:root`. |
| `static/app.css` | The base layer plus the app frame: `body`, resets, focus rings, scrollbars, form-control defaults, and the `.app-sidebar` / `.app-content` shell. | Reusable content components — those belong in `components.css`. |
| `static/components.css` | Semantic classes: `.card`, `.data-table`, `.stat-bar`, `.badge-*`, `.btn-*`, `.field__*`, `.row-actions` and friends. | **Colour literals.** `var(--…)` only. |

Plus two narrow ones: `table_tools.css` (table sorting and filtering) and `orchestration_swimlane.css`.

### The rule

**Colour in a template is a bug.** Need a new shade — add a token to `tokens.css`; need a new visual element — add a class to `components.css` and reference tokens from it. Tailwind utilities stay for layout (`flex`, `gap-3`, `grid-cols-2`), not for looks.

Why so strict: Tailwind arrives through the Play CDN, which emits its rules inside `@layer`. Unlayered author CSS always beats layered CSS regardless of specificity, so "I'll just patch it with a utility in the template" works about half the time and is miserable to debug.

### The gate

```bash
python scripts/check_css_tokens.py     # exit 0 == ALL OK
```

Four checks, all of which must read zero:

1. **Colour literals in `components.css`** — hex, and any `rgb()/rgba()/hsl()` that is not black (black is allowed for shadows and overlays).
2. **Tailwind utilities carrying a palette colour** — `bg-white`, `text-gray-700`, `border-slate-200`. Every shade is caught, not just the light ones: a dark `bg-slate-900` does not belong in a template either. Size and layout utilities (`text-xs`, `border`) never match — the regex requires a colour name.
3. **Static inline `style=` in templates.** An attribute containing `{{ … }}` is a computed value (a progress bar's width) and is allowed. An attribute built only from `{% %}` is not: picking between two static colours belongs in a modifier class.
4. **A class referenced in a template but defined nowhere** — catches typos like `text-warnn`. It knows about `<style>` blocks inside templates and about classes attached by JS.

### Adding a visual element

1. Check whether `components.css` already has the class — the wave caught four duplicates (`.dim` against `.muted`, `.progress-*` against `.meter-*`, two identical modal selectors, three byte-for-byte identical tokens).
2. If a shade or size is missing, add a token to `tokens.css`, in its own group.
3. Add the class to `components.css`, through `var(--…)` only.
4. Run `python scripts/check_css_tokens.py` and `python scripts/smoke_templates_render.py`.

On contrast: when you put a text colour over a translucent tint, compute contrast against the nearest **opaque** ancestor, not against the tint's own token. The wave found about twenty colours that looked fine in the source and composited to between 2.4:1 and 4:1 in the browser.

### Dates in tables

A timestamp cell is written like this — the server renders a fallback, `static/timeago.js` swaps in something human:

```jinja
<time data-ts="{{ s.started_at }}">{{ s.started_at[5:16] | replace("T", " ") }}</time>
```

The script shows relative time up to a week ("5 minutes ago") and a short absolute date beyond that, repaints once a minute, and honours the locale. If `data-ts` will not parse, the server's text is left alone.

### Static asset caching

`dreaming/main.py` exposes `asset_v` as a Jinja global — the newest mtime across the local assets — and `base.html` appends it as `?v={{ asset_v }}`. Without it CSS edits are invisible until a hard refresh: browsers hold `/static/*.css` firmly, and restarting the server does not help. When you add a new local css/js to `base.html`, add its filename to the list inside `_asset_version()`.

## i18n discipline

- Every user-facing string in templates goes through `{{ "key.path" | t(locale=locale) }}`.
- Default locale `ru` — add first to `messages_ru.json`, then mirror to `messages_en.json`.
- **Every key must exist in both files**. `scripts/check_i18n.py` fails the build (exit code 1) on any divergence.
- Naming: `<area>.<sub>` or `<area>.<sub>.<sub2>`. Examples: `common.app_name`, `navbar.all_projects`, `p.dashboard`, `p.metrics.success`, `settings.title`.
- Plurals: use `i18n.plural("count.runs", n, locale=locale)` — it appends `.one`/`.few`/`.many` for RU and `.one`/`.other` for EN.

More in [`features/i18n.md`](features/i18n.md).

## Git conventions

- **One commit = one logical unit**. Wave 1, Wave 2.5, a specific feature.
- **Conventional commits**: `feat:`, `fix:`, `docs:`, `chore:`, `test:`. Example:
  ```
  feat: per-project nightly_learning_{slug} cron + (un)register hooks on toggle/delete/import
  fix: setup wizard — default projects_root + scan_error message + hint
  docs: add CLAUDE.md with architecture guide for future Claude sessions
  ```
- **One tag per wave**: `wave-0`, `wave-1`, `wave-2`, ..., `wave-5`. Pushable but not required.
- **Don't commit secrets**. `config.yaml` and `data/dreaming.db` — in `.gitignore`. Tokens only via env vars or wizard input.

### Commit message body

If the change is non-trivial, add a body:

```
feat: Wave 3.7 — orchestration spawns claude + ClaudeSessionTail/SubagentWatcher + live polling + resume

- POST /p/{slug}/orchestration/start now spawns claude
  and starts ClaudeSessionTail + SubagentWatcher.
- /refresh endpoint for polling from the browser.
- /resume for claude --resume <session_id>.
- Sessions backfill preserved.
```

### Encoding on Windows

When creating files with Cyrillic content **do NOT use** `Set-Content` (PowerShell 5.1 default = UTF-16 LE) — Jinja2 and check_i18n.py won't read it. Use:
- The `Write` tool (UTF-8 without BOM).
- In scripts: `[System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($false))` — UTF-8 without BOM.
- Or `Out-File -Encoding utf8` — but on PS 5.1 it adds a BOM. Prefer the first option.

See also [`troubleshooting.md`](troubleshooting.md) (mojibake).

## Cross-references

- Architecture — [`architecture.md`](architecture.md).
- Parsers (examples) — [`services.md`](services.md).
- i18n — [`features/i18n.md`](features/i18n.md).
- Wave history — [`waves.md`](waves.md).
- Design system (spec) — [`superpowers/specs/2026-08-16-design-system-foundation-design.md`](../superpowers/specs/2026-08-16-design-system-foundation-design.md).
