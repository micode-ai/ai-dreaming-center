# Orchestration (Roman runs)

Roman — корневой Claude-агент с ролью `orchestrator`. Он принимает задачу (goal), декомпозирует её через `Task` tool в sub-агенты, и DC отслеживает всю активность через в БД через ClaudeSessionTail + SubagentWatcher.

## Содержание

- [Что такое run](#что-такое-run)
- [One-Roman-per-project lock](#one-roman-per-project-lock)
- [Старт run'а](#старт-runа)
- [Detail page (live polling)](#detail-page-live-polling)
- [ClaudeSessionTail mechanics](#claudesessiontail-mechanics)
- [SubagentWatcher mechanics](#subagentwatcher-mechanics)
- [Resume](#resume)
- [Backfill](#backfill)
- [API](#api)

## Что такое run

`orchestrator_runs` (см. [`schema.md`](../schema.md#orchestrator_runs)) — одна попытка достижения goal.

Lifecycle:

```
+--------+      +---------+      +----------+
| pending| -->  | running | -->  | completed|
+--------+      +---------+      +----------+
                     |                ^
                     v                |
                 +--------+      +--------+
                 | failed |      |cancelled|
                 +--------+      +--------+
```

В коде эти статусы пишутся в столбец `status`, [`orchestration_hub.create_run`](../../dreaming/services/orchestration_hub.py:26) ставит `'running'`.

Каждый run имеет:
- `id` — DC-internal UUID.
- `external_id` — Claude session UUID (равен basename'у `.jsonl` файла под `~/.claude/projects/<workdir>/`).
- `goal` — текстовая цель.
- `started_at`, `finished_at`.

При создании auto-вставляется root-нода ([`api.py:108`](../../dreaming/routes/api.py)):

```python
node_id = await hub.create_node(
    run_id, project.id, agent_name="roman", role="orchestrator",
    external_id=external_id,
)
```

## One-Roman-per-project lock

`OrchestrationHub.has_running_run(project_id)` ([`orchestration_hub.py:47`](../../dreaming/services/orchestration_hub.py)) возвращает `run_id` существующего running-run'а или None.

В JSON API endpoint'е `/api/orchestration/start`:
- Если `enforce_single=true` (default) — 409 с `{"detail": {"error": "...", "run_id": <existing>}}`.

В form-based endpoint'е `POST /p/{slug}/orchestration/start`:
- 303 редирект на `/p/{slug}/orchestration/{existing}` ([`project_orchestration.py:64`](../../dreaming/routes/project_orchestration.py)).

Это защита от случайного двойного клика «Start» в UI.

## Старт run'а

UI: на `/p/{slug}/orchestration` есть форма с одним полем `goal`. Жмёшь Start → POST `/p/{slug}/orchestration/start`.

Action в коде ([`project_orchestration.py:50`](../../dreaming/routes/project_orchestration.py)):

1. Проверка `goal.strip()` — иначе 400.
2. `has_running_run` → если есть, 303 на existing.
3. `claude_session_id = str(uuid.uuid4())` — будем использовать как `--session-id` для claude И как `external_id` для run'а.
4. `hub.create_run(project_id, goal, external_id=claude_session_id)`.
5. `hub.create_node(run, agent_name="roman", role="orchestrator", external_id=claude_session_id)`.
6. `hub.append_event("run_started", {project_slug, goal})`.
7. `pm.start_command(project, command_name=f"roman-{run_id[:8]}", prompt=goal, session_id=claude_session_id, ...)` — спавнит claude.
8. Если spawn упал — `finish_run(run_id, status='failed')` + 303 на detail (с error_message в БД).
9. Иначе:
   - Через 1-2 секунды claude создаст jsonl-файл. Делаем `find_session_file_by_id(claude_session_id)`.
   - Если jsonl уже есть — стартуем `ClaudeSessionTail(run_id, jsonl_path, hub, db)` через `asyncio.create_task`. Сохраняем в `app.state.orchestration_tails[run_id]`.
   - Стартуем `SubagentWatcher(run_id, root_node_id, hub, db, claude_projects_dir=...)`. Сохраняем в `app.state.orchestration_watchers[run_id]`.

Если jsonl ещё не появился — лог `INFO orchestration_start_form: jsonl not yet visible for session ...; backfill will recover` ([`project_orchestration.py:124`](../../dreaming/routes/project_orchestration.py)) — позже backfill догонит, либо при перезапуске.

## Detail page (live polling)

`GET /p/{slug}/orchestration/{run_id}` ([`project_orchestration.py:30`](../../dreaming/routes/project_orchestration.py)) рендерит `project_orchestration_detail.html` с:
- run record (goal, status, started_at, finished_at).
- nodes (с agent_name, role, status, started_at).
- messages (все сообщения всего run'а в chronological order).

Клиентский JS (внутри template) делает `setInterval` polling `GET /p/{slug}/orchestration/{run_id}/refresh` каждые ~2 секунды:

```json
{
  "status": "running",
  "finished_at": null,
  "node_count": 3,
  "message_count": 47,
  "nodes": [{"id":"...","agent_name":"alisa-frontend","status":"running","role":"worker"}],
  "messages": [{"id":"...","ts":"...","author":"agent","kind":"text","text":"..."}]
}
```

Возвращает только последние 100 messages (срез `[-100:]`, [`project_orchestration.py:182`](../../dreaming/routes/project_orchestration.py)).

POST на `/p/{slug}/orchestration/{run_id}/finish` — финиш run'а кнопкой (`status=completed`).

## ClaudeSessionTail mechanics

[`dreaming/services/claude_session_tail.py`](../../dreaming/services/claude_session_tail.py).

Объект-обёртка:

```python
tail = ClaudeSessionTail(run_id, jsonl_path, hub, db)
await tail.start()    # idempotent
# ... время идёт ...
await tail.stop()
```

`start()`:
1. `_ensure_node()` — ищет existing orchestrator-node в run'е, либо создаёт новую.
2. Запускает `asyncio.create_task(tail_session_file(...))`.

`tail_session_file` (claude_session_tail.py:338):

**Catchup pass**: открывает jsonl, читает все строки, для каждой делает `_ingest_line(...)`. Запоминает `seen_uuids` чтобы при live tail не дублировать.

**Live tail loop**:
- `path.stat()` каждые `poll_interval` (1s).
- Если `cur_inode != last_inode` — файл ротейтнулся. `last_size = 0` (читаем с начала).
- Если `cur_size < last_size` — truncation. `last_size = 0`.
- Если `cur_size > last_size` — открываем, seek(last_size), читаем новые строки, ingest'им.
- Если `idle_finalize_after` задан и `idle >= idle_finalize_after` — `update_node_status(node_id, 'completed')` и выходим.

`_ingest_line` (claude_session_tail.py:276):

```python
obj = json.loads(line)
if obj["type"] not in ("assistant", "user"): return 0
if obj["uuid"] in seen: return 0
text = _extract_text_from_message(obj["message"])
if not text: return 0
author = "assistant" if obj["type"] == "assistant" else "user"
kind = "chat" if obj["type"] == "user" else "reasoning"
msg_id = await hub.append_message(run_id, node_id, project_id, author, kind, text)
seen.add(obj["uuid"])
await hub.append_event(run_id, "message_added", payload)
```

Поддерживаемые блоки в `_extract_text_from_message`:
- `text` — добавляется напрямую.
- `tool_use` — `_summarize_tool_use(name, input)` → один-line: `[Bash] desc — \`cmd\``, `[Read] path`, `[Task → frontend] desc` и т.д.
- `tool_result` — первые 400 символов как `[tool_result] ...`.

## SubagentWatcher mechanics

[`dreaming/services/subagent_watcher.py`](../../dreaming/services/subagent_watcher.py).

Когда Roman делегирует задачу через `Task` tool, Claude CLI спавнит дочерний процесс, и его jsonl лежит под:

```
~/.claude/projects/<workdir-encoded>/<roman_session>/subagents/agent-<hash>.jsonl
~/.claude/projects/<workdir-encoded>/<roman_session>/subagents/agent-<hash>.meta.json
```

`meta.json` содержит:
```json
{"agentType": "alisa-frontend", "description": "Implement login UI"}
```

`SubagentWatcher.start`:
1. `_resolve_folder()` — ищет `<roman_session>.jsonl` под `~/.claude/projects/`, берёт `parent / <session> / subagents`.
2. Если не найден — `idle, watcher остаётся idle` (subagent_watcher.py:218).
3. Иначе запускает `watch_subagents_for_run(folder=...)`.

`watch_subagents_for_run` (subagent_watcher.py:78):
- Каждые `poll_interval` (1s):
  - `folder.glob("agent-*.meta.json")`.
  - Для каждого нового `agent_hash`:
    - Читает `meta.json` → `agent_type`, `description`.
    - `_resolve_node_for_subagent` — ищет node с `external_id == agent_hash`, либо создаёт worker-ноду parent'ом на root.
    - Запускает `tail_session_file(...)` task с `idle_finalize_after=30.0`.
    - Складывает task в `tails[agent_hash]`.

После 30s тишины subagent finalize'ится автоматически через `idle_finalize_after`. Главный run при этом продолжает идти.

`stop_subagent_tails(tails)` — cancel all tail tasks.

## Resume

`POST /p/{slug}/orchestration/{run_id}/resume` form `prompt=` ([`project_orchestration.py:187`](../../dreaming/routes/project_orchestration.py)):

1. Run должен иметь `external_id` (Claude session UUID). Иначе 400.
2. Reactivate run: `UPDATE orchestrator_runs SET status='running', finished_at=NULL, error_message=NULL WHERE id=?`.
3. `append_event("run_resumed", {prompt})`.
4. `pm.start_command(...)`:
   - `command_name = f"resume-{run_id[:8]}"`.
   - `resume_session_id = run.external_id` — это станет `claude --resume <id>`.
   - `interactive_stdin = True` — claude ждёт stdin, мы шлём prompt через stream-json user-message.
5. На RuntimeError — `finish_run(failed)`, 409.

`pm.start_command(interactive_stdin=True)` нюанс ([`process_manager.py:260`](../../dreaming/services/process_manager.py)): нельзя одновременно передавать `-p <prompt>` и `--input-format stream-json` — claude зависнет. Поэтому при `interactive_stdin=True` мы передаём только `--print` (без позиционного prompt'а), запускаем процесс, и потом `await session.send_user_message(prompt)` через stdin.

## Backfill

[`dreaming/services/subagent_backfill.py`](../../dreaming/services/subagent_backfill.py) — `backfill_run(run_id, db, hub, claude_projects_dir=None) -> int`.

Используется когда:
- Run был создан, но watcher offline'ился — orchestration tables пустые.
- Run предшествует Wave 3 (был импортирован старый external_id).

Алгоритм:
1. `find_session_file_by_id(external_id)` — ищем jsonl под `~/.claude/projects/`.
2. `_ensure_main_node` — создаём orchestrator-ноду если нет.
3. `_replay_jsonl` — построчно `_ingest_line`.
4. `subagents/agent-*.meta.json` — для каждого:
   - `_resolve_node_for_subagent` (worker-нода parent'ом на main).
   - `_replay_jsonl` для subagent jsonl.

**Не идемпотентен** — повторный run на already-backfilled даст дубликаты (subagent_backfill.py:14–17). На production либо пересобирай DB, либо проверяй наличие messages до запуска.

## API

См. [`api.md`](../api.md#orchestration-api) — все 4 endpoint'а:
- `POST /api/orchestration/start`.
- `GET /api/orchestration/{run_id}`.
- `POST /api/orchestration/{run_id}/nodes/{node_id}/message`.
- `POST /api/orchestration/{run_id}/finish`.

External harness может стартовать orchestration через harness API через `HarnessClient.start_orchestration(goal)` — но в текущем DC это не подключено к UI form'е (используется local claude). См. [`waves.md`](../waves.md#не-реализованные-пока).

## Cross-references

- Cascade pipelines: [`features/cascade.md`](cascade.md).
- Schema runs/nodes/messages/events: [`schema.md`](../schema.md).
- Service внутренности: [`services.md`](../services.md#orchestration).
