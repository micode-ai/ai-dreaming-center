# Route Inventory

The complete registry of HTTP routes. Grouped by prefix. Each route lists:

- HTTP method and path.
- Behaviour description.
- Bound template (if rendered).
- Services it uses.
- Source: file:line.

## Contents

- [Root](#root)
- [`/setup`](#setup)
- [`/projects`](#projects)
- [`/settings`](#settings)
- [`/api/`](#api)
- [`/articles`](#articles)
- [`/p/{slug}/`](#pslug)
- [`/static/`](#static)
- [Reserved paths](#reserved-paths)

## Root

Source: [`dreaming/routes/root.py`](../../dreaming/routes/root.py).

| Method | Path | Description | Template | Source |
|---|---|---|---|---|
| GET | `/health` | Simple health-check `{"ok": true}`. | — | root.py:12 |
| GET | `/` | Aggregated dashboard: per-project cards (week_stats, running, td_count, ideas_count, wiki_present), top-line totals, active runs aside. | `index_dashboard.html` | root.py:17 |
| GET | `/ai-usage` | Global AI Usage (via `ai_usage_stats.global_summary`). | `global_ai_usage.html` | root.py:109 |
| POST | `/locale` form `locale=&next=` | Sets the cookie `dc_locale`, max-age 1 year, samesite=lax. | — | root.py:126 |

`/` collects data via:
- `db.week_stats(proj.id)`.
- `pm.list_running()` filtered by `pfx = f"{slug}:"` or `cmd:{slug}:`.
- `ConfigResolver.get(proj, "tech_debt_dir", "")` + `list_tech_debt(td_dir)` if path exists.
- Same for `product_ideas_dir` and `wiki_dir`.

Note: when `working_dir` or directories are missing, falls back to 0/false; doesn't crash (root.py:60–61).

## `/setup`

Source: [`dreaming/routes/setup.py`](../../dreaming/routes/setup.py).

| Method | Path | Description | Source |
|---|---|---|---|
| GET | `/setup` | Renders the form with defaults from current settings. | setup.py:24 |
| POST | `/setup` | If `action=scan` — scans `projects_root`, renders the same page with the discovered subfolders. Otherwise — saves global YAML, imports the selected projects, registers cron jobs, redirects to `/`. | setup.py:46 |

Form fields on import:
- `claude_path`, `projects_root`, `default_locale` — global config.
- `scan_count` — how many items came from the scan.
- `slug_<i>`, `label_<i>`, `path_<i>`, `enabled_<i>`, `default_idx` — per row.

`_save_global_yaml` (setup.py:14) does a merge with the existing `config.yaml` (creates if absent). After save it calls `type(settings).load()` to refresh in-memory state (setup.py:83).

After `import_from_scan`, for each new project, calls `register_project_jobs(scheduler, app_state, proj)` (setup.py:108–111).

`scan_error` is rendered if: the path is empty, has no subfolders, or doesn't exist.

## `/projects`

Source: [`dreaming/routes/projects.py`](../../dreaming/routes/projects.py).

| Method | Path | Description | Source |
|---|---|---|---|
| GET | `/projects` | List of all projects. | projects.py:12 |
| POST | `/projects/{project_id}/toggle` | Toggle enabled. (Un)registers per-project jobs. | projects.py:23 |
| POST | `/projects/{project_id}/delete` | Deletes the project (CASCADE in DB); first calls `unregister_project_jobs`. | projects.py:40 |
| POST | `/projects/import` form `root=` | Bulk import from FS. | projects.py:50 |

Toggle (projects.py:32–36):
- new_enabled=True → `register_project_jobs`.
- new_enabled=False → `unregister_project_jobs`.

After toggle always returns 303 to `/projects`.

## `/settings`

Source: [`dreaming/routes/settings.py`](../../dreaming/routes/settings.py).

| Method | Path | Description | Source |
|---|---|---|---|
| GET | `/settings` | Renders the full form from `SETTINGS_GROUPS`. | settings.py:46 |
| POST | `/settings` | Saves to `config.yaml`, reloads in-memory settings. | settings.py:57 |

`_coerce` (settings.py:29) converts the form string back to the default's type (bool/int/float/str).

Bool fields: if the key is missing in the form, it's treated as unchecked → False (settings.py:68–70). That's the standard HTML idiom for an unchecked checkbox.

Token/api_key fields render as `type=password` (logic in the `settings.html` template).

## `/api/`

Source: [`dreaming/routes/api.py`](../../dreaming/routes/api.py).

| Method | Path | Description | Source |
|---|---|---|---|
| POST | `/api/session/start` | Creates a session DB row. | api.py:43 |
| POST | `/api/session/finish` | Closes the session + bumps rotation.last_studied_at. | api.py:52 |
| POST | `/api/orchestration/start` | Creates run + root node + event. 409 if a running one exists and `enforce_single=true`. | api.py:91 |
| GET | `/api/orchestration/{run_id}` | Snapshot run + nodes + messages. | api.py:118 |
| POST | `/api/orchestration/{run_id}/nodes/{node_id}/message` | Records a message into a node. | api.py:133 |
| POST | `/api/orchestration/{run_id}/finish` | Finishes the run. | api.py:149 |
| POST | `/api/cascade/init` | Creates a cascade run + 5 default stages. | api.py:205 |
| POST | `/api/cascade/{run_id}/stage/start` | Stage start. | api.py:240 |
| POST | `/api/cascade/{run_id}/stage/finish` | Stage finish. | api.py:250 |
| POST | `/api/cascade/{run_id}/gate` | Gate verdict. | api.py:260 |
| POST | `/api/cascade/{run_id}/artifact` | Artifact. | api.py:278 |
| POST | `/api/cascade/{run_id}/message` | Message into the run. | api.py:294 |
| POST | `/api/cascade/{run_id}/finish` | Cascade run finish. | api.py:314 |
| POST | `/api/p/{slug}/articles/ingest` | Callback for `/article-ideas-scan`: one article proposal. 400 on blank `evidence`, 422 on a bad `source`. `INSERT OR IGNORE` on `(project_id, slug_hint)` → 200 `duplicate:true`, otherwise 201. | api.py:474 |
| GET | `/api/p/{slug}/articles/list` | Dedup for the scan: `[{id, slug_hint, title, status}]` for the project. | api.py:634 |
| GET | `/api/articles/{proposal_id}` | The brief for `/write-article`: the whole `article_proposals` row. | api.py:646 |
| POST | `/api/articles/{proposal_id}/written` | Callback for `/write-article`. 409 if the status isn't `writing`. Success → `drafted`; `{error_message}` → `failed`. | api.py:655 |
| POST | `/api/p/{slug}/creatives/ingest` | Same as above for `/creative-ideas-scan`. Same `source` allow-list, same 400 on blank evidence. | api.py:513 |
| GET | `/api/p/{slug}/creatives/list` | Dedup for the campaign scan. | api.py:552 |
| GET | `/api/creatives/{proposal_id}` | The brief for `/make-creative`. | api.py:565 |
| POST | `/api/creatives/{proposal_id}/made` | Callback for `/make-creative`. 409 if the status isn't `making`. Success → `drafted`; `{error_message}` → `failed`. | api.py:574 |

Detailed body schemas and curl examples — in [`api.md`](api.md) (except the
eight article/creative rows above — their contract is documented in
[`features/articles.md`](features/articles.md) and
[`features/creatives.md`](features/creatives.md); the literal curl calls live
in the commands themselves, `templates/starter-kit/commands/*.md`).

## `/articles`

Source: [`dreaming/routes/articles.py`](../../dreaming/routes/articles.py). Mounted in `main.py` with no prefix, alongside `ai_radar_router` — not under `/p/{slug}/`.

| Method | Path | Description | Source |
|---|---|---|---|
| GET | `/articles` | Cross-project queue: every `article_proposals` row in status `proposed`, across every **enabled** project at once (a disabled/deleted project's rows are hidden, though they stay in the DB). A project badge on each card. | articles.py:17 |
| POST | `/articles/scan` form `target_project=` | Manually kick off `/article-ideas-scan` for the chosen project right from here, without navigating into that project's own `/p/{slug}/articles`. Shares `dispatch_article_scan` with the per-project scan button. | articles.py:50 |

The only button on a card here is Reject; approving an article requires that
project's own page. More — [`features/articles.md`](features/articles.md) and
[`user/features/articles.md`](user/features/articles.md).

## `/p/{slug}/`

`project_resolver_middleware` sets `request.state.project` for all of these. Under '/p/' an aggregator-router collects 19 sub-routers via `include_router`, see [`dreaming/routes/project_router.py`](../../dreaming/routes/project_router.py).

### Dashboard

Source: [`project_dashboard.py`](../../dreaming/routes/project_dashboard.py).

| Method | Path | Description | Template |
|---|---|---|---|
| GET | `/p/{slug}/` | week_stats + last 20 sessions + active running keys. | `project_dashboard.html` |

### Live + SSE

Source: [`project_live.py`](../../dreaming/routes/project_live.py).

| Method | Path | Description |
|---|---|---|
| GET | `/p/{slug}/live` | List of active runs + Kill buttons. |
| GET | `/p/{slug}/live/stream/{agent}` | SSE-stream of stdout. First sends a catchup (everything from `output_lines`), then live. Sentinel `event: end`. |
| POST | `/p/{slug}/live/kill/{agent}` | Kill the process. |

SSE is sent via `EventSourceResponse(gen())` (project_live.py:44). Each event: `{"event": "log", "data": line}`.

### Rotation

Source: [`project_rotation.py`](../../dreaming/routes/project_rotation.py).

| Method | Path | Description |
|---|---|---|
| GET | `/p/{slug}/rotation` | Roster. On entry auto-adds agents from `list_agent_names(working_dir)` if missing in DB. Passes `kit_status` to the template (see below). |
| POST | `/p/{slug}/rotation/tier` form `agent_name=&tier=` | Tier ∈ {1, 2, 3}. |
| POST | `/p/{slug}/rotation/toggle` form `agent_name=` | Toggle enabled. |
| POST | `/p/{slug}/rotation/start/{agent}` | Start self-study session, redirect to `/p/{slug}/live`. 409 if already running. |

`/rotation/start/{agent}` always passes env `DREAMING_PROJECT_SLUG` and `DREAMING_API_URL=http://localhost:{port}`.

### Starter-kit

Source: [`project_rotation.py`](../../dreaming/routes/project_rotation.py) (installer endpoint lives here for historical reasons — the path itself is neutral).

| Method | Path | Description |
|---|---|---|
| POST | `/p/{slug}/starter-kit/install` form `force=&redirect_to=` | Copies `templates/starter-kit/**` into `{working_dir}/.claude/`. `force=1` overwrites, otherwise skip-if-exists. Redirects to `redirect_to` or Referer (same-origin: only `/p/{slug}*`). |

Used by both the Rotation page and the Topics page — each sends its own `redirect_to` so the user lands back where they started.

See [`services.md#starter_kitpy--slash-command-installer`](services.md#starter_kitpy--slash-command-installer) and [`user/features/out-of-the-box.md#starter-kit`](user/features/out-of-the-box.md#starter-kit).

### Dashboard actions

Source: [`project_dashboard.py`](../../dreaming/routes/project_dashboard.py).

| Method | Path | Description |
|---|---|---|
| GET | `/p/{slug}/` | Dashboard. Passes `sessions`, `active_keys`, `active_key_set`, `kit_status`, `missing_dirs`, `bootstrap_needed` to the template. |
| POST | `/p/{slug}/bootstrap-all` | Master "out of the box" button: `starter_kit.install(force=False)` + `autoconfig.apply_all_defaults(skip_existing=True)`. Idempotent. Same-origin redirect to Referer. |
| POST | `/p/{slug}/sessions/{session_id}/stop` | Stop: if the process is alive — `pm.kill(key)`, otherwise `db.cancel_session(session_id)` (orphan). Redirects to `/p/{slug}/`. |
| POST | `/p/{slug}/sessions/{session_id}/delete` | Delete: kills the process if alive, then `db.delete_session(session_id)`. 404 if the row doesn't belong to this project. |
| POST | `/p/{slug}/sessions/force-close-stale` | Mass-marks every running row for this project as `cancelled` via `db.cancel_stale_running(project_id)`. Does not touch live processes. |

See [`user/features/out-of-the-box.md#session-controls`](user/features/out-of-the-box.md#session-controls).

### Settings (per-project)

Source: [`project_settings.py`](../../dreaming/routes/project_settings.py).

| Method | Path | Description |
|---|---|---|
| GET | `/p/{slug}/settings` | Form, renders `is_overridden` + global value + override value for each key in SETTINGS_GROUPS. |
| POST | `/p/{slug}/settings` | Per-key action: `inherit` → `unset_setting`; `override` → `set_setting` (or `unset_setting` if text-value is empty). |
| POST | `/p/{slug}/settings/autoconfig` form `key=&redirect_to=` | One-click: `mkdir -p` the default path for `key` (see `autoconfig.DEFAULTS`), save the override. Same-origin redirect to `redirect_to` or Referer. 400 if `key` is not in DEFAULTS. |

See details in [`features/settings.md`](features/settings.md) and [`user/features/out-of-the-box.md#directory-autoconfig`](user/features/out-of-the-box.md#directory-autoconfig).

### Topics, Kanban, Notes

| Method | Path | Description | Source |
|---|---|---|---|
| GET | `/p/{slug}/topics` | weekly-learning-checklist (read-only). | project_topics.py:10 |
| GET | `/p/{slug}/kanban` | Custom topics. | project_kanban.py:10 |
| POST | `/p/{slug}/kanban/add` | Add. | project_kanban.py:24 |
| POST | `/p/{slug}/kanban/{id}/delete` | Delete. | project_kanban.py:41 |
| GET | `/p/{slug}/notes` | List markdown notes. | project_notes.py:17 |
| GET | `/p/{slug}/notes/raw?path=` | Raw text; path-traversal-safe. | project_notes.py:33 |

### Findings (Tech-Debt)

Source: [`project_findings.py`](../../dreaming/routes/project_findings.py), [`project_tech_debt.py`](../../dreaming/routes/project_tech_debt.py).

| Method | Path | Description |
|---|---|---|
| GET | `/p/{slug}/findings` | TD list. |
| GET | `/p/{slug}/findings/{id}` | TD detail. |
| POST | `/p/{slug}/findings/{id}/close` | Rewrite frontmatter `status: closed`. |
| POST | `/p/{slug}/findings/{id}/delete` | Unlink .md. |
| GET | `/p/{slug}/tech-debt` | Aggregate by_status + by_module. |

### Ideas

Source: [`project_ideas.py`](../../dreaming/routes/project_ideas.py).

| Method | Path | Description |
|---|---|---|
| GET | `/p/{slug}/ideas?status=` | List, filter by status. |
| POST | `/p/{slug}/ideas/{id}/jira` | Creates a Jira Task; remembers the key in frontmatter `jira_ticket: RGS-123`. |
| POST | `/p/{slug}/ideas/{item_id}/propose-article` | Feeds the article pipeline: idea → `article_proposals(source='center')`. The button never disables itself once used — a second click just returns "duplicate". See [`features/articles.md`](features/articles.md). | project_ideas.py:189 |

### Articles

Source: [`project_articles.py`](../../dreaming/routes/project_articles.py). Full lifecycle, venue resolution and publishing detail — in [`features/articles.md`](features/articles.md); this table is inventory only.

| Method | Path | Description | Source |
|---|---|---|---|
| GET | `/p/{slug}/articles` | The project's proposals, grouped by status (`proposed/writing/drafted/published/rejected/failed` + `other`). | project_articles.py:87 |
| POST | `/p/{slug}/articles/add` form `title=&angle=&venue=` | Manual proposal, `source='manual'`. Blank `title` → 400. | project_articles.py:225 |
| POST | `/p/{slug}/articles/{id}/reject` | `proposed/... → rejected`. | project_articles.py:294 |
| POST | `/p/{slug}/articles/{id}/restore` | `rejected → proposed`. | project_articles.py:309 |
| POST | `/p/{slug}/articles/{id}/venue` form `venue=` | Changes the venue override, while the row is still `proposed`. 409 after dispatch — the venue is already pinned. | project_articles.py:322 |
| POST | `/p/{slug}/articles/scan` | Dispatches `/article-ideas-scan` into the project. Proposes only — never writes, never publishes. | project_articles.py:399 |
| POST | `/p/{slug}/articles/{id}/approve` | First human gate: resolves the venue + blog root, dispatches `/write-article {id}` with `bypassPermissions`. 409 if the status isn't in `(proposed, approved, failed, drafted)`. | project_articles.py:408 |
| POST | `/p/{slug}/articles/{id}/cancel` | `writing → failed` by hand. Does not kill the process. | project_articles.py:576 |
| POST | `/p/{slug}/articles/{id}/revise` form `notes=&finding=` | Writes `revision_notes`, calls the same code as approve. 400 on an empty request. | project_articles.py:615 |
| GET | `/p/{slug}/articles/{id}/preview?lang=&file=` | Shows `draft_ref`'s working tree, validated by the same validator publish uses. | project_articles.py:660 |
| POST | `/p/{slug}/articles/{id}/publish` | Second gate: commits only the paths from `draft_ref` (+ `article_publish_extra_paths`). Terminal transition to `published`. | project_articles.py:812 |

A fourth feeder lives outside this file and outside `/p/{slug}` — `POST
/ai-radar/{finding_id}/propose-article` in
[`dreaming/routes/ai_radar.py`](../../dreaming/routes/ai_radar.py)
(`source='radar'`, evidence assembled from the finding itself). AI Radar as a
section is not otherwise covered by this inventory — see
[`features/articles.md`](features/articles.md#who-submits-proposals).

### Creatives

Source: [`project_creatives.py`](../../dreaming/routes/project_creatives.py). Differences from articles and the shared machinery — in [`features/creatives.md`](features/creatives.md).

| Method | Path | Description | Source |
|---|---|---|---|
| GET | `/p/{slug}/creatives` | The project's campaigns by status (`proposed/making/drafted/published/rejected/failed` + `other`). | project_creatives.py:202 |
| POST | `/p/{slug}/creatives/scan` | Dispatches `/creative-ideas-scan`. | project_creatives.py:267 |
| POST | `/p/{slug}/creatives/add` multipart `title=&angle=&venue=&formats=&locales=&files=` | Manual proposal **with attachments in one step** — the one way this form differs from articles'. | project_creatives.py:305 |
| POST | `/p/{slug}/creatives/{id}/attach` multipart `files=` | Attach material into `<slug>/src/`. 409 while the campaign is `making`. | project_creatives.py:409 |
| POST | `/p/{slug}/creatives/{id}/approve` | Dispatches `/make-creative {id}` with `bypassPermissions`. | project_creatives.py:450 |
| POST | `/p/{slug}/creatives/{id}/cancel` | `making → failed` by hand. See [Known gap: reconcile is not wired up](features/creatives.md#known-gap-reconcile-is-not-wired-up) — unlike articles, there's no automatic recovery. | project_creatives.py:526 |
| POST | `/p/{slug}/creatives/{id}/reject` | `proposed/failed → rejected`. | project_creatives.py:541 |
| POST | `/p/{slug}/creatives/{id}/restore` | `rejected → proposed`. | project_creatives.py:554 |
| POST | `/p/{slug}/creatives/{id}/venue` form `venue=` | Changes the venue, while `proposed`/`failed`. | project_creatives.py:565 |
| GET | `/p/{slug}/creatives/{id}/preview?fmt=&loc=` | Tabs by `(format, locale)`, renders + post copy. | project_creatives.py:587 |
| GET | `/p/{slug}/creatives/{id}/media?path=` | Serves one render/attachment — only a path the row itself named in `draft_ref` or one of its own attachments, only an extension on the allow-list (no `.svg`). | project_creatives.py:668 |
| POST | `/p/{slug}/creatives/{id}/revise` form `notes=&finding=` | Same as articles: findings + text → `revision_notes`, calls approve. | project_creatives.py:716 |
| POST | `/p/{slug}/creatives/{id}/publish` | The same `article_publish.publish` articles use. 409 if `draft_ref` is empty. | project_creatives.py:742 |

### Wiki

Source: [`project_wiki.py`](../../dreaming/routes/project_wiki.py).

| Method | Path | Description |
|---|---|---|
| GET | `/p/{slug}/wiki` | Status (via `get_wiki_status`). |
| POST | `/p/{slug}/wiki/bootstrap` | Runs `/wiki-bootstrap` via `pm.start_command`. Redirect to `/p/{slug}/live`. |

### Orchestration

Source: [`project_orchestration.py`](../../dreaming/routes/project_orchestration.py).

| Method | Path | Description |
|---|---|---|
| GET | `/p/{slug}/orchestration` | List of runs (last 50). |
| GET | `/p/{slug}/orchestration/{run_id}` | Run detail with polling (via JS). |
| POST | `/p/{slug}/orchestration/start` form `goal=` | Creates run + root node, spawns claude, starts ClaudeSessionTail + SubagentWatcher. 409 → redirect to existing run. |
| POST | `/p/{slug}/orchestration/{run_id}/finish` | Finishes the run. |
| GET | `/p/{slug}/orchestration/{run_id}/refresh` | JSON polling. Returns `{status, finished_at, node_count, message_count, nodes, messages}`. |
| POST | `/p/{slug}/orchestration/{run_id}/resume` form `prompt=` | claude --resume + interactive_stdin. |

More — in [`features/orchestration.md`](features/orchestration.md).

### Analytics dashboards (read-only)

| Method | Path | Description | Service |
|---|---|---|---|
| GET | `/p/{slug}/ai-usage` | Token usage. | `ai_usage_stats.project_summary` |
| GET | `/p/{slug}/cascade-costs` | Cost roll-up per run. | `cascade_costs.list_cascade_costs` |
| GET | `/p/{slug}/evolutions` | Agent _context overrides. | `evolutions.list_evolutions` |
| GET | `/p/{slug}/loops` | Reflex loops. | `loops.list_loops` |
| GET | `/p/{slug}/plans` | Plans with progress%. | `plans.list_plans` |
| GET | `/p/{slug}/contracts` | Module/page contracts. | `contracts.list_contracts` |
| GET | `/p/{slug}/sidecar-findings?severity=` | Sidecar reviewer JSON findings. | `sidecar_findings.list_sidecar_findings` |

All follow the same pattern (resolver → dir setting → list → render).

## `/static/`

Mounted in `main.py:80`:

```python
app.mount("/static", StaticFiles(directory="dreaming/static"), name="static")
```

Files: `dreaming/static/app.css`. Tailwind comes from a CDN (see `templates/base.html`).

## Reserved paths

FastAPI auto-mounts:
- `/docs` — Swagger UI.
- `/redoc` — ReDoc.
- `/openapi.json` — OpenAPI schema.

**Do NOT define** your own routes on these paths — they get silently overridden. setup_gate skips them (see [`middleware/setup_gate.py:8`](../../dreaming/middleware/setup_gate.py)).

## Cross-references

- Full body schemas and curl examples — [`api.md`](api.md).
- What each service does — [`services.md`](services.md).
- Templates and i18n — [`features/i18n.md`](features/i18n.md).
- Multi-project resolver — [`features/multi-project.md`](features/multi-project.md).
