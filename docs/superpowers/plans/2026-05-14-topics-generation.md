# Topics Generation & Injection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-generate `custom_topics` rows from project context (manual button + weekly cron) and actually inject those topics into the `/self-study` agent prompt. Both halves are needed: generation without injection produces dead data; injection without generation requires manual entry only.

**Architecture:** A new slash-command `/topics-scan` runs inside the project's Claude CLI (same pattern as `/tech-debt-scan`). It curls topic payloads back to a new DC endpoint `POST /api/p/{slug}/topics/ingest`, which inserts into the existing `custom_topics` table. A new UI button on `/p/{slug}/kanban` and a new entry in `scheduler._PER_PROJECT_JOBS` are the two triggers. Separately, both `scheduler._nightly_learning` and `routes/project_rotation.rotation_start` now build an `extra_prompt` block from `db.list_custom_topics_for_agent` and pass it through the existing-but-unused `extra_prompt` parameter of `process_manager.start_session`.

**Tech Stack:** Python 3.x, FastAPI, APScheduler, SQLite (aiosqlite), Jinja2, Claude CLI via `process_manager.start_command` / `start_session`.

**Spec reference:** `docs/superpowers/specs/2026-05-14-topics-generation-design.md`

**Project note — TDD adaptation:** This project has no test suite by design (see `CLAUDE.md`). Each task's verification step is a **manual smoke check** (curl + DB query, or browser interaction). The final task adds an end-to-end smoke script. Browser steps assume `python -m uvicorn dreaming.main:app --port 8086 --reload` is running.

---

## File Structure

| Path | Action | Responsibility |
|------|--------|----------------|
| `dreaming/services/topics_prompt.py` | create | `build_topics_extra_prompt(db, project_id, agent_name) -> str` — formats `custom_topics` rows as a markdown block prepended to `/self-study` prompts |
| `dreaming/routes/api.py` | modify | Add `POST /api/p/{slug}/topics/ingest`, `GET /api/p/{slug}/topics/list` for slash-command callbacks |
| `dreaming/routes/project_kanban.py` | modify | Add `POST /p/{slug}/topics/generate` that spawns the slash-command; pass `running` state to template |
| `dreaming/services/scheduler.py` | modify | Add `_weekly_topics_scan` job + register it in `_PER_PROJECT_JOBS`; inject `extra_prompt` in `_nightly_learning` |
| `dreaming/routes/project_rotation.py` | modify | Inject `extra_prompt` in `rotation_start` |
| `dreaming/templates/project_kanban.html` | modify | Add «Сгенерировать темы» button next to «Добавить»; respect running-state lock |
| `dreaming/templates/project_topics.html` | modify | Add one-line hint that the editor and generator live on the Kanban page |
| `dreaming/i18n/messages_ru.json` | modify | Add 3 strings under `topics.*` |
| `dreaming/i18n/messages_en.json` | modify | Mirror the 3 strings |
| `templates/starter-kit/commands/topics-scan.md` | create | Slash-command spec: scans project context, POSTs topics to DC |
| `scripts/smoke_topics_generation.py` | create | End-to-end smoke test using a stub `claude` binary |

**Build order:** bottom-up — DB-side helper and API endpoints first (independently testable with `curl`), then the trigger wiring, then the slash-command, then injection into agent runs, then the UI and i18n, then docs/smoke.

---

## Task 1: Shared topics-prompt builder

**Files:**
- Create: `dreaming/services/topics_prompt.py`

- [ ] **Step 1.1: Write the helper**

Create the file with this content (uses only existing `db.list_custom_topics_for_agent` from `dreaming/services/db.py:797-805`):

```python
"""Build the `extra_prompt` block fed into /self-study from custom_topics."""
from __future__ import annotations


async def build_topics_extra_prompt(db, project_id: int, agent_name: str) -> str:
    """Returns a markdown block listing active custom_topics targeted at this
    agent, or "" if none. The empty case is important: callers prepend the
    string unconditionally, so "" must mean "no change to current behavior".
    """
    rows = await db.list_custom_topics_for_agent(project_id, agent_name)
    if not rows:
        return ""
    blocks = ["## Темы на сегодня (из DC)"]
    for r in rows:
        blocks.append(f"### {r['title']}")
        if r["module"]:
            blocks.append(f"Модуль: {r['module']}")
        if r["question"]:
            blocks.append(f"Что изучить: {r['question']}")
        if r["why_important"]:
            blocks.append(f"Почему важно: {r['why_important']}")
        blocks.append("")
    return "\n".join(blocks).rstrip()
```

