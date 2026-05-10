# Multi-project

DC's main differentiator from ALC is first-class multi-project support. URL resolver, registry, setup wizard, aggregated dashboard.

## Contents

- [Project registry](#project-registry)
- [URL resolver middleware](#url-resolver-middleware)
- [Setup wizard](#setup-wizard)
- [Project lifecycle hooks](#project-lifecycle-hooks)
- [Concurrency: composite keys](#concurrency-composite-keys)
- [Reconcile: project_id-aware](#reconcile-project_id-aware)
- [Aggregated dashboard](#aggregated-dashboard)

## Project registry

The [`projects`](../schema.md#projects) table:

```sql
CREATE TABLE projects (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    slug         TEXT UNIQUE NOT NULL,
    label        TEXT NOT NULL,
    working_dir  TEXT NOT NULL,
    enabled      INTEGER NOT NULL DEFAULT 1,
    is_default   INTEGER NOT NULL DEFAULT 0,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    color        TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
```

`slug` — UNIQUE, used in URLs `/p/{slug}/`. Must be URL-safe (no spaces, slashes).

`working_dir` — absolute path to the project root. Must contain `.claude/agents/` if you want self-study.

`is_default` — the single default project for slash commands without `project_slug` (see [`api.py:36`](../../../dreaming/routes/api.py)).

[`ProjectsService`](../../../dreaming/services/projects.py) — CRUD:

```python
await projects.list_all(only_enabled=False)
await projects.get_by_slug(slug)
await projects.get_by_id(project_id)
await projects.get_default()
await projects.create(slug, label, working_dir, ...)
await projects.update(project_id, **kwargs)
await projects.delete(project_id)

# Per-project KV settings
await projects.set_setting(project_id, key, value)
await projects.unset_setting(project_id, key)
await projects.get_setting(project_id, key)
await projects.all_settings(project_id) -> dict
```

## URL resolver middleware

[`dreaming/middleware/project_resolver.py`](../../../dreaming/middleware/project_resolver.py):

```python
async def project_resolver_middleware(request, call_next):
    request.state.project = None
    path = request.url.path
    if not path.startswith("/p/"):
        return await call_next(request)

    parts = path.split("/", 3)        # ['', 'p', slug, rest]
    if len(parts) < 3 or not parts[2]:
        return await call_next(request)

    slug = parts[2]
    project = await request.app.state.projects.get_by_slug(slug)
    if project is None or not project.enabled:
        return TemplateResponse("project_not_found.html",
            {"slug": slug, "is_disabled": project is not None and not project.enabled},
            status_code=404)
    request.state.project = project
    return await call_next(request)
```

Logic:
1. If the path doesn't start with `/p/` — pass through.
2. Parse the slug (the 3rd path segment).
3. `get_by_slug(slug)`.
4. If None or disabled → 404 + render `project_not_found.html`.
5. Otherwise → `request.state.project = project`.

Every route under `/p/{slug}/*` then just reads `request.state.project` — no repeated DB lookup.

Registered as the **second** middleware (inner — runs after setup_gate). See [`architecture.md`](../architecture.md#middleware) for the full order.

## Setup wizard

On the first launch, `setup_gate_middleware` detects an empty `projects` table and redirects to `/setup`.

UI: a single page with two phases.

### Phase 1: Globals + Scan

Fields:
- `claude_path` (default `claude`).
- `projects_root` (default `D:\Work\micode`).
- `default_locale` (`ru` / `en`).

Buttons:
- **Scan** — POST `action=scan`. The server runs `ProjectsService.scan_projects_root(root)` and returns the same page plus a table of discovered subfolders.

`scan_projects_root` ([`projects.py:135`](../../../dreaming/services/projects.py)):

```python
@staticmethod
def scan_projects_root(root: str) -> list[dict]:
    p = Path(root)
    if not p.exists() or not p.is_dir():
        return []
    out = []
    for entry in sorted(p.iterdir()):
        if not entry.is_dir(): continue
        if entry.name.startswith("."): continue
        has_claude = (entry / ".claude").is_dir()
        out.append({
            "path": str(entry),
            "name": entry.name,
            "suggested_slug": entry.name,
            "suggested_label": entry.name,
            "has_claude": has_claude,
        })
    return out
```

Returns a list of dicts. `has_claude` flags whether the directory has `.claude/`.

### Phase 2: Selection + Save

In the rendered scan table — checkbox per row, slug/label/path inputs. Radio for default.

Submit POST without `action=scan`:

1. `_save_global_yaml({claude_path, projects_root, default_locale})` — merge into `config.yaml`.
2. `request.app.state.settings = type(settings).load()` — reload.
3. From the form we collect `items = [{slug, label, working_dir, enabled}, ...]`.
4. `await projects.import_from_scan(items, default_slug=...)`.
5. For each new project — `await register_project_jobs(scheduler, app_state, proj)`.
6. 303 to `/`.

`import_from_scan` ([`projects.py:156`](../../../dreaming/services/projects.py)) is **idempotent**:
- Skip items by `working_dir` or `slug` already in the DB.
- If the slug collides — append a `-2`, `-3` suffix.

## Project lifecycle hooks

### Toggle (enable/disable)

`POST /projects/{project_id}/toggle` ([`projects.py:23`](../../../dreaming/routes/projects.py)):

```python
new_enabled = not p.enabled
await projects.update(project_id, enabled=new_enabled)
refreshed = await projects.get_by_id(project_id)
if new_enabled:
    await register_project_jobs(scheduler, app_state, refreshed)
else:
    await unregister_project_jobs(scheduler, refreshed)
```

After toggle — **always** (un)register cron jobs. Otherwise:
- enabled=true but jobs not registered → cron doesn't fire.
- enabled=false but jobs still in scheduler → cron fires for the disabled project (although `_nightly_learning` itself checks `proj.enabled`).

### Delete

`POST /projects/{project_id}/delete` ([`projects.py:40`](../../../dreaming/routes/projects.py)):

```python
p = await projects.get_by_id(project_id)
if p:
    await unregister_project_jobs(scheduler, p)
await projects.delete(project_id)
```

First unregister, then DELETE. CASCADE removes every project-dependent row (see [`schema.md`](../schema.md#cascade-delete)).

### Import (re-scan)

`POST /projects/import` form `root=` ([`projects.py:50`](../../../dreaming/routes/projects.py)) — bulk scan + import.

Same idempotence. After creation — register jobs for every new one.

### Settings change

When `cron_expression` or `cron_enabled` changes via `/p/{slug}/settings`, **no** re-register is triggered automatically. To pick up the change — restart DC, or call `register_project_jobs` by hand. This is a TODO; see [`waves.md`](../waves.md#not-implemented-yet).

## Concurrency: composite keys

`ProcessManager.running` ([`process_manager.py:91`](../../../dreaming/services/process_manager.py)) — `dict[str, RunningSession]` with composite keys:

| Spawn type | Composite key |
|---|---|
| `start_session(project, agent_name=...)` | `"{project.slug}:{agent_name}"` |
| `start_command(project, command_name=...)` | `"cmd:{project.slug}:{command_name}"` |
| `start_raw_command(project, command_name=...)` | `"cmd:{project.slug}:{command_name}"` |

Benefits:
- The same agent `alisa-frontend` can run simultaneously in projects `rgs` and `eng` — different keys.
- Commands (e.g. `wiki-bootstrap`) — also per-project, not global.
- During reconcile / kill you can filter by `pfx = f"{slug}:"` / `f"cmd:{slug}:"` to take only one project.

`max_concurrent` (default 2) is the **global** limit ([`process_manager.py:92`](../../../dreaming/services/process_manager.py)). Not per-project. If you want per-project limits — pull requests welcome.

Active runs aside on the home `/` is built by walking `pm.list_running()`:

```python
pfx_runs = []
for k in pm.list_running().keys():
    if k.startswith("cmd:"):
        parts = k.split(":", 2)
        if len(parts) == 3:
            pfx_runs.append({"slug": parts[1], "agent": f"cmd:{parts[2]}"})
    else:
        slug, _, agent = k.partition(":")
        pfx_runs.append({"slug": slug, "agent": agent})
```

See [`root.py:81–89`](../../../dreaming/routes/root.py).

## Reconcile: project_id-aware

`pm.reconcile_stale_sessions(active_pairs: list[tuple[int, str]])` ([`process_manager.py:699`](../../../dreaming/services/process_manager.py)):

```python
async def reconcile_stale_sessions(self, active_pairs):
    active_keys = set()
    for pid, name in active_pairs:
        proj = await self.projects.get_by_id(pid)
        if proj:
            active_keys.add(f"{proj.slug}:{name}")
    closed = 0
    for key in list(self.running.keys()):
        if key.startswith("cmd:"): continue
        if key not in active_keys:
            await self.kill(key); closed += 1
    return closed
```

Takes tuples `(project_id, agent_name)` — not slug. ProjectsService resolves the slug.

The global cron job `_reconcile_job` ([`scheduler.py:37`](../../../dreaming/services/scheduler.py)) collects active_pairs from in-memory `pm.running` (not from the DB!) and hands them back. Defends against orphan keys in `running`.

Reconcile does NOT trigger DB updates — that's done by `pm._cleanup` after each spawn via `db.reconcile_stale_sessions(...)` (the method is implemented lazily — in the current code it's a call on db with grace_minutes 2, see [`process_manager.py:627`](../../../dreaming/services/process_manager.py)).

## Aggregated dashboard

`GET /` ([`root.py:17`](../../../dreaming/routes/root.py)) shows:

### Per-project cards

For every enabled project:
- `week_stats` (success/failed/timeout/running since Monday UTC).
- Running count: filter `pm.list_running()` by `pfx`.
- TD count: `len(list_tech_debt(td_dir))` if `tech_debt_dir` is set and exists.
- Ideas count: `len(list_product_ideas(ideas_dir))`.
- Wiki present: `Path(wiki_dir).exists()`.

All computed inline in the handler. With many projects it may slow down — TODO to optimise (cached + invalidate on writes).

### Top-line totals

Sum across all cards: total_success, total_failed, total_timeout, total_running, total_td, total_ideas.

### Active runs aside

Flat list `{slug, agent}` for every running key. Includes `cmd:*` (with the prefix).

### Locale + projects (for the navbar)

- `locale = cookie["dc_locale"] OR settings.default_locale`.
- `projects = list_all(only_enabled=True)` for the navbar dropdown.

## Cross-references

- Schema: [`schema.md`](../schema.md#projects).
- Resolver middleware: [`architecture.md`](../architecture.md#middleware).
- Settings inheritance: [`features/settings.md`](settings.md).
- Setup routes: [`api.md`](../api.md#setup-wizard) and [`routes.md`](../routes.md#setup).
