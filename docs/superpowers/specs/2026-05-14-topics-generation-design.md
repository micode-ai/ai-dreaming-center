---
date: 2026-05-14
status: draft
topic: topics-generation-and-injection
---

# Topics: generation, editing, injection

## Problem

The "topics" subsystem has two parallel implementations and three broken contracts:

1. **`/p/{slug}/topics`** (file-based): reads `.claude/agents/lessons/_weekly-learning-checklist.md`. Docs say "the team-lead agent generates this file during self-study", but no `team-lead.md` exists in `templates/starter-kit/agents/` and no code in `dreaming/**/*.py` ever writes to this file. The page is in practice always empty unless a human edits the file by hand.

2. **`/p/{slug}/kanban`** (DB-based): CRUD on `custom_topics` table works (`dreaming/routes/project_kanban.py:92-113`). Docs claim these topics are injected into the `/self-study` prompt during nightly cron. They are not: `dreaming/services/scheduler.py:_nightly_learning` (line 92) and `dreaming/routes/project_rotation.py:rotation_start` (line 87) call `process_manager.start_session(...)` without `extra_prompt`. `db.list_custom_topics_for_agent` exists (`db.py:797`) but has no callers.

3. **Generation**: nothing in the codebase generates topics. Both pages assume someone else does it.

The user wants: (a) topics auto-generated, (b) editable in DC UI. Editing (b) already works via Kanban. This spec closes generation and prompt injection.

## Goals

- Generate topics automatically from project context (recent commits, agent roster, learning notes, sidecar findings) on demand and on a weekly schedule.
- Keep generated topics in the existing `custom_topics` table — no schema change. Kanban CRUD continues to work unchanged.
- Wire `custom_topics` → agent prompts so generation has real effect during `/self-study` runs.

## Non-goals

- Reorganizing the Topics vs Kanban page split. The file-based Topics page stays read-only for now; a hint will point at Kanban as the editor.
- Per-week scoping of topics (`week` column on `custom_topics`). Out of scope; topics live until manually deleted.
- Topic deduplication via fuzzy matching. The generator will read existing topics and skip exact-title matches; near-duplicates are accepted.
- Replacing the `_weekly-learning-checklist.md` file flow entirely. The file remains as a human-authored side channel; this spec does not migrate it.

## Architecture

```
                    ┌────────────────────────────┐
   user clicks      │ POST /p/{slug}/topics/generate
   "Generate" ────► │  (new route handler)       │──┐
                    └────────────────────────────┘  │
                                                    │ spawns
   weekly cron                                      ▼
   "0 3 * * 1" ───► _weekly_topics_scan ──► pm.start_command(
                    (new fn in scheduler.py)    command_name="topics-scan",
                                                prompt="/topics-scan",
                                                env DREAMING_API_URL=...)
                                                            │
                                                            ▼
                                  ┌─────────────────────────────────────┐
                                  │ Claude CLI in {working_dir}        │
                                  │ runs templates/starter-kit/commands │
                                  │ /topics-scan.md                     │
                                  │                                     │
                                  │ For each topic it proposes:         │
                                  │   curl POST $DREAMING_API_URL       │
                                  │     /api/p/{slug}/topics/ingest     │
                                  └─────────────────────────────────────┘
                                                            │
                                                            ▼
                                  ┌─────────────────────────────────────┐
                                  │ POST /api/p/{slug}/topics/ingest    │
                                  │  (new handler in routes/api.py)     │
                                  │  → db.add_custom_topic(...)         │
                                  └─────────────────────────────────────┘
                                                            │
                                                            ▼
                                                    custom_topics table
                                                            │
                                  ┌─────────────────────────┘
                                  │
                                  ▼
   nightly cron / Start ────► _nightly_learning + rotation_start
   button on /rotation         fetch list_custom_topics_for_agent(...),
                               format markdown block, pass as extra_prompt
                               to pm.start_session(...)
                                  │
                                  ▼
                          Claude CLI receives:
                          "/self-study <agent>
                          
                          ## Custom topics for tonight (from DC)
                          - {title} (модуль: {module})
                            Question: {question}
                            Why important: {why_important}
                          ..."
```