- [ ] **Step 1.2: Manual smoke**

Start a Python REPL in the repo root, build an in-memory DB the same way the app does, insert one row, and assert non-empty:

```bash
python -c "
import asyncio
from dreaming.services.db import SqliteDB
from dreaming.services.topics_prompt import build_topics_extra_prompt

async def main():
    db = SqliteDB(':memory:'); await db.connect()
    # Need a project row first because of FK
    await db.execute(
        'INSERT INTO projects (id, slug, name, working_dir, enabled, created_at) '
        'VALUES (1, \"x\", \"X\", \".\", 1, \"2026-05-14\")', ())
    await db.add_custom_topic(1, 'Refactor auth', module='auth',
        target_agents='vera', question='3 pain points?', why_important='migration soon')
    print(repr(await build_topics_extra_prompt(db, 1, 'vera')))
    print(repr(await build_topics_extra_prompt(db, 1, 'svetlana')))

asyncio.run(main())
"
```

Expected: first line is a non-empty string containing `Refactor auth` and `Модуль: auth`. Second line is `''` (svetlana isn't targeted, and `target_agents='vera'` doesn't match the `OR target_agents=''` clause).

If the `projects` INSERT fails because of a different schema (extra NOT NULL columns), adjust the columns — the goal is just to seed the FK.

- [ ] **Step 1.3: Commit**

```powershell
git add dreaming/services/topics_prompt.py
git commit -m "feat(topics): add build_topics_extra_prompt helper"
```

---

## Task 2: DC ingest endpoints

**Files:**
- Modify: `dreaming/routes/api.py`

- [ ] **Step 2.1: Add the payload model + endpoints**

Append at the end of `dreaming/routes/api.py` (after the orchestration block, but inside the same `router`):

```python
# -- Topics ingest (slash-command callback) ----------------------

class TopicIngestIn(BaseModel):
    title: str
    module: str = ""
    target_agents: str = ""
    question: str = ""
    why_important: str = ""


@router.post("/p/{slug}/topics/ingest")
async def topics_ingest(request: Request, slug: str, payload: TopicIngestIn):
    """Called by /topics-scan slash-command running inside the project. One POST
    per topic. We don't dedupe at this layer — the slash-command is responsible
    for not proposing duplicates (it can GET /topics/list first)."""
    project = await _resolve_project(request, slug)
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="title required")
    tid = await request.app.state.db.add_custom_topic(
        project.id, title, payload.module.strip(),
        payload.target_agents.strip(), payload.question.strip(),
        payload.why_important.strip(),
    )
    return JSONResponse({"id": tid}, status_code=201)


@router.get("/p/{slug}/topics/list")
async def topics_list(request: Request, slug: str):
    """Called by /topics-scan to see what already exists so it can skip
    duplicates. Returns active topics only."""
    project = await _resolve_project(request, slug)
    rows = await request.app.state.db.list_custom_topics(project.id, active_only=True)
    return JSONResponse([
        {"id": r["id"], "title": r["title"], "module": r["module"],
         "target_agents": r["target_agents"]}
        for r in rows
    ])
```

`_resolve_project` already exists in this file (line 30) and raises 404 on unknown slug — no need to duplicate.

- [ ] **Step 2.2: Verify via curl**

With the dev server running, create or pick an enabled project (the rest of the plan uses `ai-budget-assistant`; substitute your slug):

```powershell
$body = '{"title":"Smoke test topic","module":"auth","target_agents":"vera"}'
curl.exe -X POST "http://localhost:8086/api/p/ai-budget-assistant/topics/ingest" `
  -H "Content-Type: application/json" -d $body
```

Expected: HTTP 201, JSON `{"id":"<uuid>"}`. Then:

```powershell
curl.exe "http://localhost:8086/api/p/ai-budget-assistant/topics/list"
```

Expected: JSON array containing the row just inserted.

Open `/p/ai-budget-assistant/kanban` in the browser — the topic appears in the Custom topics table.

- [ ] **Step 2.3: Verify the 422 path**

```powershell
curl.exe -X POST "http://localhost:8086/api/p/ai-budget-assistant/topics/ingest" `
  -H "Content-Type: application/json" -d '{"title":"   "}'
```

Expected: HTTP 422, body mentions `title required`.

- [ ] **Step 2.4: Verify the 404 path**

```powershell
curl.exe -X POST "http://localhost:8086/api/p/nonexistent-slug/topics/ingest" `
  -H "Content-Type: application/json" -d '{"title":"x"}'
