# Multi-project

Главное отличие DC от ALC — first-class multi-project поддержка. URL-resolver, registry, setup wizard, aggregated dashboard.

## Содержание

- [Project registry](#project-registry)
- [URL resolver middleware](#url-resolver-middleware)
- [Setup wizard](#setup-wizard)
- [Project lifecycle hooks](#project-lifecycle-hooks)
- [Concurrency: composite keys](#concurrency-composite-keys)
- [Reconcile: project_id-aware](#reconcile-project_id-aware)
- [Aggregated dashboard](#aggregated-dashboard)

## Project registry

Таблица [`projects`](../schema.md#projects):

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

`slug` — UNIQUE, используется в URL `/p/{slug}/`. Должен быть URL-safe (без пробелов, slashes).

`working_dir` — абсолютный путь к корню проекта. Там должен быть `.claude/agents/` если хочешь self-study.

`is_default` — единственный default-проект для slash-команды без `project_slug` (см. [`api.py:36`](../../dreaming/routes/api.py)).

[`ProjectsService`](../../dreaming/services/projects.py) — CRUD:

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

[`dreaming/middleware/project_resolver.py`](../../dreaming/middleware/project_resolver.py):

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

Логика:
1. Если path не начинается с `/p/` — pass through.
2. Парсим slug (3-й path-segment).
3. `get_by_slug(slug)`.
4. Если None или disabled → 404 + render `project_not_found.html`.
5. Иначе → `request.state.project = project`.

Все роуты внутри `/p/{slug}/*` потом просто `request.state.project` — без повторного DB-lookup'а.

Зарегистрирован как **второй** middleware (внутренний — runs after setup_gate). См. [`architecture.md`](../architecture.md#middleware) для полного порядка.

## Setup wizard

При первом старте `setup_gate_middleware` детектит пустую `projects` таблицу и редиректит на `/setup`.

UI: одна страница с двумя phase'ами.

### Phase 1: Globals + Scan

Поля:
- `claude_path` (default `claude`).
- `projects_root` (default `D:\Work\micode`).
- `default_locale` (`ru` / `en`).

Кнопки:
- **Scan** — POST `action=scan`. Сервер делает `ProjectsService.scan_projects_root(root)`, возвращает то же page плюс таблицу найденных подпапок.

`scan_projects_root` ([`projects.py:135`](../../dreaming/services/projects.py)):

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

Возвращает список dicts. `has_claude` — флаг что у директории есть `.claude/`.

### Phase 2: Selection + Save

В rendered scan-таблице — checkbox per row, поля slug/label/path. radio для default.

Submit POST'ом без `action=scan`:

1. `_save_global_yaml({claude_path, projects_root, default_locale})` — merge в `config.yaml`.
2. `request.app.state.settings = type(settings).load()` — reload.
3. Из form собирается `items = [{slug, label, working_dir, enabled}, ...]`.
4. `await projects.import_from_scan(items, default_slug=...)`.
5. Для каждого нового проекта — `await register_project_jobs(scheduler, app_state, proj)`.
6. 303 на `/`.

`import_from_scan` ([`projects.py:156`](../../dreaming/services/projects.py)) **идемпотентен**:
- Skip items по `working_dir` или `slug` уже в БД.
- Если slug коллизит — добавляет суффикс `-2`, `-3`.

## Project lifecycle hooks

### Toggle (enable/disable)

`POST /projects/{project_id}/toggle` ([`projects.py:23`](../../dreaming/routes/projects.py)):

```python
new_enabled = not p.enabled
await projects.update(project_id, enabled=new_enabled)
refreshed = await projects.get_by_id(project_id)
if new_enabled:
    await register_project_jobs(scheduler, app_state, refreshed)
else:
    await unregister_project_jobs(scheduler, refreshed)
```

После toggle — **обязательно** (un)register cron jobs. Иначе:
- enabled=true но jobs не зарегистрированы → cron не сработает.
- enabled=false но jobs ещё в scheduler → cron сработает на disabled проект (хотя `_nightly_learning` сам проверит `proj.enabled`).

### Delete

`POST /projects/{project_id}/delete` ([`projects.py:40`](../../dreaming/routes/projects.py)):

```python
p = await projects.get_by_id(project_id)
if p:
    await unregister_project_jobs(scheduler, p)
await projects.delete(project_id)
```

Сначала unregister, потом DELETE. CASCADE удалит все project-зависимые rows (см. [`schema.md`](../schema.md#cascade-удаление)).

### Import (re-scan)

`POST /projects/import` form `root=` ([`projects.py:50`](../../dreaming/routes/projects.py)) — массовый scan + import.

Идемпотентность та же. После создания — register jobs для каждого нового.

### Settings change

Когда меняется `cron_expression` или `cron_enabled` через `/p/{slug}/settings`, **не вызывается** re-register автоматически. Чтобы изменения подхватились — перезапусти DC, или руками вызови `register_project_jobs`. Это TODO; см. [`waves.md`](../waves.md#не-реализованные-пока).

## Concurrency: composite keys

`ProcessManager.running` ([`process_manager.py:91`](../../dreaming/services/process_manager.py)) — `dict[str, RunningSession]` с composite-key:

| Тип spawn'а | Composite key |
|---|---|
| `start_session(project, agent_name=...)` | `"{project.slug}:{agent_name}"` |
| `start_command(project, command_name=...)` | `"cmd:{project.slug}:{command_name}"` |
| `start_raw_command(project, command_name=...)` | `"cmd:{project.slug}:{command_name}"` |

Преимущества:
- Один и тот же агент `alisa-frontend` может работать одновременно в проектах `rgs` и `eng` — разные ключи.
- Команды (например `wiki-bootstrap`) — тоже per-project, не глобальные.
- При reconcile / kill можно фильтровать по `pfx = f"{slug}:"` / `f"cmd:{slug}:"` чтобы взять только один проект.

`max_concurrent` (default 2) — это **глобальный** лимит ([`process_manager.py:92`](../../dreaming/services/process_manager.py)). Не per-project. Если хочешь per-project лимиты — будут pull request'ы.

Active runs aside на главном `/` строится перебором `pm.list_running()`:

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

См. [`root.py:81–89`](../../dreaming/routes/root.py).

## Reconcile: project_id-aware

`pm.reconcile_stale_sessions(active_pairs: list[tuple[int, str]])` ([`process_manager.py:699`](../../dreaming/services/process_manager.py)):

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

Принимает кортежи `(project_id, agent_name)` — не slug. ProjectsService резолвит slug.

Глобальный cron job `_reconcile_job` ([`scheduler.py:37`](../../dreaming/services/scheduler.py)) собирает active_pairs из in-memory `pm.running` (не из БД!) и передаёт обратно. Это защита от orphan-keys в `running`.

Reconcile NOT trigger'ит DB-обновления — это делает `pm._cleanup` после каждого spawn'а через `db.reconcile_stale_sessions(...)` (метод реализуется лениво — в текущем коде это вызов на db с грейс-минутами 2, см. [`process_manager.py:627`](../../dreaming/services/process_manager.py)).

## Aggregated dashboard

`GET /` ([`root.py:17`](../../dreaming/routes/root.py)) показывает:

### Per-project cards

Для каждого enabled-проекта:
- `week_stats` (success/failed/timeout/running с понедельника UTC).
- Running count: фильтр `pm.list_running()` по `pfx`.
- TD count: `len(list_tech_debt(td_dir))` если `tech_debt_dir` задан и существует.
- Ideas count: `len(list_product_ideas(ideas_dir))`.
- Wiki present: `Path(wiki_dir).exists()`.

Все вычисляются inline в handler'е. При большом числе проектов это может тормозить — TODO для оптимизации (cached + invalidate on writes).

### Top-line totals

Sum по всем cards: total_success, total_failed, total_timeout, total_running, total_td, total_ideas.

### Active runs aside

Flat-список `{slug, agent}` для всех running keys. Включает и `cmd:*` (с префиксом).

### Locale + projects (для navbar)

- `locale = cookie["dc_locale"] OR settings.default_locale`.
- `projects = list_all(only_enabled=True)` для navbar dropdown'а.

## Cross-references

- Schema: [`schema.md`](../schema.md#projects).
- Resolver middleware: [`architecture.md`](../architecture.md#middleware).
- Settings inheritance: [`features/settings.md`](settings.md).
- Setup routes: [`api.md`](../api.md#setup-wizard) и [`routes.md`](../routes.md#setup).
