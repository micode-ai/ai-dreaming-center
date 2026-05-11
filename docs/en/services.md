# Service Layer Reference

Every module under [`dreaming/services/`](../../dreaming/services/) grouped by purpose. For each one we list: short purpose, public API (classes / functions with signatures), a couple of key behavioural notes.

## Contents

- [Storage](#storage)
- [Processes](#processes)
- [Orchestration](#orchestration)
- [Pipeline parsers](#pipeline-parsers)
- [Cross-cutting](#cross-cutting)

## Storage

### `db.py` — `SqliteDB`

Async SQLite wrapper. One persistent connection, WAL mode, schema-on-connect, ~30 domain methods.

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

**Key**: `connect()` calls PRAGMA outside `executescript` (db.py:275 — otherwise `journal_mode=WAL` is silently ignored). Auto-creates the parent dir. Full table list — in [`schema.md`](schema.md).

`finish_session` additionally bumps `agent_learning_rotation.last_studied_at` if the row is found (db.py:425).

`reconcile_stale_sessions` (mentioned in `process_manager._cleanup`) is expected in db.py for the production call, but in the current codebase it isn't defined — instead PM kicks orphans itself via its `pm.reconcile_stale_sessions(active_pairs)` (process_manager.py:699), which walks the in-memory `running` dict.

### `projects.py` — `ProjectsService`, `Project`, `scan_projects_root`

Project registry + filesystem scan.

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
    async def update(project_id, **kwargs) -> None  # fields from allowed set
    async def delete(project_id) -> None

    async def set_setting(project_id, key, value) -> None     # JSON-encode
    async def unset_setting(project_id, key) -> None
    async def get_setting(project_id, key)
    async def all_settings(project_id) -> dict

    @staticmethod
    def scan_projects_root(root: str) -> list[dict]   # [{path, name, suggested_slug, suggested_label, has_claude}]
    async def import_from_scan(items: list[dict], default_slug=None) -> list[Project]
```

**Idempotence of `import_from_scan`** (projects.py:156–189): skips items by `working_dir` or `slug` that are already registered. If the slug collides, appends a `-2`, `-3`, ... suffix.

`set_setting` always JSON-encodes (`json.dumps(value)`); `get_setting` decodes.

### `config_resolver.py` — `ConfigResolver`

Override-with-fallback: per-project value → global setting → default.

```python
class ConfigResolver:
    def __init__(self, projects: ProjectsService, global_settings: AppSettings)
    async def get(self, project: Project | None, key: str, default = SENTINEL)
    def invalidate_project(project_id: int) -> None
```

Per-request cache `_cache: dict[int, dict]` — for N requests of the same project there's a single SELECT (config_resolver.py:18).

`get_resolver(request)` factory in `main.py:69` — creates a fresh resolver per request so the cache doesn't accumulate between requests.

See [`features/settings.md`](features/settings.md).

## Processes

### `process_manager.py` — `ProcessManager`, `RunningSession`

Manages Claude CLI subprocesses. One instance per app (see main.py:41). Holds `running: dict[str, RunningSession]` with composite keys.

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
    key: str  # key in pm.running

    async def send_user_message(text) -> bool   # stream-json into stdin

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
- `"cmd:{slug}:{command_name}"` — slash-commands and raw (`start_command` / `start_raw_command`).

`_resolve_claude_path` (process_manager.py:31) uses `shutil.which` to pick `claude.cmd` on Windows instead of the bash-script `claude`.

`_parse_stream_json` (process_manager.py:398) parses Claude's stream-json into human-readable lines `[tool] Bash: ls -la`, `[done] status=ok cost=$0.34`, etc.

`_watchdog` (process_manager.py:544) is a **silence-watchdog**, not a lifetime watchdog: kills the process if `time.time() - last_stdout_at >= timeout_minutes*60`. If there's a pending question in `orchestrator_questions` (process_manager.py:575), resets the counter (a valid wait for user input).

`STDOUT_BUFFER_LIMIT = 16 MB` (process_manager.py:28) — bumped from the default 64KB so readline doesn't fail on huge assistant blocks.

On `LimitOverrunError` (process_manager.py:502) — drains the remaining chunk up to `\n`, logs warn, continues (no crash).

`KeepAwake.acquire()` is called on every spawn, `release()` on every cleanup (refcount).

`_cleanup` calls `db.reconcile_stale_sessions(active_pairs, learning_notes_dir, grace_minutes=2)` — not defined in the current db.py, exception is caught (process_manager.py:633).

### `keep_awake.py` — `KeepAwake`

Windows-only refcount guard. On non-Windows — no-op.

```python
class KeepAwake:
    def __init__()
    def acquire()    # refs++; if refs==1 → SetThreadExecutionState(ON)
    def release()    # refs--; if refs==0 → SetThreadExecutionState(OFF)
    @property
    def active() -> bool
```

Calls `kernel32.SetThreadExecutionState` with flags `ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED` (keep_awake.py:49). The display can still turn off normally.

History: added after the May 5 incident — the machine slept Modern Standby at 06:53, the cascade died at 07:03. See the comment in process_manager.py:96–98.

### `scheduler.py` — `build_scheduler`, `register_project_jobs`, `unregister_project_jobs`

Global + per-project APScheduler jobs.

```python
def build_scheduler(app_state) -> AsyncIOScheduler   # + reconcile + ai_usage_ingest
async def register_project_jobs(scheduler, app_state, project) -> None
async def unregister_project_jobs(scheduler, project) -> None

# List of per-project jobs:
_PER_PROJECT_JOBS = [
    ("nightly_learning", "cron_expression", "cron_enabled", "0 2 * * *", True, _nightly_learning),
    ("weekly_tech_debt_scan", ..., False, _weekly_tech_debt_scan),
    ("weekly_product_ideas_scan", ..., False, _weekly_product_ideas_scan),
    ("weekly_wiki_lint", ..., False, _weekly_wiki_lint),
]
```

Global jobs (scheduler.py:223–230):
- `reconcile_stale_sessions` — interval 5 min, via `_reconcile_job` collects active_pairs from `pm.list_running()` and delegates to `pm.reconcile_stale_sessions`.
- `ai_usage_ingest` — interval 5 min, calls `ai_usage_parser.ingest_ai_usage`.

`register_project_jobs` (scheduler.py:181) — for each `(kind, ...)` in `_PER_PROJECT_JOBS`:
1. resolver.get(`enabled_key`) → if false, `remove_job` (silently ignores error).
2. resolver.get(`cron_key`) → cron expression.
3. `scheduler.add_job(fn, CronTrigger.from_crontab(cron_expr), args=[app_state, project.id], id=f"{kind}_{slug}", replace_existing=True)`.

Hooks calling it:
- When projects are created in the setup wizard ([`setup.py:108`](../../dreaming/routes/setup.py)).
- On `POST /projects/{id}/toggle` ([`projects.py:32`](../../dreaming/routes/projects.py)).
- On `POST /projects/{id}/delete` ([`projects.py:43`](../../dreaming/routes/projects.py)).
- On `POST /projects/import` ([`projects.py:62`](../../dreaming/routes/projects.py)).

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
    async def has_running_run(project_id) -> str | None  # run_id or None
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

`has_running_run` is needed for the one-Roman-per-project lock. Use it before `create_run` if you want to enforce.

`append_artifact` catches the UNIQUE-constraint exception and returns `None` (orch_hub.py:227).

### `claude_session_tail.py` — `ClaudeSessionTail`, `tail_session_file`, helpers

Tail-watcher for `~/.claude/projects/<workdir>/<session>.jsonl`.

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

**Key functions**:

`encode_workdir` — encodes a path the way Claude CLI does: every non-alnum character becomes a `-`. On Windows `D:\Work\micode\rgs-frontend` → `D--Work-micode-rgs-frontend`.

`tail_session_file` — staged:
1. **Catchup**: reads the entire existing jsonl, runs through `_ingest_line`. Records `seen_uuids` to avoid duplicates.
2. **Live tail loop**: polls `path.stat()` every `poll_interval` (1s default), reads new bytes from offset, ingests. Detects rotation/truncation via inode change.
3. If `idle_finalize_after` is set — after `idle` seconds of silence, `update_node_status('completed')` and exit.

`_ingest_line` (claude_session_tail.py:276) parses a JSONL line:
- if `type` is not in `("assistant", "user")` — skip.
- if `uuid` is already in `seen` — skip.
- `_extract_text_from_message` (claude_session_tail.py:211) collects text from `text` / `tool_use` (via `_summarize_tool_use`) / `tool_result` blocks.
- `append_message(...)` + `append_event("message_added", ...)`.

### `subagent_watcher.py` — `SubagentWatcher`, `watch_subagents_for_run`, `_resolve_node_for_subagent`

Watcher for `subagents/agent-*.meta.json`.

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

Logic: one subagent_hash = one node. If a node with `external_id == agent_hash` already exists — reuse. Otherwise creates a worker node parented to parent_node_id.

`SubagentWatcher.start` (subagent_watcher.py:214) lazy-resolves the folder via `_resolve_folder` (subagent_watcher.py:189) — searches for `~/.claude/projects/**/<external_id>.jsonl` and takes `parent / <external_id> / subagents`.

Each new subagent file gets its own `tail_session_file` task with `idle_finalize_after=30.0` — finalised automatically after 30 seconds of silence.

### `subagent_backfill.py` — `backfill_run`

Offline reconstruction. Replays the run's JSONLs into orchestration tables.

```python
async def backfill_run(run_id, db, hub, claude_projects_dir=None) -> int
```

Used when the watcher was offline or the run predates Wave 3. Not idempotent at the DB level — calling again on an already-backfilled run produces duplicates (subagent_backfill.py:14–17).

### `harness_client.py` — `HarnessClient`, `HarnessClientCache`

HTTP/SSE adapter to the external harness API (if used instead of the local claude CLI). Permissive in parsing (supports run_id at `data.run_id`, `external_id`, `id`).

```python
class HarnessClient:
    def __init__(self, settings=None, **kwargs)
    @property
    def enabled(self) -> bool   # True if base_url is set
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

`stream_events` — SSE with NDJSON fallback. `_normalize_event` (harness_client.py:215) maps aliases (`spawn` → `node_created`, `chat` → `message_added`, etc.).

`HarnessClientCache.get_for_project` (harness_client.py:250) is lazy — resolves `harness_*` settings via `ConfigResolver.get(project, key)`. If `harness_base_url` is empty — returns None.

### `cascade_stage_detect.py` — `detect_stage`

Heuristic: by `agent_name + description` → stage_key.

```python
def detect_stage(agent_name: str, description: str = "") -> str | None
```

Returns one of `'contract' | 'design' | 'implementation' | 'review' | 'qa'` or None.

Rules in `_RULES` (cascade_stage_detect.py:17–57): rule order matters — first match wins.

### `tts_backfill.py` — `backfill_tts` (stub)

Wave 3.9 stub:

```python
async def backfill_tts(run_id, db, hub, claude_projects_dir=None) -> int   # always 0
```

Full implementation deferred.

## Pipeline parsers

All parsers are project-aware: the first argument is a path to the directory, not the global settings.

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

`_iter_td_paths` (tech_debt.py:73) tries `{td_dir}/items/TD-*.md` (ALC layout) and falls back to `{td_dir}/TD-*.md` or `{td_dir}/*.md` (flat micode layout).

`close_tech_debt_item` (tech_debt.py:191) — regex replaces `^status:.*$` with `status: closed`. If absent — appends to frontmatter.

### `product_ideas.py`

```python
@dataclass
class ProductIdeaItem: id, title, status, impact, effort, confidence, priority,
                       ..., jira_ticket, jira_epic, jira_task, value_hypothesis,
                       file_path

def list_product_ideas(ideas_dir) -> list[ProductIdeaItem]
def parse_product_ideas(ideas_dir)   # alias
def read_product_idea(file_path) -> tuple[dict, str]
def read_idea_slug(file_path) -> str   # from PI-NNN-<slug>.md
```

Mirrors `tech_debt.py`. Same fallback layout (`items/PI-*.md` → `PI-*.md` → `*.md`).

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

JSON parser. Reviewer = parent dir name or file stem (sidecar_findings.py:43).

### `wiki_data.py`

```python
@dataclass
class WikiStatus: wiki_dir, exists, domains_count, domains   # first 20 names

def get_wiki_status(wiki_dir) -> WikiStatus
```

Tries `{wiki_dir}/domains/*.md`, falls back to `{wiki_dir}/*.md`.

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

`progress_pct` = `done * 100 // total` where `done` — `- [x]` checkboxes, `todo` — `- [ ]` (plans.py:14, 56).

### `cascade_costs.py`

```python
@dataclass
class CascadeRunCost: run_id, project_id, goal, status, started_at, finished_at,
                       total_cost_usd, event_count

async def list_cascade_costs(db, project_id, limit=50) -> list[CascadeRunCost]
```

Sums `cost_usd` or `total_cost_usd` from each run's `orchestrator_events.payload_json`.

### `notes.py`

```python
class NoteEntry(NamedTuple): relative_path, full_path, size, mtime

def list_notes(notes_dir, max_items=200) -> list[NoteEntry]
def read_note(notes_dir, relative_path) -> str | None   # path-traversal-safe
```

`read_note` (notes.py:34) does `Path(notes_dir).resolve() / Path(relative_path).resolve()` and checks startswith — protection from `..`.

### `checklist.py`

```python
@dataclass
class ChecklistTopic: number, title, module, target_agents, question,
                       why_important, completed

def parse_checklist(agents_dir) -> tuple[str, list[ChecklistTopic]]   # (week_label, topics)
def parse_weekly_checklist(text: str) -> list[ChecklistTopic]
```

Parses `_weekly-learning-checklist.md`. Skip sections: "Приоритет недели" (Week priority), "Общие (любой агент)" (General (any agent)) (checklist.py:37–42).

### `agents.py`

```python
def list_agent_names(working_dir: str) -> list[str]
```

Scans `{working_dir}/.claude/agents/`. Supports single-file `.md` and a multi-file dir with `{name}.md` or `agent.md`.

### `jira.py`

```python
class JiraError(RuntimeError): ...

async def create_task(settings, *, summary, item_id, item_url, description="",
                      project_key_override=None, kind="идея") -> dict
```

POST to `{jira_url}/rest/api/3/issue`. Auth — `(jira_email, jira_api_token)`. ADF description with link back (jira.py:25–46).

`_extract_error` (jira.py:114) tries to extract a comprehensible message from the Jira error body.

## Cross-cutting

### `i18n.py` — `I18n`, `russian_plural`, `english_plural`

```python
class I18n:
    def __init__(self, base_dir: Path)   # reads messages_ru.json + messages_en.json
    def t(self, key: str, locale: str | None = None, **fmt) -> str
    def plural(self, key_base: str, n: int, locale: str | None = None) -> str

def russian_plural(n: int) -> str   # 'one' | 'few' | 'many' (CLDR)
def english_plural(n: int) -> str   # 'one' | 'other'
```

Fallback chain: `locale → 'ru' → key`. With `**fmt` — formats via `str.format`, catches `KeyError/IndexError`.

`russian_plural` (i18n.py:42–50) — CLDR rules: `mod10==1 && mod100!=11 → one`, `mod10 in (2,3,4) && mod100 not in (12,13,14) → few`, otherwise `many`.

See [`features/i18n.md`](features/i18n.md).

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
1. `build_cwd_to_project_id(db)` — map `_norm_for_match(working_dir) → project_id`.
2. `discover_jsonl_files(root)` — yield every JSONL, `is_subagent` = `parent.name == 'subagents'`.
3. Per file: `read_new_lines(path, stored_offset, st.st_size)` → list of complete lines + new_offset.
4. `parse_line` for each line. If `cwd` is not in the map → `events_skipped++`.
5. `_insert_events(db, project_id, rows)` batch INSERT OR IGNORE.
6. `_upsert_file` — saves new offset + counters.
7. Files that vanished from disk → `_mark_missing` (is_missing=1).

Returns `{files, events_inserted, events_skipped, errors, duration_ms}`.

### `ai_usage_stats.py` — aggregates

```python
async def project_summary(db, project_id) -> {project_id, last_7d, last_30d, by_model}
async def global_summary(db) -> {last_7d, last_30d, by_project, events_total}
```

Inside: `_totals` / `_by_model` / `_by_project` (private). All queries by `ts_date BETWEEN ? AND ?`.

### `starter_kit.py` — slash-command installer

Out-of-the-box bootstrap: `templates/starter-kit/` in the DC repo is mirrored
into `{working_dir}/.claude/` of the target project.

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

Implementation (`dreaming/services/starter_kit.py`):
- `TEMPLATE_DIR = <repo>/templates/starter-kit`.
- `_template_files()` recursively `rglob('*')` under `TEMPLATE_DIR`.
- `install()` walks each file, computes the rel-path, checks existence in
  the target, copies via `shutil.copy2`. Default behaviour is **skip if
  exists** — overwrite only with `force=True`.

Used by:
- Routes: `dreaming/routes/project_rotation.py` (POST
  `/p/{slug}/starter-kit/install`), the rotation page (status in context),
  `dreaming/routes/project_topics.py` (status for an inline button).
- CLI: `scripts/install_starter_kit.py`.

See [`user/features/out-of-the-box.md`](user/features/out-of-the-box.md#starter-kit).

### `autoconfig.py` — one-click per-project directories

Default paths for every `*_dir` setting plus directory creation plus override
persistence — all behind one button.

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
2. `projects_svc.set_setting(project.id, key, abs_path)` — JSON-encoded into
   `project_settings`.
3. Returns the absolute path (useful for logs).

Used by:
- Route: `dreaming/routes/project_settings.py` (POST
  `/p/{slug}/settings/autoconfig`).
- Per-page routes: each of the 8 dashboard routes (`project_tech_debt.py`,
  `project_ideas.py`, `project_wiki.py`, `project_evolutions.py`,
  `project_loops.py`, `project_plans.py`, `project_contracts.py`,
  `project_sidecar_findings.py`) imports `autoconfig` and passes
  `default_abs(project, key)` into the template as `autoconfig_default`.
- Jinja: `dreaming/templates/_autoconfig_banner.html` (macro
  `autoconfig_banner(project, key, default_path, what)`).

See [`user/features/out-of-the-box.md`](user/features/out-of-the-box.md#directory-autoconfig).

## Cross-references

- Which endpoints invoke which services — [`api.md`](api.md), [`routes.md`](routes.md).
- What's stored in the DB — [`schema.md`](schema.md).
- What's configured where — [`configuration.md`](configuration.md).