```

Expected: HTTP 404, body contains `project 'nonexistent-slug' not found`.

- [ ] **Step 2.5: Clean up the smoke row**

Delete the smoke row via the Kanban UI (red `delete` link) so the table is clean for later tasks.

- [ ] **Step 2.6: Commit**

```powershell
git add dreaming/routes/api.py
git commit -m "feat(topics): add /api/p/{slug}/topics ingest+list endpoints"
```

---

## Task 3: Inject topics into nightly_learning

**Files:**
- Modify: `dreaming/services/scheduler.py` — function `_nightly_learning` (lines 76-108)

- [ ] **Step 3.1: Import the helper**

Near the top of `dreaming/services/scheduler.py`, after the existing `from dreaming.services.config_resolver import ConfigResolver` line, add:

```python
from dreaming.services.topics_prompt import build_topics_extra_prompt
```

- [ ] **Step 3.2: Pass `extra_prompt` per agent**

In `_nightly_learning`, inside the `for row in candidates:` loop (currently line 90), before the `await pm.start_session(...)` call, fetch the per-agent topic block and pass it through. Replace the current call (lines 91-107) with:

```python
        try:
            extra_prompt = await build_topics_extra_prompt(
                db, proj.id, row["agent_name"],
            )
            await pm.start_session(
                proj,
                agent_name=row["agent_name"],
                claude_path=await resolver.get(proj, "claude_path", "claude"),
                working_dir=proj.working_dir,
                model=await resolver.get(proj, "model", "sonnet"),
                max_turns=int(await resolver.get(proj, "max_turns", 25)),
                timeout_minutes=int(await resolver.get(proj, "timeout_minutes", 20)),
                self_study_command=await resolver.get(proj, "self_study_command", "/self-study"),
                extra_prompt=extra_prompt,
                env_overrides={
                    "DREAMING_PROJECT_SLUG": proj.slug,
                    "DREAMING_API_URL": f"http://localhost:{settings.port}",
                },
            )
        except RuntimeError as e:
            log.warning("nightly_learning [%s] %s: %s", proj.slug, row["agent_name"], e)
        await asyncio.sleep(pause)