## Components

### 1. `templates/starter-kit/commands/topics-scan.md` (new)

A slash-command spec, following the same pattern as `tech-debt-scan.md`:

- Reads project context: `.claude/agents/*.md` (agent roster), `git log --oneline -50`, `.claude/agents/learning-notes/`, `.claude/agents/sidecar-findings/`.
- Optionally GETs existing topics from `$DREAMING_API_URL/api/p/$DREAMING_PROJECT_SLUG/topics/list` to skip duplicates (new GET endpoint, see below).
- For each proposed topic, POSTs to `$DREAMING_API_URL/api/p/$DREAMING_PROJECT_SLUG/topics/ingest`:
  ```json
  {
    "title": "Refactor session management",
    "module": "auth",
    "target_agents": "vera,svetlana",
    "question": "What are the 3 main pain-points of current auth.login()?",
    "why_important": "Refactor starts in 2 weeks; need inventory."
  }
  ```
- Reports back via the existing `$DREAMING_API_URL/api/session/finish` curl.

### 2. New DC endpoints in `dreaming/routes/api.py`

```python
@router.post("/p/{slug}/topics/ingest")
async def topics_ingest(request: Request, slug: str, payload: TopicIngestIn):
    # Validates the project exists, calls db.add_custom_topic, returns 201.

@router.get("/p/{slug}/topics/list")
async def topics_list(request: Request, slug: str):
    # Returns active topics; called by the slash-command to skip duplicates.
```

Both routes resolve project by slug via `request.app.state.projects.get_by_slug(slug)`. They do NOT live under `/p/{slug}/...` because that path is reserved for the middleware-resolved HTML pages (which require cookies/session); these are callback APIs.

### 3. New UI handler in `dreaming/routes/project_kanban.py`

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

The button on the Kanban page (`templates/project_kanban.html`) becomes a tiny POST form pointing here. Disabled-while-running state is computed from `process_manager.list_running()` containing `cmd:{slug}:topics-scan` (matches the existing rotation-button lock pattern in `project_rotation.py:25-27`).

### 4. Weekly cron in `dreaming/services/scheduler.py`

Add to `_PER_PROJECT_JOBS`:

```python
("weekly_topics_scan", "weekly_topics_scan_cron", "weekly_topics_scan_enabled",
 "0 3 * * 1", False, _weekly_topics_scan),
```

Implementation of `_weekly_topics_scan` is a near-copy of `_weekly_tech_debt_scan` (lines 111-135) — just swaps `command_name`/`prompt` to `"weekly-topics-scan"` / `"/topics-scan"`. Default cron: Monday 03:00 local. Default enabled: False (opt-in via per-project settings UI, matching the other weekly scanners).

### 5. Prompt injection in `dreaming/services/scheduler.py:_nightly_learning` and `dreaming/routes/project_rotation.py:rotation_start`

Shared helper `services/topics_prompt.py`:

