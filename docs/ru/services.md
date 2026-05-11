# Service Layer Reference

Все модули под [`dreaming/services/`](../dreaming/services/) сгруппированы по назначению. Для каждого приведено: краткое назначение, публичный API (классы / функции с сигнатурой), пара ключевых заметок про поведение.

## Содержание

- [Storage](#storage)
- [Processes](#processes)
- [Orchestration](#orchestration)
- [Pipeline parsers](#pipeline-parsers)
- [Cross-cutting](#cross-cutting)

## Storage

### `db.py` — `SqliteDB`

Async SQLite wrapper. Один persistent connection, WAL mode, schema-on-connect, ~30 domain methods.

```python
class SqliteDB:
    def __init__(self, path: str)
    async def connect() -> None
    async def close() -> None
    async def execute(sql: str, params: tuple = ()) -> None
    async def fetch_one(sql, params) -> Row | None
    async def fetch_all(sql, params) -> list[Row]

    # Sessions
    async def create_session(project_id, agent_name, model="sonnet") -> str
    async def get_or_create_session(project_id, agent_name, model, reuse_window_sec=120) -> str
    async def finish_session(session_id, status, **kwargs) -> bool
    async def cancel_session(session_id) -> bool
    async def cancel_stale_running(project_id) -> int        # mass-cancel all running rows
    async def delete_session(session_id) -> bool             # hard-delete row
    async def list_sessions(project_id, limit=50) -> list
    async def list_running_sessions(project_id) -> list
    async def week_stats(project_id) -> dict

    # Rotation
    async def list_rotation(project_id) -> list
    async def next_agents_for_nightly(project_id, count=5) -> list
    async def upsert_agent_rotation(project_id, agent_name, tier=2, last_studied_at=None)
    async def set_agent_tier(project_id, agent_name, tier)
    async def set_agent_enabled(project_id, agent_name, enabled: bool)

    # Custom topics
    async def list_custom_topics(project_id, active_only=True) -> list
    async def list_custom_topics_for_agent(project_id, agent_name) -> list
    async def add_custom_topic(project_id, title, ...) -> str
    async def delete_custom_topic(project_id, topic_id) -> bool

    # _migrate_orchestration  -> ALTER + new orchestrator_questions table
```

**Ключевое**: `connect()` вызывает PRAGMA outside `executescript` (db.py:275 — иначе `journal_mode=WAL` молча игнорируется). Auto-creates parent dir. Полный список таблиц — в [`schema.md`](schema.md).

`finish_session` дополнительно бьёт `agent_learning_rotation.last_studied_at` если row найден (db.py:425).

`reconcile_stale_sessions` (упоминается в `process_manager._cleanup`) ожидается в db.py для production-вызова, но в текущей кодовой базе не определён — вместо этого PM сам кикает orphan'ы через свой `pm.reconcile_stale_sessions(active_pairs)` (process_manager.py:699), который проходит по in-memory `running` dict.

### `projects.py` — `ProjectsService`, `Project`, `scan_projects_root`

Реестр проектов + scan filesystem'а.

```python
@dataclass
class Project:
    id: int; slug: str; label: str; working_dir: str
    enabled: bool; is_default: bool; sort_order: int
    color: Optional[str]; created_at: str; updated_at: str

class ProjectsService:
    def __init__(self, db: SqliteDB)
    async def list_all(only_enabled=False) -> list[Project]
    async def get_by_slug(slug) -> Project | None
    async def get_by_id(project_id) -> Project | None
    async def get_default() -> Project | None
    async def create(slug, label, working_dir, enabled=True, is_default=False, ...) -> Project
    async def update(project_id, **kwargs) -> None  # поля из allowed-set
    async def delete(project_id) -> None

    async def set_setting(project_id, key, value) -> None     # JSON-encode
    async def unset_setting(project_id, key) -> None
    async def get_setting(project_id, key)
    async def all_settings(project_id) -> dict

    @staticmethod
    def scan_projects_root(root: str) -> list[dict]   # [{path, name, suggested_slug, suggested_label, has_claude}]
    async def import_from_scan(items: list[dict], default_slug=None) -> list[Project]
```

**Идемпотентность `import_from_scan`** (projects.py:156–189): пропускает items по `working_dir` или `slug`, который уже зарегистрирован. Если slug коллизит, добавляет суффикс `-2`, `-3`, ... .

`set_setting` всегда JSON-encoded (`json.dumps(value)`), `get_setting` decode'ит.

### `config_resolver.py` — `ConfigResolver`

Override-with-fallback: per-project value → global setting → default.

```python
class ConfigResolver:
    def __init__(self, projects: ProjectsService, global_settings: AppSettings)
    async def get(self, project: Project | None, key: str, default = SENTINEL)
    def invalidate_project(project_id: int) -> None
```

Per-request кэш `_cache: dict[int, dict]` — на N запросов одного project'а делается один SELECT (config_resolver.py:18).

`get_resolver(request)` фабрика в `main.py:69` — создаёт fresh resolver на каждый request чтобы кэш не накапливался между запросами.

См. [`features/settings.md`](features/settings.md).

## Processes

### `process_manager.py` — `ProcessManager`, `RunningSession`

Управление subprocess'ами Claude CLI. Один экземпляр на app (см. main.py:41). Холдит `running: dict[str, RunningSession]` с composite-key.

```python
@dataclass
class RunningSession:
    session_id: str; agent_name: str
    project_id: int; project_slug: str
    process: asyncio.subprocess.Process
    output_lines: list[str]              # ring buffer (5000)
    subscribers: list[asyncio.Queue]     # SSE
    started_at: float; last_stdout_at: float
    _reader_task: Task; _watchdog_task: Task
    key: str  # ключ в pm.running

    async def send_user_message(text) -> bool   # stream-json в stdin

class ProcessManager:
    def __init__(self, settings, db, projects, env_resolver=None)
    async def start_session(project, *, agent_name, claude_path, working_dir,
                            model="sonnet", max_turns=25, timeout_minutes=20,
                            self_study_command="/self-study", extra_prompt="",
                            env_overrides=None) -> str
    async def start_command(project, *, command_name, prompt, claude_path,
                            working_dir=None, model="sonnet", max_turns=25,
                            timeout_minutes=30, env_overrides=None,
                            session_id=None, resume_session_id=None,
                            interactive_stdin=False) -> str
    async def start_raw_command(project, *, command_name, argv, ...) -> str
    async def kill(key: str) -> bool
    async def kill_session(key) -> bool      # alias of kill
    async def kill_all() -> None
    def subscribe(key, catchup_lines=100) -> tuple[list[str], Queue] | None
    def stream_subscriber(key) -> AsyncGenerator
    def get_session_output(key) -> list[str] | None
    def get_running_agents() -> list[str]
    def list_running() -> dict[str, RunningSession]
    async def reconcile_stale_sessions(active_pairs: list[tuple[int, str]]) -> int
```

**Composite keys**:
- `"{slug}:{agent_name}"` — self-study (`start_session`).
- `"cmd:{slug}:{command_name}"` — slash-команды и raw (`start_command` / `start_raw_command`).

`_resolve_claude_path` (process_manager.py:31) использует `shutil.which` чтобы на Windows подобрать `claude.cmd` вместо bash-скрипта `claude`.

`_parse_stream_json` (process_manager.py:398) парсит stream-json от claude в человекочитаемые строки `[tool] Bash: ls -la`, `[done] status=ok cost=$0.34` и т.д.

`_watchdog` (process_manager.py:544) — это **silence-watchdog**, не lifetime-watchdog: убивает процесс если `time.time() - last_stdout_at >= timeout_minutes*60`. Если есть pending question в `orchestrator_questions` (process_manager.py:575), сбрасывает счётчик (валидное ожидание ответа пользователя).

`STDOUT_BUFFER_LIMIT = 16 MB` (process_manager.py:28) — поднят с дефолтных 64KB чтобы readline не падал на гигантских assistant-блоках.

При `LimitOverrunError` (process_manager.py:502) — выкачиваем оставшийся chunk до `\n`, логируем warn, продолжаем (не падаем).

`KeepAwake.acquire()` бьётся при каждом spawn'е, `release()` — при каждом cleanup'е (refcount).

`_cleanup` зовёт `db.reconcile_stale_sessions(active_pairs, learning_notes_dir, grace_minutes=2)` — не определено в db.py текущей версии, ловит exception (process_manager.py:633).

### `keep_awake.py` — `KeepAwake`

Windows-only refcount guard. На non-Windows — no-op.

```python
class KeepAwake:
    def __init__()
    def acquire()    # refs++; если refs==1 → SetThreadExecutionState(ON)
    def release()    # refs--; если refs==0 → SetThreadExecutionState(OFF)
    @property
    def active() -> bool
```

Вызывает `kernel32.SetThreadExecutionState` с флагами `ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED` (keep_awake.py:49). Дисплей всё равно может выключаться нормально.

История: добавлено после инцидента 05.05 — машина уснула в Modern Standby в 06:53, каскад умер в 07:03. См. комментарий в process_manager.py:96–98.

### `scheduler.py` — `build_scheduler`, `register_project_jobs`, `unregister_project_jobs`

Глобальные + per-project APScheduler jobs.

```python
def build_scheduler(app_state) -> AsyncIOScheduler   # + reconcile + ai_usage_ingest
async def register_project_jobs(scheduler, app_state, project) -> None
async def unregister_project_jobs(scheduler, project) -> None

# Список per-project jobs:
_PER_PROJECT_JOBS = [
    ("nightly_learning", "cron_expression", "cron_enabled", "0 2 * * *", True, _nightly_learning),
    ("weekly_tech_debt_scan", ..., False, _weekly_tech_debt_scan),
    ("weekly_product_ideas_scan", ..., False, _weekly_product_ideas_scan),
    ("weekly_wiki_lint", ..., False, _weekly_wiki_lint),
]
```

Глобальные jobs (scheduler.py:223–230):
- `reconcile_stale_sessions` — interval 5 min, через `_reconcile_job` собирает active_pairs из `pm.list_running()` и делегирует `pm.reconcile_stale_sessions`.
- `ai_usage_ingest` — interval 5 min, вызывает `ai_usage_parser.ingest_ai_usage`.

`register_project_jobs` (scheduler.py:181) — для каждого `(kind, ...)` из `_PER_PROJECT_JOBS`:
1. resolver.get(`enabled_key`) → если false, `remove_job` (молча игнорит ошибку).
2. resolver.get(`cron_key`) → cron expression.
3. `scheduler.add_job(fn, CronTrigger.from_crontab(cron_expr), args=[app_state, project.id], id=f"{kind}_{slug}", replace_existing=True)`.

Hooks вызова:
- При создании проектов в setup wizard'е ([`setup.py:108`](../dreaming/routes/setup.py)).
- При `POST /projects/{id}/toggle` ([`projects.py:32`](../dreaming/routes/projects.py)).
- При `POST /projects/{id}/delete` ([`projects.py:43`](../dreaming/routes/projects.py)).
- При `POST /projects/import` ([`projects.py:62`](../dreaming/routes/projects.py)).

## Orchestration

### `orchestration_hub.py` — `OrchestrationHub`

DB-backed runs/nodes/messages/stages/verdicts/artifacts/events.

```python
class OrchestrationHub:
    def __init__(self, db, projects)

    # Runs
    async def create_run(project_id, goal, external_id=None) -> str
    async def get_run(run_id)
    async def list_runs(project_id, limit=50) -> list
    async def has_running_run(project_id) -> str | None  # run_id или None
    async def finish_run(run_id, status="completed", error_message=None) -> bool

    # Nodes
    async def create_node(run_id, project_id, agent_name, role="executor",
                          parent_node_id=None, external_id=None) -> str
    async def list_nodes(run_id) -> list
    async def update_node_status(node_id, status) -> None

    # Messages
    async def append_message(run_id, node_id, project_id, author, kind, text,
                             client_message_id=None) -> str
    async def list_messages(run_id) -> list
    async def list_messages_for_node(node_id) -> list

    # Events
    async def append_event(run_id, event_type, payload: dict) -> None
    async def list_events(run_id, limit=200) -> list

    # Stages
    async def ensure_stage(run_id, stage_index, stage_key, label) -> str  # idempotent
    async def start_stage(stage_id) -> None
    async def finish_stage(stage_id, status="completed") -> None
    async def list_stages(run_id) -> list
    async def get_stage(stage_id)

    # Gate verdicts
    async def record_gate_verdict(run_id, stage_id, verdict, ...) -> str
    async def list_gate_verdicts(run_id) -> list

    # Artifacts (with dedup_hash)
    async def append_artifact(run_id, kind, title, ..., dedup_hash=None) -> str | None
    async def list_artifacts(run_id) -> list
```

`has_running_run` нужно для one-Roman-per-project lock'а. Использовать перед `create_run` если хотим enforce.

`append_artifact` ловит exception на UNIQUE-constraint и возвращает `None` (orch_hub.py:227).

### `claude_session_tail.py` — `ClaudeSessionTail`, `tail_session_file`, helpers

Tail-watcher для `~/.claude/projects/<workdir>/<session>.jsonl`.

```python
def encode_workdir(working_dir: str) -> str   # alphanumeric+- encoding
def claude_projects_root(home=None) -> Path    # ~/.claude/projects
def session_file_path(working_dir, session_id, home=None) -> Path
def subagents_dir(working_dir, session_id, home=None) -> Path
def find_session_file(working_dir, session_id=None, home=None) -> Path | None
def find_session_file_by_id(session_id, claude_projects_dir=None) -> Path | None
def find_recent_session_files(working_dir, limit=10, home=None) -> list[Path]
def find_session_for_goal(working_dir, goal, after_iso=None, home=None) -> Path | None

async def tail_session_file(*, run_id, node_id, project_id, path, hub, db,
                            seen_uuids=None, poll_interval=1.0,
                            stop_event=None, idle_finalize_after=None) -> int

class ClaudeSessionTail:
    def __init__(self, run_id, jsonl_path, hub, db)
    async def start() -> None       # idempotent
    async def stop() -> None        # idempotent
```

**Ключевые функции**:

`encode_workdir` — кодирует путь так же, как Claude CLI: каждый non-alnum символ заменяется на `-`. На Windows `D:\Work\micode\rgs-frontend` → `D--Work-micode-rgs-frontend`.

`tail_session_file` — поэтапно:
1. **Catchup**: читает весь существующий jsonl, гонит через `_ingest_line`. Записывает `seen_uuids` чтобы не дублировать.
2. **Live tail loop**: пуллит `path.stat()` каждый `poll_interval` (1s default), читает новые байты с offset'а, ингестит. Детектирует rotation/truncation через inode change.
3. Если `idle_finalize_after` задан — после `idle` секунд молчания `update_node_status('completed')` и выходит.

`_ingest_line` (claude_session_tail.py:276) парсит JSONL line:
- если `type` не in `("assistant", "user")` — skip.
- если `uuid` уже в `seen` — skip.
- `_extract_text_from_message` (claude_session_tail.py:211) собирает текст из `text` / `tool_use` (через `_summarize_tool_use`) / `tool_result` блоков.
- `append_message(...)` + `append_event("message_added", ...)`.

### `subagent_watcher.py` — `SubagentWatcher`, `watch_subagents_for_run`, `_resolve_node_for_subagent`

Watch'ер за `subagents/agent-*.meta.json`.

```python
async def watch_subagents_for_run(*, run_id, parent_node_id, folder, hub, db,
                                  poll_interval=1.0, stop_event=None,
                                  tails=None) -> dict[str, asyncio.Task]
async def stop_subagent_tails(tails: dict) -> None
async def _resolve_node_for_subagent(*, hub, db, run_id, project_id,
                                     parent_node_id, agent_type, description,
                                     agent_hash) -> str | None

class SubagentWatcher:
    def __init__(run_id, parent_node_id, hub, db, claude_projects_dir=None)
    async def start() -> None
    async def stop() -> None
```

Логика: один subagent_hash = один node. Если node с `external_id == agent_hash` уже существует — reuse. Иначе создаёт worker-ноду parent'ом на parent_node_id.

`SubagentWatcher.start` (subagent_watcher.py:214) lazy-резолвит folder через `_resolve_folder` (subagent_watcher.py:189) — ищет `~/.claude/projects/**/<external_id>.jsonl` и берёт `parent / <external_id> / subagents`.

Каждый новый subagent file получает свой `tail_session_file` task с `idle_finalize_after=30.0` — finalized'ится автоматически через 30 секунд тишины.

### `subagent_backfill.py` — `backfill_run`

Offline reconstruction. Replays JSONL'ы run'а в orchestration tables.

```python
async def backfill_run(run_id, db, hub, claude_projects_dir=None) -> int
```

Используется когда watcher был offline или run предшествует Wave 3. Не идемпотентен на DB-level — повторный вызов на already-backfilled run даст дубликаты (subagent_backfill.py:14–17).

### `harness_client.py` — `HarnessClient`, `HarnessClientCache`

HTTP/SSE адаптер к внешнему harness API (если используется вместо локального claude CLI). Permissive в parsing (поддерживает run_id в `data.run_id`, `external_id`, `id`).

```python
class HarnessClient:
    def __init__(self, settings=None, **kwargs)
    @property
    def enabled(self) -> bool   # True если base_url задан
    async def start_orchestration(goal, meta=None) -> str   # run_id
    async def send_input(*, run_external_id, node_external_id, text) -> dict
    async def stream_events(external_run_id) -> AsyncIterator[dict]   # SSE
    async def fetch_events(external_run_id, since=None) -> tuple[list[dict], str | None]
    async def simulated_agent_reply(agent_name, text) -> str
    async def close() -> None

class HarnessClientCache:
    async def get_for_project(project, resolver) -> HarnessClient | None
    def invalidate(project_id) -> None
```

`stream_events` — SSE с fallback на NDJSON. `_normalize_event` (harness_client.py:215) маппит aliases (`spawn` → `node_created`, `chat` → `message_added` и т.д.).

`HarnessClientCache.get_for_project` (harness_client.py:250) ленивый — резолвит `harness_*` настройки через `ConfigResolver.get(project, key)`. Если `harness_base_url` пуст — возвращает None.

### `cascade_stage_detect.py` — `detect_stage`

Heuristic: по `agent_name + description` → stage_key.

```python
def detect_stage(agent_name: str, description: str = "") -> str | None
```

Возвращает one of `'contract' | 'design' | 'implementation' | 'review' | 'qa'` либо None.

Правила в `_RULES` (cascade_stage_detect.py:17–57): порядок rules важен — first match wins.

### `tts_backfill.py` — `backfill_tts` (stub)

Wave 3.9 stub:

```python
async def backfill_tts(run_id, db, hub, claude_projects_dir=None) -> int   # always 0
```

Полная реализация отложена.

## Pipeline parsers

Все парсеры — project-aware: первый аргумент это путь к директории, не глобальный settings.

### `tech_debt.py`

```python
@dataclass
class TechDebtItem: id, title, status, priority, module, ..., file_path
@dataclass
class ReleaseItem: release, target_date, status, description, file_path

def parse_tech_debt(td_dir) -> list[TechDebtItem]
def list_tech_debt(td_dir)        # alias
def read_tech_debt_item(td_dir, item_id) -> TechDebtItem | None
def parse_releases(td_dir) -> list[ReleaseItem]
def close_tech_debt_item(td_dir, item_id) -> bool   # rewrite frontmatter
def delete_tech_debt_item(td_dir, item_id) -> bool  # unlink file
def find_td_file(td_dir, td_id) -> Path | None
def read_td(file_path) -> tuple[dict, str]          # (frontmatter, body)
```

`_iter_td_paths` (tech_debt.py:73) пробует `{td_dir}/items/TD-*.md` (ALC layout) и фоллбэчит на `{td_dir}/TD-*.md` или `{td_dir}/*.md` (flat micode layout).

`close_tech_debt_item` (tech_debt.py:191) — regex-замена `^status:.*$` на `status: closed`. Если нет — добавляет в frontmatter.

### `product_ideas.py`

```python
@dataclass
class ProductIdeaItem: id, title, status, impact, effort, confidence, priority,
                       ..., jira_ticket, jira_epic, jira_task, value_hypothesis,
                       file_path

def list_product_ideas(ideas_dir) -> list[ProductIdeaItem]
def parse_product_ideas(ideas_dir)   # alias
def read_product_idea(file_path) -> tuple[dict, str]
def read_idea_slug(file_path) -> str   # из PI-NNN-<slug>.md
```

Mirror'ится с `tech_debt.py`. Same fallback layout (`items/PI-*.md` → `PI-*.md` → `*.md`).

### `contracts.py`

```python
@dataclass
class ContractItem: path, name, kind, module, page, status, last_review_at, raw_frontmatter

def list_contracts(contracts_dir) -> list[ContractItem]
```

`kind` ∈ {`module`, `page`, `unknown`}.

### `sidecar_findings.py`

```python
@dataclass
class SidecarFinding: source_file, reviewer, id, title, severity, module, file, rule, raw

def list_sidecar_findings(sidecar_dir) -> list[SidecarFinding]
```

JSON parser. Reviewer = parent dir name либо file stem (sidecar_findings.py:43).

### `wiki_data.py`

```python
@dataclass
class WikiStatus: wiki_dir, exists, domains_count, domains   # first 20 names

def get_wiki_status(wiki_dir) -> WikiStatus
```

Пробует `{wiki_dir}/domains/*.md`, фоллбэчит на `{wiki_dir}/*.md`.

### `evolutions.py`

```python
@dataclass
class EvolutionItem: path, name, agent_name, title, status, has_conflict, raw_frontmatter

def list_evolutions(evolutions_dir) -> list[EvolutionItem]
```

### `loops.py`

```python
@dataclass
class LoopItem: path, name, title, status, iterations, raw_frontmatter

def list_loops(loops_dir) -> list[LoopItem]
```

### `plans.py`

```python
@dataclass
class PlanItem: path, name, title, status, done, todo, progress_pct, raw_frontmatter

def list_plans(plans_dir) -> list[PlanItem]
```

`progress_pct` = `done * 100 // total` где `done` — чекбоксы `- [x]`, `todo` — `- [ ]` (plans.py:14, 56).

### `cascade_costs.py`

```python
@dataclass
class CascadeRunCost: run_id, project_id, goal, status, started_at, finished_at,
                       total_cost_usd, event_count

async def list_cascade_costs(db, project_id, limit=50) -> list[CascadeRunCost]
```

Суммирует `cost_usd` или `total_cost_usd` из `orchestrator_events.payload_json` каждого run'а.

### `notes.py`

```python
class NoteEntry(NamedTuple): relative_path, full_path, size, mtime

def list_notes(notes_dir, max_items=200) -> list[NoteEntry]
def read_note(notes_dir, relative_path) -> str | None   # path-traversal-safe
```

`read_note` (notes.py:34) делает `Path(notes_dir).resolve() / Path(relative_path).resolve()` и проверяет startswith — защита от `..`.

### `checklist.py`

```python
@dataclass
class ChecklistTopic: number, title, module, target_agents, question,
                       why_important, completed

def parse_checklist(agents_dir) -> tuple[str, list[ChecklistTopic]]   # (week_label, topics)
def parse_weekly_checklist(text: str) -> list[ChecklistTopic]
```

Парсит `_weekly-learning-checklist.md`. Skip-секции: «Приоритет недели», «Общие (любой агент)» (checklist.py:37–42).

### `agents.py`

```python
def list_agent_names(working_dir: str) -> list[str]
```

Сканирует `{working_dir}/.claude/agents/`. Поддерживает single-file `.md` и multi-file dir с `{name}.md` или `agent.md`.

### `jira.py`

```python
class JiraError(RuntimeError): ...

async def create_task(settings, *, summary, item_id, item_url, description="",
                      project_key_override=None, kind="идея") -> dict
```

POST на `{jira_url}/rest/api/3/issue`. Аутентификация — `(jira_email, jira_api_token)`. ADF-описание с link обратно (jira.py:25–46).

`_extract_error` (jira.py:114) пытается достать понятное сообщение из Jira error body.

## Cross-cutting

### `i18n.py` — `I18n`, `russian_plural`, `english_plural`

```python
class I18n:
    def __init__(self, base_dir: Path)   # читает messages_ru.json + messages_en.json
    def t(self, key: str, locale: str | None = None, **fmt) -> str
    def plural(self, key_base: str, n: int, locale: str | None = None) -> str

def russian_plural(n: int) -> str   # 'one' | 'few' | 'many' (CLDR)
def english_plural(n: int) -> str   # 'one' | 'other'
```

Fallback chain: `locale → 'ru' → key`. Если есть `**fmt` — форматирует через `str.format`, ловит `KeyError/IndexError`.

`russian_plural` (i18n.py:42–50) — CLDR rules: `mod10==1 && mod100!=11 → one`, `mod10 in (2,3,4) && mod100 not in (12,13,14) → few`, иначе `many`.

См. [`features/i18n.md`](features/i18n.md).

### `ai_usage_parser.py` — `ingest_ai_usage`, helpers

Incremental JSONL parser → `ai_usage_events` rows.

```python
def resolve_claude_projects_root(override=None) -> Path
def discover_jsonl_files(root) -> Iterator[(Path, is_subagent, slug)]
async def build_cwd_to_project_id(db) -> dict[str, int]
def parse_line(raw, *, project_slug, source_file, source_line) -> dict | None
def read_new_lines(path, offset, size) -> tuple[list[bytes], int]
async def ingest_ai_usage(db, projects, claude_projects_dir=None,
                          max_files=1000, batch_size=500) -> dict
```

`ingest_ai_usage` (ai_usage_parser.py:255):
1. `build_cwd_to_project_id(db)` — мап `_norm_for_match(working_dir) → project_id`.
2. `discover_jsonl_files(root)` — yield все JSONL'ы, `is_subagent` = `parent.name == 'subagents'`.
3. Per file: `read_new_lines(path, stored_offset, st.st_size)` → list of complete lines + new_offset.
4. `parse_line` каждой строки. Если `cwd` нет в map → `events_skipped++`.
5. `_insert_events(db, project_id, rows)` batch INSERT OR IGNORE.
6. `_upsert_file` — сохраняет new offset + counters.
7. Files которые исчезли с диска → `_mark_missing` (is_missing=1).

Возвращает `{files, events_inserted, events_skipped, errors, duration_ms}`.

### `ai_usage_stats.py` — aggregates

```python
async def project_summary(db, project_id) -> {project_id, last_7d, last_30d, by_model}
async def global_summary(db) -> {last_7d, last_30d, by_project, events_total}
```

Внутри: `_totals` / `_by_model` / `_by_project` (private). Все запросы по `ts_date BETWEEN ? AND ?`.

### `starter_kit.py` — установка slash-команд

Bootstrap «из коробки»: `templates/starter-kit/` в репо DC зеркалится в `{working_dir}/.claude/` целевого проекта.

```python
@dataclass
class StarterKitStatus:
    template_files: list[str]      # relative paths from templates/starter-kit/
    installed: list[str]
    missing: list[str]
    all_present: bool
    template_root: str

@dataclass
class InstallResult:
    copied: list[str]
    overwritten: list[str]
    skipped: list[str]
    dry_run: bool

def status(working_dir) -> StarterKitStatus
def install(working_dir, *, force=False, dry_run=False) -> InstallResult
```

Реализация (`dreaming/services/starter_kit.py`):
- `TEMPLATE_DIR = <repo>/templates/starter-kit`.
- `_template_files()` рекурсивно `rglob('*')` под `TEMPLATE_DIR`.
- `install()` обходит каждый файл, считает rel-path, проверяет existence в target, копирует через `shutil.copy2`. По умолчанию **skip if exists** — overwrite только с `force=True`.

Используется:
- Routes: `dreaming/routes/project_rotation.py` (POST `/p/{slug}/starter-kit/install`), `dreaming/routes/project_rotation.py:rotation_page` (status в context), `dreaming/routes/project_topics.py:topics_page` (status для inline-кнопки).
- CLI: `scripts/install_starter_kit.py`.

См. [`features/out-of-the-box.md`](user/features/out-of-the-box.md#starter-kit).

### `autoconfig.py` — one-click per-project directories

Дефолтные пути для всех `*_dir` настроек + создание каталога + сохранение override'а.

```python
DEFAULTS: dict[str, str] = {
    "tech_debt_dir":         "docs/tech-debt",
    "product_ideas_dir":     "docs/product-ideas",
    "wiki_dir":              "docs/wiki",
    "evolutions_dir":        ".claude/agents/_context",
    "loops_dir":             "docs/loops",
    "plans_dir":             "docs/plans",
    "contracts_dir":         "docs/contracts",
    "sidecar_findings_dir":  ".claude/agents/sidecar-findings",
    "learning_notes_dir":    ".claude/agents/learning-notes",
    "findings_dir":          "docs/findings",
}

def default_abs(project, key: str) -> str | None
async def apply(projects_svc, project, key: str) -> str
```

`apply()` (`autoconfig.py:35`):
1. `Path(abs_path).mkdir(parents=True, exist_ok=True)`.
2. `projects_svc.set_setting(project.id, key, abs_path)` — JSON-encoded в `project_settings`.
3. Возвращает абсолютный путь (полезно для логов).

Используется:
- Route: `dreaming/routes/project_settings.py` (POST `/p/{slug}/settings/autoconfig`).
- Per-page routes: каждый из 8 dashboard-routes (`project_tech_debt.py`, `project_ideas.py`, `project_wiki.py`, `project_evolutions.py`, `project_loops.py`, `project_plans.py`, `project_contracts.py`, `project_sidecar_findings.py`) импортит `autoconfig` и передаёт `default_abs(project, key)` в шаблон как `autoconfig_default`.
- Jinja: `dreaming/templates/_autoconfig_banner.html` (макрос `autoconfig_banner(project, key, default_path, what)`).

См. [`features/out-of-the-box.md`](user/features/out-of-the-box.md#autoconfig-каталогов).

## Cross-references

- Какие endpoint'ы дёргают какие сервисы — [`api.md`](api.md), [`routes.md`](routes.md).
- Что хранится в БД — [`schema.md`](schema.md).
- Что и куда конфигурируется — [`configuration.md`](configuration.md).