```

Only one logical change: insert the `extra_prompt = ...` lookup and pass it as a kwarg. The rest of the loop body is unchanged.

- [ ] **Step 3.3: Smoke (no-op path)**

With `custom_topics` empty for `ai-budget-assistant`, trigger one nightly run manually. The easiest way: hit the rotation Start button (Task 4 wires the same helper into that path, so it also works once Task 4 lands; for now use the existing button). Verify the `/self-study <agent>` prompt in the live log is **unchanged** from before — empty `extra_prompt` produces no output difference.

Actually, since Task 4 wires the same helper into the rotation Start path, we can't fully test Task 3 in isolation without waiting for nightly cron. Substitute test: run the Task 1 smoke script from the REPL to confirm the helper returns `""` for empty input, and visually inspect that the diff in `scheduler.py` only adds `extra_prompt=...` without touching anything else.

- [ ] **Step 3.4: Commit**

```powershell
git add dreaming/services/scheduler.py
git commit -m "feat(topics): inject custom_topics into nightly_learning extra_prompt"
```

---

## Task 4: Inject topics into rotation Start button

**Files:**
- Modify: `dreaming/routes/project_rotation.py` — function `rotation_start` (lines 81-103)

- [ ] **Step 4.1: Import the helper**

Add to the existing imports at the top of `dreaming/routes/project_rotation.py`:

```python
from dreaming.services.topics_prompt import build_topics_extra_prompt
```

- [ ] **Step 4.2: Pass `extra_prompt`**

Inside `rotation_start`, before `await pm.start_session(...)`, fetch the block and pass it. The whole try/except becomes:

```python
    try:
        extra_prompt = await build_topics_extra_prompt(
            request.app.state.db, project.id, agent,
        )
        await pm.start_session(
            project,
            agent_name=agent,
            claude_path=getattr(settings, "claude_path", "claude"),
            working_dir=project.working_dir,
            model=getattr(settings, "model", "sonnet"),
            max_turns=getattr(settings, "max_turns", 25),
            timeout_minutes=getattr(settings, "timeout_minutes", 20),
            self_study_command=getattr(settings, "self_study_command", "/self-study"),
            extra_prompt=extra_prompt,
            env_overrides={
                "DREAMING_PROJECT_SLUG": project.slug,
                "DREAMING_API_URL": f"http://localhost:{settings.port}",
            },
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
```

- [ ] **Step 4.3: End-to-end smoke (with topic)**

1. On `/p/ai-budget-assistant/kanban` add a topic via the form: title `Smoke E2E`, target_agents `aba-architect`.
2. On `/p/ai-budget-assistant/rotation`, click Start next to `aba-architect`.
3. On `/p/ai-budget-assistant/live`, watch the new session's stdout for the literal string `Темы на сегодня (из DC)` followed by `### Smoke E2E`.

If the string appears: injection works. Stop the session (or let it finish), then delete the smoke topic.

- [ ] **Step 4.4: Smoke (empty path — no regression)**

With `custom_topics` empty, click Start on a different agent. Verify the live-log shows the bare `/self-study <agent>` prompt without any prepended block — same behavior as before this plan.

- [ ] **Step 4.5: Commit**

```powershell
git add dreaming/routes/project_rotation.py
git commit -m "feat(topics): inject custom_topics into rotation Start extra_prompt"
```

---

## Task 5: Generate-topics route + Kanban button

**Files:**
- Modify: `dreaming/routes/project_kanban.py`
- Modify: `dreaming/templates/project_kanban.html`

- [ ] **Step 5.1: Add the route handler**

Append to `dreaming/routes/project_kanban.py` (after `kanban_delete`):

```python
@router.post("/p/{slug}/topics/generate")
async def topics_generate(request: Request, slug: str):
    project = request.state.project
    pm = request.app.state.process_manager
    settings = request.app.state.settings
    resolver = request.app.state.resolver_factory(request)
    try:
        await pm.start_command(
            project,
            command_name="topics-scan",
            prompt="/topics-scan",
            claude_path=await resolver.get(project, "claude_path", "claude"),
            working_dir=project.working_dir,
            model=await resolver.get(project, "model", "sonnet"),
            max_turns=int(await resolver.get(project, "max_turns", 50)),
            timeout_minutes=int(await resolver.get(project, "timeout_minutes", 30)),
            env_overrides={
                "DREAMING_PROJECT_SLUG": project.slug,
                "DREAMING_API_URL": f"http://localhost:{settings.port}",
            },
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return RedirectResponse(f"/p/{project.slug}/live", status_code=303)
```

- [ ] **Step 5.2: Expose running-state to the template**

In `kanban_page` (currently lines 25-89), just before the `return` (after the `topics = await db.list_custom_topics(...)` line, ~line 74), add:

```python
    pm = request.app.state.process_manager
    topics_running = f"cmd:{project.slug}:topics-scan" in pm.list_running()
```

And add `"topics_running": topics_running,` to the context dict passed into the TemplateResponse.

- [ ] **Step 5.3: Add the button in the template**

In `dreaming/templates/project_kanban.html`, find the line `<h2 class="text-sm font-semibold mb-3" style="color: var(--text-strong);">Custom topics</h2>` (currently line 68). Replace it with a flex row containing the heading plus a Generate form to the right:

```html
<div class="flex items-center justify-between mb-3 gap-3">
  <h2 class="text-sm font-semibold" style="color: var(--text-strong);">Custom topics</h2>
  <form method="post" action="/p/{{ project.slug }}/topics/generate">
    <button type="submit"
            class="text-xs rounded px-3 py-1.5 disabled:opacity-50"
            style="background: var(--brand); color: white; border:1px solid var(--brand-hover);"
            {% if topics_running %}disabled title="Уже выполняется"{% endif %}>
      {% if topics_running %}Генерируется…{% else %}Сгенерировать темы{% endif %}
    </button>
  </form>
</div>
```

Leave the rest of the Custom Topics section untouched.

- [ ] **Step 5.4: Smoke — 409 path (collision lock)**

The button shouldn't fire the command twice. To verify the lock without a real slash-command (since starter-kit task hasn't landed yet, the `claude` CLI will fail to find `/topics-scan` but `start_command` still registers the running key briefly), call the endpoint twice in quick succession:

```powershell
curl.exe -X POST "http://localhost:8086/p/ai-budget-assistant/topics/generate" `
  -i -L --max-redirs 0
curl.exe -X POST "http://localhost:8086/p/ai-budget-assistant/topics/generate" `
  -i -L --max-redirs 0
```

Expected: first call returns 303 redirect to `/p/.../live`. Second call (before the first one finishes) returns 409 with body mentioning `topics-scan` already running. (If the first call finished too fast to observe collision, run them in parallel or wait for Task 6 when the command actually exists.)

- [ ] **Step 5.5: Smoke — UI button**