```python
async def build_topics_extra_prompt(db, project_id: int, agent_name: str) -> str:
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

Both call sites add:

```python
extra_prompt = await build_topics_extra_prompt(db, proj.id, agent_name)
await pm.start_session(..., extra_prompt=extra_prompt, ...)
```

`process_manager.start_session` already prepends `extra_prompt` correctly (`process_manager.py:167-169`). Empty string → no change to existing behavior, so existing flows stay byte-identical when no topics exist.

## Data flow

**Generation (manual):** Button on `/p/{slug}/kanban` → `POST /p/{slug}/topics/generate` → `pm.start_command(prompt="/topics-scan", ...)` → Claude CLI runs in project's working_dir → for each topic, `curl POST /api/p/{slug}/topics/ingest` → `db.add_custom_topic` → topic appears in Kanban list on next page refresh.

**Generation (scheduled):** APScheduler fires `_weekly_topics_scan` per project enabled with `weekly_topics_scan_enabled=true` → same path as manual after that.

**Injection:** Nightly cron (`_nightly_learning`) or manual rotation Start → `build_topics_extra_prompt` reads `custom_topics` filtered by `target_agents` for that agent → formats markdown → passed as `extra_prompt` → prepended to the `/self-study <agent>` prompt.

**Editing:** Unchanged. `/p/{slug}/kanban` form still POSTs to `/p/{slug}/kanban/add` and `/p/{slug}/kanban/{id}/delete`.

## Error handling

- **Concurrent generation**: `process_manager.start_command` already raises `RuntimeError` if `cmd:{slug}:topics-scan` is already running. Route returns HTTP 409. UI button is rendered disabled when the running key is present.
- **Invalid topic payload**: `/api/p/{slug}/topics/ingest` returns 422 (pydantic validation). The slash-command logs and continues — partial ingestion of a generation run is acceptable.
- **Unknown project slug**: `/api/p/{slug}/topics/ingest` returns 404. Slash-command logs and skips.
- **Generator times out**: `pm.start_command` enforces `timeout_minutes` and marks the session failed via the existing process_manager flow. Topics ingested before timeout are kept (no transaction wrapping the whole run — each topic is its own INSERT).
- **Empty `custom_topics`**: `build_topics_extra_prompt` returns `""` and the agent prompt is unchanged. No regression vs current behavior.

## Settings

New per-project keys (resolved by `ConfigResolver`, override-able from `/p/{slug}/settings`):

| Key | Default | Notes |
|-----|---------|-------|
| `weekly_topics_scan_cron` | `"0 3 * * 1"` | Monday 03:00 local |
| `weekly_topics_scan_enabled` | `false` | Opt-in, like other weekly scanners |

The existing per-project settings UI doesn't need new code: it discovers keys from `ConfigResolver` defaults at render time. (Verify on implementation — if it does require listing, add the key to wherever the settings UI's key list lives.)

## Testing

No test suite exists in this repo (per CLAUDE.md). Add a manual smoke script:

`scripts/smoke_topics_generation.py`:

1. Create a temp project pointing at a temp working_dir.
2. Replace `claude_path` setting with a stub binary that, when invoked with `/topics-scan`, curls a fixed list of 3 topics to `/api/p/{slug}/topics/ingest` and posts `session/finish`.
3. Call `POST /p/{slug}/topics/generate`.
4. Poll until the process_manager key clears.
5. Assert: 3 rows in `custom_topics` with the expected titles.
6. Call `build_topics_extra_prompt` directly for an agent in `target_agents`; assert non-empty and contains all 3 titles.

Run via `python scripts/smoke_topics_generation.py` after wave implementation.

## Files touched

New:
- `templates/starter-kit/commands/topics-scan.md` — slash-command spec.
- `dreaming/services/topics_prompt.py` — `build_topics_extra_prompt`.
- `scripts/smoke_topics_generation.py` — smoke test.

Modified:
- `dreaming/routes/api.py` — `POST /p/{slug}/topics/ingest`, `GET /p/{slug}/topics/list`.
- `dreaming/routes/project_kanban.py` — `POST /p/{slug}/topics/generate`, pass running-state to template.
- `dreaming/services/scheduler.py` — `_weekly_topics_scan` function, entry in `_PER_PROJECT_JOBS`, inject `extra_prompt` in `_nightly_learning`.
- `dreaming/routes/project_rotation.py` — inject `extra_prompt` in `rotation_start`.
- `dreaming/templates/project_kanban.html` — generate button + lock state.
- `dreaming/templates/project_topics.html` — hint pointing to Kanban for editing/generation.
- `dreaming/i18n/messages_ru.json`, `dreaming/i18n/messages_en.json` — new strings (RU primary, EN mirror per CLAUDE.md).

Docs (separate sweep — optional in the implementation plan):
- `docs/ru/user/features/topics-kanban.md`, EN twin — document the Generate button and the wired-up injection.
- `docs/ru/services.md`, EN twin — note the new helper if the file enumerates services.

## YAGNI deferred

- Per-week scoping (`week` column).
- Approval queue (generated topics auto-activate; user can delete via Kanban).
- Streaming progress in the UI (existing live-log captures stdout already).
- Fuzzy dedup; auto-archive of old topics.
- Replacing Topics page or removing the `.md` file flow.
