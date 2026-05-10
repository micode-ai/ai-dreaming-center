# Development Guide

Конвенции, чек-листы для типовых задач, code style, git discipline.

## Содержание

- [Code conventions](#code-conventions)
- [Adding a per-project page](#adding-a-per-project-page)
- [Adding a settings key](#adding-a-settings-key)
- [Adding a scheduled job](#adding-a-scheduled-job)
- [Writing a parser service](#writing-a-parser-service)
- [DB conventions](#db-conventions)
- [Testing approach](#testing-approach)
- [i18n discipline](#i18n-discipline)
- [Git conventions](#git-conventions)

## Code conventions

- **Python ≥ 3.10**, `from __future__ import annotations` всюду — pep604 union'ы и т.д.
- **Async везде** где есть IO. `aiosqlite`, `asyncio.subprocess`, `httpx.AsyncClient`.
- **User-facing text** в шаблонах и `HTTPException(detail=...)` — **по-русски** (например `"Настройте Jira (email + API token) в /settings"` в [`jira.py:67`](../dreaming/services/jira.py)).
- **Code identifiers / log messages / docstrings** — английский. Это позволяет грепать.
- **Modern Starlette TemplateResponse signature**: `templates.TemplateResponse(request, "name.html", {ctx})` — request первым позиционным аргументом, не в context. Старый стиль `TemplateResponse("name.html", {"request": request, ...})` deprecated и выдаёт warning.
- **Type hints**: пишем для public API сервисов. Для private/local — opt-in.
- **Dataclasses** для plain DTO (Item-классы во всех парсерах). NamedTuple — только если нужен tuple-API (см. `notes.py:7`).
- **Никаких глобальных синглтонов** — всё через `app.state`.
- **Никакого fork'а воркеров** — single-uvicorn с asyncio.

## Adding a per-project page

Полный пример — добавляем `/p/{slug}/heartbeat` страницу.

### Чек-лист

1. **Создай парсер-сервис** (если читает с диска): `dreaming/services/heartbeat.py`. Use `@dataclass` для Item, `def list_heartbeats(dir: str) -> list[Item]` шапка.
2. **Создай роут**: `dreaming/routes/project_heartbeat.py`:
   ```python
   from fastapi import APIRouter, Request
   router = APIRouter()

   @router.get("/p/{slug}/heartbeat")
   async def heartbeat_page(request: Request, slug: str):
       project = request.state.project    # уже резолвлен middleware'ой
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
3. **Создай шаблон**: `dreaming/templates/project_heartbeat.html`. Скопируй structure из `project_loops.html` или похожего. Подключи `_project_layout.html` если хочешь сайдбар.
4. **Зарегистрируй роутер**: добавь в `dreaming/routes/project_router.py`:
   ```python
   from dreaming.routes.project_heartbeat import router as heartbeat_router
   ...
   router.include_router(heartbeat_router)
   ```
5. **Добавь nav-link**: edit `dreaming/templates/_project_layout.html` (если страница в сайдбаре) или `_navbar.html`. Используй `t("p.heartbeat")` filter.
6. **Добавь i18n keys** в обоих `messages_ru.json` и `messages_en.json`:
   ```json
   "p.heartbeat": "Heartbeat"
   ```
7. **Запусти `scripts/check_i18n.py`** — проверит что ключи сматчены в RU/EN.
8. **Smoke**: `curl http://localhost:8086/p/<slug>/heartbeat` — ожидаешь 200.

## Adding a settings key

### Чек-лист

1. **Объяви в `AppSettings`** ([`dreaming/config.py`](../dreaming/config.py)):
   ```python
   heartbeat_dir: str = ""
   heartbeat_interval_minutes: int = 30
   ```
2. **Добавь в `SETTINGS_GROUPS`** в той же config.py — выбери подходящую группу или создай новую:
   ```python
   ("Watchdogs", [
       ...
       "heartbeat_dir", "heartbeat_interval_minutes",
   ]),
   ```
3. **Документируй** в [`configuration.md`](configuration.md) — добавь строку в таблицу группы (default, type, per-proj scope, описание, example).
4. **Используй через resolver** в роутах:
   ```python
   resolver.get(project, "heartbeat_dir", "")
   ```
5. **НЕ забудь** что bool-поля в `/settings` HTML обрабатываются через тройку: hidden=`false` + checkbox=`true` (HTML idiom).
6. **Если поле secret** (token/api_key) — UI auto-render как `type=password` (логика в `templates/settings.html`). Имена-обозначители: содержит `token`, `api_key`, `password`.

Изменения автоматически попадут в:
- `/settings` форму (через SETTINGS_GROUPS).
- `/p/{slug}/settings` форму (через тот же SETTINGS_GROUPS).

## Adding a scheduled job

### Per-project job

1. **Напиши job-функцию** в `dreaming/services/scheduler.py`:
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
2. **Добавь в `_PER_PROJECT_JOBS`**:
   ```python
   _PER_PROJECT_JOBS = [
       ...
       ("weekly_heartbeat_check", "weekly_heartbeat_check_cron", "weekly_heartbeat_check_enabled",
        "0 8 * * 1", False, _weekly_heartbeat_check),
   ]
   ```
3. **Добавь settings keys** в `AppSettings`: `weekly_heartbeat_check_cron` + `weekly_heartbeat_check_enabled` (см. [Adding a settings key](#adding-a-settings-key)).
4. **Добавь в `SETTINGS_GROUPS`** в группу `"Scheduling — weekly (opt-in)"`.

При следующем `register_project_jobs(scheduler, app_state, proj)` (вызов автоматически в setup/toggle/import) job будет зарегистрирована.

### Глобальный job (не per-project)

В `build_scheduler` ([`scheduler.py:219`](../dreaming/services/scheduler.py)):

```python
def build_scheduler(app_state) -> AsyncIOScheduler:
    sched = AsyncIOScheduler()
    sched.add_job(_reconcile_job, "interval", minutes=5, args=[app_state],
                  id="reconcile_stale_sessions")
    # Новый:
    sched.add_job(_my_global_job, "cron", hour=3, minute=0, args=[app_state],
                  id="my_global_job")
    return sched
```

## Writing a parser service

Стандартная форма (mirror'ится с `evolutions.py`, `loops.py`, `plans.py`, `contracts.py`):

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
- Первый аргумент — путь, не settings. (Project-aware.)
- Если каталог не существует — возвращай `[]`, **не raise**.
- `OSError` ловится per-file — один битый файл не должен валить весь list.
- Если хочешь YAML вместо custom regex — используй `yaml.safe_load` (см. tech_debt.py:108).

## DB conventions

- **Все таблицы с `project_id`** объявляют его как `INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE`. См. примеры в `_SCHEMA`.
- **Денормализация vs JOIN**: денормализуем `project_id` в hot-path таблицы (`agent_learning_sessions`, `orchestrator_runs`, `orchestrator_nodes`, `orchestrator_messages`, `ai_usage_events`, `ai_usage_files`). Не денормализуем в child-таблицы где project достаётся через JOIN с run'ом (`orchestrator_events`, `orchestrator_stages`, `orchestrator_gate_verdicts`, `orchestrator_artifacts`).
- **Idempotent migrations**: ВСЕГДА `IF NOT EXISTS` / try/except. Никогда не делай `ALTER TABLE ADD COLUMN ... NOT NULL` без default'а — SQLite этого не любит. См. `_migrate_orchestration` ([`db.py:282`](../dreaming/services/db.py)).
- **PK rebuild discipline**: SQLite не умеет `ALTER PRIMARY KEY`. Если нужно поменять PK (как мы сделали для `agent_learning_rotation`):
  1. Создай новую таблицу с правильным PK.
  2. INSERT INTO ... SELECT FROM старая.
  3. DROP TABLE старая.
  4. ALTER TABLE новая RENAME TO старое имя.
  В нашем случае мы стартанули greenfield, поэтому ребилда не было — просто `_SCHEMA` объявляет правильный PK сразу.
- **Timestamps** хранятся как ISO-строки UTC (`datetime.now(timezone.utc).isoformat()`). Парсятся через `_fmt_dt` Jinja-фильтра в base.html (если он есть, либо вручную в шаблоне).
- **UUID v4** для всех string PK. Используй `uuid.uuid4()` или `str(uuid4())`.

## Testing approach

**Test framework нет** — это сознательное решение, унаследованное из ALC. Причины:
- Бо'льшая часть кода — IO (subprocess, БД, FS). Mock'ать всё непродуктивно; smoke test покрывает реальный путь.
- Schema migrations идемпотентны — повторный run на расколотом БД ловится сразу.
- Routes есть curl-тестируемые — внешний контракт легко проверить.

Smoke-сценарии живут в [`scripts/`](../scripts/):

| Скрипт | Что проверяет |
|---|---|
| `smoke_db_methods.py` | DB CRUD методы (sessions, rotation, topics). |
| `smoke_pm_api.py` | ProcessManager spawn/kill цикл. |
| `smoke_session.py` | Sessions API (POST start/finish). |
| `smoke_pipelines.py` | Парсеры (tech-debt, ideas, contracts, ...). |
| `smoke_resolver.py` | ConfigResolver override-with-fallback. |
| `smoke_setup.py` | Setup wizard flow. |
| `smoke_scan.py` | scan_projects_root. |
| `smoke_seed_one.py` | Seed одного проекта в DB. |
| `smoke_i18n.py` | Загрузка messages + plurals. |
| `check_i18n.py` | RU/EN keys parity. |

Запуск:

```bash
python scripts/smoke_session.py
python scripts/check_i18n.py    # exit 0 если parity OK
```

Если ты добавил фичу — добавь smoke (или extend существующий). См. `docs/smoke-tests.md`.

## i18n discipline

- Все user-facing строки в шаблонах через `{{ "key.path" | t(locale=locale) }}`.
- Default locale `ru` — добавляй сначала в `messages_ru.json`, затем зеркаль в `messages_en.json`.
- **Каждый ключ должен быть в обоих файлах**. `scripts/check_i18n.py` валит build (exit code 1) если есть divergence.
- Naming: `<area>.<sub>` или `<area>.<sub>.<sub2>`. Примеры: `common.app_name`, `navbar.all_projects`, `p.dashboard`, `p.metrics.success`, `settings.title`.
- Plurals: используй `i18n.plural("count.runs", n, locale=locale)` — он добавит `.one`/`.few`/`.many` для RU и `.one`/`.other` для EN.

См. подробно [`features/i18n.md`](features/i18n.md).

## Git conventions

- **Один commit — одна логическая единица**. Wave 1, Wave 2.5, конкретная фича.
- **Conventional commits**: `feat:`, `fix:`, `docs:`, `chore:`, `test:`. Например:
  ```
  feat: per-project nightly_learning_{slug} cron + (un)register hooks on toggle/delete/import
  fix: setup wizard — default projects_root + scan_error message + hint
  docs: add CLAUDE.md with architecture guide for future Claude sessions
  ```
- **Один тег на волну**: `wave-0`, `wave-1`, `wave-2`, ..., `wave-5`. Pushable, но не обязательно.
- **Don't commit secrets**. `config.yaml` и `data/dreaming.db` — в `.gitignore`. Token'ы только через env vars или wizard input.

### Commit message body

Если изменения нетривиальные, добавь body:

```
feat: Wave 3.7 — orchestration spawns claude + ClaudeSessionTail/SubagentWatcher + live polling + resume

- POST /p/{slug}/orchestration/start теперь спавнит claude
  и стартует ClaudeSessionTail + SubagentWatcher.
- /refresh endpoint для polling'а из браузера.
- /resume для claude --resume <session_id>.
- Sessions backfill сохранён.
```

### Encoding на Windows

При создании файлов с Cyrillic content **НЕ используй** `Set-Content` (PowerShell 5.1 default = UTF-16 LE) — Jinja2 и check_i18n.py не прочитают. Используй:
- `Write` tool (UTF-8 без BOM).
- В скриптах: `[System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($false))` — UTF-8 без BOM.
- Или `Out-File -Encoding utf8` — но в PS5.1 он добавит BOM. Лучше first option.

См. также [`troubleshooting.md`](troubleshooting.md) (mojibake).

## Cross-references

- Архитектура — [`architecture.md`](architecture.md).
- Парсеры (примеры) — [`services.md`](services.md).
- i18n — [`features/i18n.md`](features/i18n.md).
- Wave-история — [`waves.md`](waves.md).