Reload `/p/ai-budget-assistant/kanban`. The button «Сгенерировать темы» appears to the right of «Custom topics» heading. Click it once: browser navigates to `/p/ai-budget-assistant/live`, and a new session row appears (likely failing because the slash-command isn't installed yet — that's fine, Task 6 fixes it).

- [ ] **Step 5.6: Commit**

```powershell
git add dreaming/routes/project_kanban.py dreaming/templates/project_kanban.html
git commit -m "feat(topics): add /topics/generate route + Kanban button"
```

---

## Task 6: Starter-kit slash-command

**Files:**
- Create: `templates/starter-kit/agents/commands/topics-scan.md` — wait, check the existing layout first

The existing scanner commands live in `templates/starter-kit/commands/` (verified — `tech-debt-scan.md` is at `templates/starter-kit/commands/tech-debt-scan.md`). Use the same path.

- Create: `templates/starter-kit/commands/topics-scan.md`

- [ ] **Step 6.1: Write the slash-command spec**

Create the file with the following content. Pattern follows `tech-debt-scan.md` exactly so an engineer copy-pasting from there will get something that works.

````markdown
---
description: Propose 5–10 learning topics for project agents and post them to the AI Dreaming Center.
---

You are running inside Claude Code, spawned by the AI Dreaming Center
(weekly scanner or on-demand) to propose 5–10 learning topics that the
project's agents should study during nightly `/self-study` runs.

## What you have

- `cwd` is the project repository root.
- Env vars: `LEARNING_SESSION_ID`, `DREAMING_API_URL`, `DREAMING_PROJECT_SLUG`.
- Agent roster: every `.md` file in `.claude/agents/` is an agent name. Use the **filename without `.md`** when filling `target_agents`.
- Recent activity signals (cheap to read):
  - `git log --oneline -50` — what's been changing.
  - `.claude/agents/learning-notes/` (if present) — what's been studied recently; avoid duplicating.
  - `.claude/agents/sidecar-findings/` (if present) — open questions agents have flagged.
  - `CLAUDE.md`, `README.md` — current focus areas.

## What to do

1. **Read what's already proposed.** Skip duplicates by title:

   ```bash
   curl -s "$DREAMING_API_URL/api/p/$DREAMING_PROJECT_SLUG/topics/list"
   ```

   This returns a JSON array of active topics. Treat case-insensitive
   exact-title matches as duplicates. Near-duplicates are fine — humans
   prune them later.

2. **Propose 5–10 new topics.** Each topic should be:
   - **Actionable** — a real thing an agent can study in one session.
   - **Targeted** — name 1-3 agents whose role fits. `target_agents` is a
     comma-separated list of agent filenames (no `.md`). Empty string = all.
   - **Grounded** — refer to specific files / modules / commits when possible.

3. **POST each topic** to the ingest endpoint:

   ```bash
   curl -s -X POST "$DREAMING_API_URL/api/p/$DREAMING_PROJECT_SLUG/topics/ingest" \
     -H "Content-Type: application/json" \
     -d '{
       "title": "Refactor session management — переход на FastAPI DI",
       "module": "auth",
       "target_agents": "vera,svetlana",
       "question": "Какие 3 main pain-points у текущей auth.login()?",
       "why_important": "Через 2 недели начинается переписывание; до этого нужна inventory pain-points."
     }'
   ```

   Expected: HTTP 201 with `{"id":"<uuid>"}`. Log and continue on any
   non-2xx response — partial ingestion is acceptable.

   **JSON escaping (critical):** wrap the body in single quotes for the
   shell, and double-quote string values inside JSON. If a value contains
   a literal double quote, use `\"`. Don't mix quote styles.

4. **Report back** when done (success or fail):

   ```bash
   curl -s -X POST "$DREAMING_API_URL/api/session/finish" \
     -H "Content-Type: application/json" \
     -d "{\"session_id\":\"$LEARNING_SESSION_ID\",\"status\":\"success\"}"
   ```

   On failure, send `"status":"failed"` with `"error_message"`.

## Rules

- Do **not** edit any project files. This command is read-only on disk;
  all output goes via the ingest endpoint.
- Do **not** invent topics where none exist — if you can't find 5 real
  things to learn, post fewer.
- Use agent filenames (without `.md`) verbatim in `target_agents`. If
  unsure, leave empty (= all agents).
````

- [ ] **Step 6.2: Install starter-kit into a test project**

Open `/p/ai-budget-assistant/kanban`. If the starter-kit panel shows a "missing files" install button, click it. Otherwise force-reinstall via:

```powershell
curl.exe -X POST "http://localhost:8086/p/ai-budget-assistant/starter-kit/install" `
  -i -L --max-redirs 0 -F "force=1"
```

Verify the file landed:

```powershell
Test-Path "D:\Work\micode\ai-budget-assistant\.claude\commands\topics-scan.md"
```

Note: starter-kit's `commands/` may install to `.claude/commands/` not `.claude/agents/commands/` — verify by reading `dreaming/services/starter_kit.py` to confirm the mirror layout. (Same uncertainty exists for `tech-debt-scan.md`; pattern-match where it actually ended up.)

- [ ] **Step 6.3: End-to-end smoke**

1. With the file installed, click «Сгенерировать темы» on `/p/ai-budget-assistant/kanban`.
2. Watch `/p/ai-budget-assistant/live` for the `topics-scan` session.
3. When it finishes (success status), reload `/p/ai-budget-assistant/kanban`. Expected: 5–10 new rows in the Custom topics table.

If Claude doesn't post any topics (e.g., session ends with `success` but zero rows): inspect the live-log stdout for HTTP errors from the curl calls, fix the slash-command spec, reinstall, retry.

- [ ] **Step 6.4: Commit**

```powershell
git add templates/starter-kit/commands/topics-scan.md
git commit -m "feat(topics): add /topics-scan slash-command to starter-kit"
```

---

## Task 7: Weekly cron job

**Files:**
- Modify: `dreaming/services/scheduler.py` — add `_weekly_topics_scan` and a `_PER_PROJECT_JOBS` entry

- [ ] **Step 7.1: Add the cron function**

In `dreaming/services/scheduler.py`, after the existing `_weekly_wiki_lint` function (around line 189), add a near-clone:

```python
async def _weekly_topics_scan(app_state, project_id: int):
    """Run /topics-scan via Claude CLI to generate fresh learning topics."""
    proj = await app_state.projects.get_by_id(project_id)
    if proj is None or not proj.enabled:
        return
    pm = app_state.process_manager
    settings = app_state.settings
    resolver = ConfigResolver(app_state.projects, settings)
    try:
        await pm.start_command(
            proj,
            command_name="weekly-topics-scan",
            prompt="/topics-scan",
            claude_path=await resolver.get(proj, "claude_path", "claude"),
            working_dir=proj.working_dir,
            model=await resolver.get(proj, "model", "sonnet"),
            max_turns=int(await resolver.get(proj, "max_turns", 50)),
            timeout_minutes=int(await resolver.get(proj, "timeout_minutes", 30)),
            env_overrides={
                "DREAMING_PROJECT_SLUG": proj.slug,
                "DREAMING_API_URL": f"http://localhost:{settings.port}",
            },
        )
    except RuntimeError as e:
        log.warning("weekly_topics_scan [%s]: %s", proj.slug, e)
```

Note the `command_name` is `"weekly-topics-scan"` (vs the on-demand button's `"topics-scan"`) so the two triggers don't collide on the `cmd:{slug}:{name}` key in `process_manager`.

- [ ] **Step 7.2: Register the job**

In the same file, find `_PER_PROJECT_JOBS` (around line 193) and add a new entry as the final element:

```python
    ("weekly_topics_scan", "weekly_topics_scan_cron", "weekly_topics_scan_enabled",
     "0 3 * * 1", False, _weekly_topics_scan),
```

Default cron `0 3 * * 1` = Monday 03:00 local. Default `False` = opt-in per project (same pattern as the other weekly scanners).

- [ ] **Step 7.3: Smoke — registration**

Restart the dev server (Ctrl+C, `python -m uvicorn dreaming.main:app --port 8086 --reload`). On startup, the per-project job loop runs. Look in the server log for the line registering `weekly_topics_scan_ai-budget-assistant`. Because `weekly_topics_scan_enabled` defaults to `False`, the entry should be **skipped** (removed if previously registered) on first startup — no errors.

Then enable it for one project. Either via the per-project settings UI (`/p/ai-budget-assistant/settings`), or directly:

```powershell
sqlite3 dc.db "INSERT OR REPLACE INTO project_settings (project_id, key, value) VALUES ((SELECT id FROM projects WHERE slug='ai-budget-assistant'), 'weekly_topics_scan_enabled', 'true');"
```

Trigger re-registration by toggling the project off/on, or by calling whatever endpoint normally re-registers jobs. Confirm in logs that the job got added.

- [ ] **Step 7.4: Smoke — trigger manually**

APScheduler exposes `run_job` programmatically. Simplest manual test: from a Python REPL connected to the running app's scheduler — or, faster, change the cron to `* * * * *` temporarily, wait one minute, watch for the live-log session. After confirming, restore the default and turn the toggle off.

- [ ] **Step 7.5: Commit**

```powershell
git add dreaming/services/scheduler.py
git commit -m "feat(topics): add weekly_topics_scan per-project cron job"
```

---

## Task 8: i18n strings + Topics-page hint

**Files:**
- Modify: `dreaming/i18n/messages_ru.json`
- Modify: `dreaming/i18n/messages_en.json`
- Modify: `dreaming/templates/project_topics.html`
- (Optional) Modify: `dreaming/templates/project_kanban.html` to replace hardcoded RU strings with `| t` filter

- [ ] **Step 8.1: Add RU keys**

Use the Edit tool (NOT `Set-Content` — see `CLAUDE.md`: PowerShell defaults to UTF-16 LE and breaks the parser). Append 3 keys before the closing `}` of `dreaming/i18n/messages_ru.json`:

```json
  "topics.generate.button": "Сгенерировать темы",
  "topics.generate.running": "Генерируется…",
  "topics.editor_hint": "Редактирование и генерация тем — на странице Kanban."
```

- [ ] **Step 8.2: Mirror EN keys**

```json
  "topics.generate.button": "Generate topics",
  "topics.generate.running": "Generating…",
  "topics.editor_hint": "Editing and generation live on the Kanban page."
```

- [ ] **Step 8.3: Verify i18n parity**

```powershell
python scripts/check_i18n.py
```

Expected: OK / identical keysets.

- [ ] **Step 8.4: Replace hardcoded button strings in the Kanban template**

In `dreaming/templates/project_kanban.html` (the button added in Task 5.3), swap the literal strings:

```html
{% if topics_running %}{{ "topics.generate.running" | t(locale=locale) }}{% else %}{{ "topics.generate.button" | t(locale=locale) }}{% endif %}
```

Confirm `locale` is in the template context. (`kanban_page` already passes `locale` — line 75.)

- [ ] **Step 8.5: Add the hint on the Topics page**

In `dreaming/templates/project_topics.html`, the placeholder block (lines 47-64) ends with a `<p class="text-xs text-sky-900">…</p>`. Just before that closing `</div>`, add a separator hint:

```html
<p class="text-xs mt-3 text-sky-900">
  {{ "topics.editor_hint" | t(locale=locale) }}
  <a href="/p/{{ project.slug }}/kanban" class="underline">Открыть Kanban →</a>
</p>
```

- [ ] **Step 8.6: Smoke**

- Reload `/p/ai-budget-assistant/kanban`. Button text changes with locale (`/locale/ru`, `/locale/en` if such a switcher exists; otherwise change the `dc_locale` cookie via DevTools and reload).
- Reload `/p/ai-budget-assistant/topics`. The blue placeholder block now contains the hint with a working link to Kanban.

- [ ] **Step 8.7: Commit**

```powershell
git add dreaming/i18n/messages_ru.json dreaming/i18n/messages_en.json `
        dreaming/templates/project_kanban.html dreaming/templates/project_topics.html
git commit -m "i18n(topics): add topics.* keys + Topics-page hint to Kanban"
```

---

## Task 9: Smoke script

**Files:**
- Create: `scripts/smoke_topics_generation.py`

- [ ] **Step 9.1: Write the script**

This is an integration smoke that simulates what the slash-command does (curl POSTs) without spawning a real Claude CLI. It verifies: ingest → DB → helper → extra_prompt content.

```python
"""Smoke test: topics ingest endpoint + prompt-injection helper.

Runs against a live dev server on port 8086. Picks any enabled project,
inserts 3 topics via POST /api/p/{slug}/topics/ingest, queries them via
GET /topics/list, calls build_topics_extra_prompt directly against the
same DB, asserts the generated block contains all 3 titles, and cleans up.

Exit code 0 on success, non-zero on any failure.
"""
from __future__ import annotations
import asyncio
import json
import sys
import urllib.request

import aiosqlite  # via dreaming dependency

BASE = "http://localhost:8086"


def http_json(method: str, path: str, body: dict | None = None) -> tuple[int, dict | list | str]:
    req = urllib.request.Request(BASE + path, method=method)
    data = None
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode("utf-8")
    try:
        with urllib.request.urlopen(req, data=data, timeout=10) as r:
            raw = r.read().decode("utf-8")
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


async def main() -> int:
    status, projects = http_json("GET", "/api/projects")  # adjust if endpoint differs
    if status != 200 or not isinstance(projects, list) or not projects:
        print(f"FAIL: cannot list projects: {status} {projects}", file=sys.stderr)
        return 1
    slug = next((p["slug"] for p in projects if p.get("enabled")), projects[0]["slug"])
    print(f"using project: {slug}")

    titles = ["SMOKE topic alpha", "SMOKE topic beta", "SMOKE topic gamma"]
    ids: list[str] = []
    for title in titles:
        status, body = http_json("POST", f"/api/p/{slug}/topics/ingest", {
            "title": title, "module": "smoke",
            "target_agents": "smoke-agent", "question": "?", "why_important": "smoke",
        })
        if status != 201:
            print(f"FAIL ingest: {status} {body}", file=sys.stderr)
            return 1
        ids.append(body["id"])
    print(f"ingested {len(ids)} topics")

    status, listing = http_json("GET", f"/api/p/{slug}/topics/list")
    listed_titles = {t["title"] for t in listing} if isinstance(listing, list) else set()
    missing = set(titles) - listed_titles
    if missing:
        print(f"FAIL list: missing {missing}", file=sys.stderr)
        return 1
    print(f"list shows all {len(titles)} titles")

    from dreaming.services.db import SqliteDB
    from dreaming.services.topics_prompt import build_topics_extra_prompt
    db = SqliteDB("dc.db")  # adjust if main.py uses a different path
    await db.connect()
    pid = (await db.fetch_one("SELECT id FROM projects WHERE slug=?", (slug,)))["id"]
    block = await build_topics_extra_prompt(db, pid, "smoke-agent")
    missing = [t for t in titles if t not in block]
    if missing:
        print(f"FAIL helper: missing titles in block: {missing}", file=sys.stderr)
        print(f"--- block ---\n{block}\n---", file=sys.stderr)
        return 1
    print("helper block contains all titles")

    # Cleanup
    for tid in ids:
        await db.delete_custom_topic(pid, tid)
    await db.close()
    print(f"cleaned up {len(ids)} topics. OK.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

If `/api/projects` doesn't exist (verify), replace with a direct SQLite query against `dc.db` to pick a slug. If the production DB path differs from `dc.db`, hardcode whatever path `main.py` uses.

- [ ] **Step 9.2: Run the smoke**

With the dev server running:

```powershell
python scripts/smoke_topics_generation.py
```

Expected: `OK.` on the last line, exit code 0. Confirm in the Kanban UI that the smoke rows are gone after cleanup.

- [ ] **Step 9.3: Commit**

```powershell
git add scripts/smoke_topics_generation.py
git commit -m "test(topics): add smoke_topics_generation script"
```

---

## Task 10: Docs

**Files:**
- Modify: `docs/ru/user/features/topics-kanban.md`
- Modify: `docs/en/user/features/topics-kanban.md`

- [ ] **Step 10.1: Update RU doc**

The current doc claims "Чек-лист генерирует и редактирует сам агент-стартеркит (например, team-lead.md)" (line 28 of `docs/ru/user/features/topics-kanban.md`) — this was aspirational and is now superseded. Update the Kanban section to:

- Describe the «Сгенерировать темы» button and `/topics-scan` slash-command.
- Describe the weekly cron `weekly_topics_scan` and its per-project enable/cron settings.
- Replace the `team-lead.md` mention with a note that the Topics page is now a static read-only view of `_weekly-learning-checklist.md` (kept for backwards compatibility) and the Kanban page is the canonical editor + generator.

- [ ] **Step 10.2: Mirror EN**

Apply the same changes to `docs/en/user/features/topics-kanban.md`.

- [ ] **Step 10.3: Commit**

```powershell
git add docs/ru/user/features/topics-kanban.md docs/en/user/features/topics-kanban.md
git commit -m "docs(topics): document generation button + weekly cron + injection wiring"
```

---

## Final verification

- [ ] All commits applied; `git log --oneline -10` shows the 10 feature commits.
- [ ] Manual run: visit `/p/<slug>/kanban`, click «Сгенерировать темы», wait for live-log completion, verify 5–10 new rows appear.
- [ ] Manual run: click Start on any agent in `/p/<slug>/rotation`, watch live log for the `## Темы на сегодня (из DC)` block.
- [ ] `python scripts/smoke_topics_generation.py` exits 0.
- [ ] `python scripts/check_i18n.py` passes.
