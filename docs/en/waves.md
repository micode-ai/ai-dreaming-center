# Waves history

History of AI Dreaming Center development: what was done in each wave, the git tag, what was deferred.

## Contents

- [Wave 0 — Foundation](#wave-0--foundation)
- [Wave 1 — Self-study core](#wave-1--self-study-core)
- [Wave 2 — Pipeline pages](#wave-2--pipeline-pages)
- [Wave 2.5 — Tech-debt + Jira + Wiki bootstrap](#wave-25--tech-debt--jira--wiki-bootstrap)
- [Wave 3 lean — OrchestrationHub](#wave-3-lean--orchestrationhub)
- [Wave 3.6 — claude_session_tail / subagent_watcher / backfill](#wave-36--claude_session_tail--subagent_watcher--backfill)
- [Wave 3.7 — orchestration spawns claude](#wave-37--orchestration-spawns-claude)
- [Wave 3.8 — cascade pipelines API](#wave-38--cascade-pipelines-api)
- [Wave 3.9 (Wave 3 full) — contracts + sidecar + tts stub](#wave-39-wave-3-full--contracts--sidecar--tts-stub)
- [Wave 4 lite — AI Usage analytics](#wave-4-lite--ai-usage-analytics)
- [Wave 4 full — evolutions / loops / plans / cascade-costs](#wave-4-full--evolutions--loops--plans--cascade-costs)
- [Wave 5 — aggregated dashboard](#wave-5--aggregated-dashboard)
- [Wave D1/D2 — Design system foundation](#wave-d1d2--design-system-foundation)
- [Wave A — Article pipeline](#wave-a--article-pipeline)
- [Wave B — Article cross-project](#wave-b--article-cross-project)
- [Wave C — Article committed build output](#wave-c--article-committed-build-output)
- [Not implemented yet](#not-implemented-yet)

## Wave 0 — Foundation

**Tag**: `wave-0`. Acceptance commits: `c9800b3` (skeleton) → `efaef43` (smoke OK).

**Goal**: minimum FastAPI app with the DB schema, middlewares and a starter setup wizard.

**What landed**:
- Project skeleton: `pyproject.toml`, `dreaming/main.py`, `dreaming/__init__.py`.
- Minimum FastAPI app on 8086 with `/health` (`96795d4`).
- SQLite schema fork from ALC + `project_id` (`5ee789b`).
- ProjectsService — CRUD + scan_projects_root (`c1cfc2e`).
- ConfigResolver — override-with-fallback (`10ae4fe`).
- setup_gate + project_resolver middleware + `project_not_found.html` (`2200281`).
- i18n loader + Jinja `t()` + CLDR Russian plurals (`3860dee`).
- Key-parity verifier `scripts/check_i18n.py` (`5da55c8`).
- Setup wizard: global config + projects_root scan + bulk import (`a529c9c`).
- /projects list, toggle, delete, import (`c174a89`).
- /settings minimal UI (`e1f0843`).
- Stub services + minimal scheduler (`df1849f`).
- End-to-end smoke (`efaef43`).

**Acceptance**: app starts, wizard works, projects register, idempotent import.

**Deferred**:
- Real ProcessManager (Wave 1).
- Sessions API (Wave 1).
- Pipeline pages (Wave 2).

## Wave 1 — Self-study core

**Tag**: `wave-1`. Acceptance commits: `a6ed585` → `b7824f9`.

**Goal**: nightly self-study + per-project dashboard + sessions REST API.

**What landed**:
- Port `keep_awake.py` from ALC (`1743d9a`).
- Port ProcessManager + project_id awareness (`a6ed585`).
- SqliteDB session/rotation domain methods (`79ac75f`).
- /api/session/start|finish (`e0e87cf`).
- Project-scoped routes `/p/{slug}/{,live,rotation}` + agents discovery (`6ef210f`).
- /p/{slug}/settings minimal UI (`651afcb`).
- Per-project nightly_learning_{slug} cron + register/unregister hooks (`5f9855e`).
- End-to-end smoke (`b7824f9`).

**Acceptance**:
- Session API works in multi-project mode.
- Dashboard renders week_stats.
- Rotation page with tier/enabled inline edit.
- Live SSE streaming.
- Nightly cron fires and starts claude.

**Deferred**:
- Pipeline pages (Wave 2).
- Topics, Kanban, Notes (Wave 2.1).

## Wave 2 — Pipeline pages

**Tag**: `wave-2`. Acceptance commits: `3b9995b`, `87fc009`, `f3270d3`, `8bd34b8`, `5a6f5b4`.

**Goal**: read-only pages for every ALC pipeline.

**What landed**:
- Wave 2.1 (3b9995b): Topics, Kanban, Notes.
- Wave 2.2 (87fc009): tech-debt parser + /findings + /tech-debt minimal.
- Wave 2.3+2.4 (f3270d3): Product Ideas board + Wiki bootstrap status.
- Wave 2.5 weekly_*_{slug} cron kinds + start_command project-scoping (8bd34b8).
- Smoke E2E for all 7 pipeline pages (5a6f5b4).

**Acceptance**:
- Every pipeline page renders without 500 (even with an empty dir).
- weekly_tech_debt_scan_{slug} registers when `weekly_tech_debt_scan_enabled=true`.

**Deferred**:
- TD detail / close / delete (Wave 2.5).
- Jira integration (Wave 2.5).
- Wiki bootstrap button (Wave 2.5).

## Wave 2.5 — Tech-debt + Jira + Wiki bootstrap

**Tag**: `wave-2.5`. Acceptance commit: `e39a0fe`.

**Goal**: actionable actions from the UI on pipeline pages.

**What landed**:
- TD detail page (`/p/{slug}/findings/{id}`).
- TD close (rewrite frontmatter `status: closed`).
- TD delete (unlink the file).
- Jira service (`dreaming/services/jira.py`).
- Ideas → Jira button with `jira_ticket: <key>` persisted into frontmatter.
- Wiki bootstrap button — `/p/{slug}/wiki/bootstrap` POST → `pm.start_command("/wiki-bootstrap")`.

**Acceptance**:
- The buttons actually do something.
- Per-project `jira_project_key` override works.
- Wiki bootstrap appears in `/p/{slug}/live` after a few seconds.

## Wave 3 lean — OrchestrationHub

**Tag**: `wave-3-lean`. Acceptance commit: `dcec547`.

**Goal**: DB-backed runs/nodes/messages for Roman flows + a minimal API endpoint set + UI for inspection.

**What landed**:
- Real `OrchestrationHub` impl: create_run, create_node, append_message, finish_run, ensure_stage, append_event, etc.
- 4 base API endpoints: `/api/orchestration/start`, `/{run_id}`, `.../message`, `/finish`.
- /p/{slug}/orchestration list page.
- /p/{slug}/orchestration/{run_id} detail page.
- One-Roman-per-project lock in `has_running_run` + 409.

**Acceptance**:
- A run can be created via curl and seen in the UI.
- The lock prevents creating a second parallel run.

**Deferred**:
- Spawning claude from POST /start (Wave 3.7).
- ClaudeSessionTail (Wave 3.6).
- SubagentWatcher (Wave 3.6).
- Cascade stages API (Wave 3.8).
- TTS, sidecar, contracts (Wave 3.9).

## Wave 3.6 — claude_session_tail / subagent_watcher / backfill

**Tag**: (no separate one, included in the `wave-3-full` peak). Commit: `75e67b0`.

**Goal**: real implementation of tail-watchers for Claude jsonl files.

**What landed**:
- `dreaming/services/claude_session_tail.py` — `tail_session_file`, `ClaudeSessionTail`, helpers (encode_workdir, find_session_file_by_id, find_recent_session_files, etc.).
- `dreaming/services/subagent_watcher.py` — `watch_subagents_for_run`, `SubagentWatcher`, `_resolve_node_for_subagent`.
- `dreaming/services/subagent_backfill.py` — `backfill_run` for offline replay.

**Acceptance**:
- Start a run, the file `~/.claude/projects/<workdir>/<session>.jsonl` updates live, messages appear in the DB.

**Deferred**: spawning claude from form-based start (Wave 3.7).

## Wave 3.7 — orchestration spawns claude

**Commit**: `f13babe`.

**Goal**: the form-based "Start Orchestration" button now actually starts claude and attaches watchers.

**What landed**:
- The form `POST /p/{slug}/orchestration/start` accepts `goal` and:
  - Creates run + root_node.
  - Spawns claude via `pm.start_command(session_id=claude_session_id)`.
  - Starts `ClaudeSessionTail` + `SubagentWatcher` via `asyncio.create_task`.
  - Saves the tasks to `app.state.orchestration_tails` and `orchestration_watchers`.
- `GET /refresh` — JSON for browser polling.
- `POST /resume` — `claude --resume <session_id>` + `interactive_stdin=True`.

**Acceptance**:
- Click Start, within seconds messages show up on the detail page.
- Resume works against an old session_id.

## Wave 3.8 — cascade pipelines API

**Commit**: `f59a8ea`.

**Goal**: API for cascade pipelines (5 stages with gates and artifacts).

**What landed**:
- 7 endpoints under `/api/cascade/`:
  - `init` (creates the run + 5 default stages).
  - `stage/start`, `stage/finish`.
  - `gate` (verdict).
  - `artifact` (with dedup_hash).
  - `message`.
  - `finish`.
- `dreaming/services/harness_client.py` — `HarnessClient` + `HarnessClientCache`.
- `dreaming/services/cascade_stage_detect.py` — heuristic detector.

**Acceptance**:
- `curl /api/cascade/init` creates a run and 5 stages.
- `dedup_hash` collision returns `{"id": null, "deduped": true}`.

**Deferred**: starter-kit slash commands `/cascade-task` and `/cascade-contract` — these are part of the external project, not DC.

## Wave 3.9 (Wave 3 full) — contracts + sidecar + tts stub

**Tag**: `wave-3-full`. Commit: `b49aafd`.

**Goal**: Wave 3 finalisation — add contracts page, sidecar findings page, tts_backfill stub.

**What landed**:
- `dreaming/services/contracts.py` + route + template.
- `dreaming/services/sidecar_findings.py` + route + template.
- `dreaming/services/tts_backfill.py` (stub).

**Acceptance**:
- /p/{slug}/contracts and /p/{slug}/sidecar-findings render.

**Deferred**:
- Real TTS backfill (stub returns 0).
- Full AskUserQuestion plumbing (table created in migration but the full API isn't there yet).

## Wave 4 lite — AI Usage analytics

**Tag**: `wave-4-lite`. Commit: `1c84f44a`/`1c84f44`/`1c84f44` — effectively `1c8...` (see `git log --grep "Wave 4 lite"`). The tag points to `1c8`.

**Goal**: per-project + global token usage.

**What landed**:
- `dreaming/services/ai_usage_parser.py` — incremental JSONL → `ai_usage_events`.
- `dreaming/services/ai_usage_stats.py` — `project_summary`, `global_summary`.
- `/p/{slug}/ai-usage` route + template.
- `/ai-usage` global route + template.
- Ingest cron (every 5 min).

**Acceptance**:
- Rows appear in the `ai_usage_events` table after the first ingest.
- Dashboard shows last_7d / last_30d totals + by_model.

## Wave 4 full — evolutions / loops / plans / cascade-costs

**Tag**: `wave-4-full`. Commit: `9841f53`.

**Goal**: 4 more read-only dashboards.

**What landed**:
- `dreaming/services/evolutions.py` + route + template.
- `dreaming/services/loops.py` + route + template.
- `dreaming/services/plans.py` + route + template (with progress%).
- `dreaming/services/cascade_costs.py` + route + template.
- Full ~80-key settings UI grouped by category (`4a44f02`).

**Acceptance**:
- All 4 pages render.
- Per-project + global settings UI shows every one of the 80+ keys.

## Wave 5 — aggregated dashboard

**Tag**: `wave-5`. Commit: `d33bd3c`.

**Goal**: the home page `/` shows per-project cards + global totals + active runs.

**What landed**:
- `index_dashboard.html` template.
- `root.py:index` collects stats for every project in one handler.
- Cross-project metrics: total success/failed/timeout/running, sum td/ideas, wiki_present.
- Active runs aside.
- README/CLAUDE.md final.

**Acceptance**:
- `/` renders N cards (one per enabled project).
- Active running keys are displayed.

## Wave D1/D2 — Design system foundation

**Tag**: `design-system`. Merge commit `83df347`, range `666c72b`..`5aebaa5` — 80 commits, 56 files, +2719/−1670.

**Spec**: [`docs/superpowers/specs/2026-08-16-design-system-foundation-design.md`](../superpowers/specs/2026-08-16-design-system-foundation-design.md)
**Plan**: [`docs/superpowers/plans/2026-08-16-design-system-foundation.md`](../superpowers/plans/2026-08-16-design-system-foundation.md)

**Problem**: `app.css` defined tokens and almost nothing used them. Appearance was encoded directly in markup — **491 static inline `style=` attributes** and **464 light-theme Tailwind utilities** (`bg-white`, `text-slate-900`, `border-slate-200`) inherited from the ALC port. A block of ~50 `!important` rules at the bottom of `app.css` retro-fitted the dark theme onto whichever utilities someone had remembered to patch. The unpatched ones rendered light.

**Result**:

| | Before | After |
|---|---|---|
| Static inline `style=` | 491 | **0** |
| Light-theme colour utilities | 464 | **0** |
| `!important` in `dreaming/static/` | ~50 | **0** |
| Button classes | 0 (100+ markup variations) | `.btn` + 5 variants |

**What went in**:

- **Stylesheet split** into three files with enforced boundaries: [`tokens.css`](../../dreaming/static/tokens.css) — `:root` only (89 tokens, the single place the app's look is defined); [`components.css`](../../dreaming/static/components.css) — semantic classes, no colour literal; [`app.css`](../../dreaming/static/app.css) — base elements, form elements, sidebar shell, `.md-content`.
- **Component layer**: `.btn` (+ `primary` / `danger` / `warn` / `ghost` / `success` / `sm`), `.card`, `.panel`, `.banner` (+ `info` / `warn` / `danger` / `brand` / `--inline`), `.page-header`, `.section-title`, `.toolbar`, `.empty-state`, `.field`, `.num`, `.data-table.is-dense`, `.meter-track` / `.meter-fill`, `.filter-tab`, `.stat-chip`, `.rubric-tile`, `.queue-item`.
- **All 51 templates migrated** — shell first, then three acceptance-gate screens (dashboard, orchestration, findings), then in batches.
- **`!important` block deleted** as the final commit, behind a green linter gate.
- **Two new check scripts** (below).

**Bugs fixed** (not only appearance):

- `bg-sky-50` and `bg-amber-50` in seven files rendered as near-white boxes on the dark app — never covered by the `!important` block.
- `border-purple-500 text-purple-700` buttons — dark purple text on a dark card.
- **~20 light-theme colours the spec did not know about**, found during migration and fixed with recomputed contrast: `#059669` at 3.97:1, `#b91c1c` at 2.46:1, nine in `orchestration_swimlane.css` (its "failed" status pill measured 2.4:1), and the kanban row highlight at 2.61:1 → 12.09:1.
- `orchestration_swimlane.css` referenced `var(--bg-surface)` — **a token that never existed**; the swimlane wrapper rendered transparent.
- The live-view Kill button carried `hover:bg-red-100`, and the `!important` block shimmed red backgrounds but not their hover variants — it flashed literal light Tailwind colour on mouse-over.
- `.field__control` set a background at specificity (0,1,0) while the base rule targets `input` through nine attribute selectors at (0,9,1). The component background never applied to `<input>` but did to `<select>`: three consecutive fields on `/setup` rendered two different colours.

**New checks** (in the existing `scripts/check_*` / `smoke_*` convention):

- [`scripts/check_css_tokens.py`](../../scripts/check_css_tokens.py) — four assertions: no colour literal in `components.css` (including `rgb()`/`rgba()`/`hsl()`, black permitted for shadows); no light-theme utility in templates; no static inline `style=`; and **every class the markup references is defined** — in our CSS, in a template `<style>` block, or referenced by JavaScript as a hook. Exits 0.
- [`scripts/smoke_templates_render.py`](../../scripts/smoke_templates_render.py) — compiles all 51 templates (catching a Jinja typo on a page nobody opens) and walks all 45 parameter-free GET routes asserting no 500. No such safety net existed before.

**Acceptance**: `check_css_tokens.py` → `ALL OK`, exit 0. `smoke_templates_render.py` → 51 templates, 45 routes, exit 0. `check_i18n.py`, `check_no_native_dialogs.py`, `smoke_table_tools.py`, `smoke_ai_radar.py` all green. A sweep of 30 pages computing background luminance for 8487 elements found zero light islands.

**What did NOT change**: no application Python. Not one string, `data-*`, `hx-*`, `id`, `name`, `action`, `data-confirm`, or `| t()` call — verified by multiset comparison across all 51 templates between base and head.

**Deferred**:

- **Inherited dead code** — `.pill-nav` / `.pill` in `components.css` (used by no template), the unreachable `{% if flash %}` block in `base.html` (`read_flash` has no callers; flashes are consumed client-side by `_app_modal.html`), `.md-content` in `app.css` (37 lines; the live renderer class is `markdown-body`), and the dead `project_orchestration_detail.html`. Removing inherited dead code is a separate decision from migrating. **~90 lines, one commit.**
- **Seven single-property `.text-*` colour utilities** in `components.css` — a third parallel system alongside `.badge-*` and `.metric.metric-*`, ~115 call sites. Growth was capped; consolidating into one base class with modifiers is a D3 input.
- **`_is_tailwind()` in the linter is too permissive**: it accepts any token whose first segment is a Tailwind root, so `.text-warn` and `.bg-elevated` are indistinguishable from real utilities. **A typo in any of the eight custom classes passes silently** — the exact failure mode that check was written for. Tighten alongside the `.text-*` consolidation.
- **Card shadows are inconsistent**: `.metric` and `.pill-nav` carry `--shadow-card`, `.card` and `.data-table` do not. Direction A calls for none; unifying is a visible change on every dashboard, so it belongs to D3.
- **Table density deviates from the spec**: `project_notes`, `project_plans`, `project_contracts` are named in the spec's comfortable group but shipped `.is-dense`. `project_kanban` and `project_topics` show the same data at two densities.
- **D3** (applying the visual direction) and **D4** (key screens, ergonomics) get their own specs.

**Unrelated defect found in passing**: `scripts/smoke_dashboard_tiles.py` prints its full OK sequence but **never terminates** — the process hangs holding a SQLite connection open. Looks like an unclosed async connection or an uncancelled task keeping the event loop alive. The result is correct, but a CI run would hang on it.

## Wave A — Article pipeline

**Branch**: `feature/article-pipeline`, range `e4f4bcc`..`211b538` — 28 commits, 27 files, +2683/−13. (`b9430e9` was the wrong base — that's the spec commit already on master; the real merge base is `e4f4bcc`.)

**Spec**: [`docs/superpowers/specs/2026-08-20-article-pipeline-design.md`](../superpowers/specs/2026-08-20-article-pipeline-design.md)
**Plan**: [`docs/superpowers/plans/2026-08-20-article-pipeline.md`](../superpowers/plans/2026-08-20-article-pipeline.md)
**Issue**: [#34](https://github.com/micode-ai/ai-dreaming-center/issues/34)

**Goal**: the center proposes article topics per project, dispatches that project's own writer agent once a topic is approved, and publishes the result by committing it into the project's repository after a second approval.

**Two corrections to the premise that shaped the design.** A writer agent exists in only 3 of the 11 managed projects (`blog-writer` in `mi-code-ai` and `ai-budget-assistant`, `kb-page-author` in `legalka-kb`), so the pipeline has to work without one rather than pretend otherwise. And the publishing format differs per project: the landing page keeps prose as data in `blog-posts.json` plus an entry in `vite.config.ts`, `accounting-ai-agent` uses per-locale markdown with a strict frontmatter contract, `legalka-kb` has its own structure. So the center owns the proposal; the project owns the article's shape.

**What shipped**:

- An `article_proposals` table with the status machine `proposed → approved → writing → drafted → published` (plus `rejected` / `failed`) and `UNIQUE(project_id, slug_hint)`, so three feeders converging on one subject produce one row.
- Feeder API: `POST /api/p/{slug}/articles/ingest` (blank `evidence` → **400**), `GET .../articles/list` for dedupe, `GET /api/articles/{id}`, and `POST /api/articles/{id}/written` guarded to 409 outside `writing`.
- Three feeders: the `article-ideas-scan` starter-kit command, a "propose an article" button on the AI Radar card, and the same on the product ideas page.
- The `write-article` starter-kit command: reads the brief from the API, resolves the writer (setting → autodetect in `.claude/agents/` → itself), learns the format from neighbouring posts, runs `article_verify_cmd`, and reports `draft_ref` plus the verification output back.
- Publishing commits only the paths in `draft_ref` — never `git add -A`, never `git stash`.
- A `/p/{slug}/articles` page grouped by status, and a cross-project `/articles` queue.
- A weekly `weekly_article_ideas_scan` job, disabled by default. The cron may only propose: it structurally cannot write or publish.

**The rule imported from `micode-landing-page`**: a proposal must carry `evidence` — a traceable fact (a commit, a closed wave, a dated release, a measured gap). This is the principle `scripts/ai-visibility/advice.mjs` states outright: "a suggestion nobody can check is worse than no suggestion". It is enforced at the API, not in the prompt.

**Defects review caught during the wave** (all fixed inside their own tasks):

- `slugify` truncated titles to six words while `slug_hint` is unique, so two different subjects sharing an opening ("Improve error handling in the parser" and "... in the scheduler") mapped to one slug; the second proposal came back as a duplicate and was **silently lost**. Fixed with a deterministic suffix applied only when truncation actually drops words.
- `git add -- <path>` does refuse paths outside the repository — but it also faithfully honours pathspec magic, so a `draft_ref` of `:(glob)**/*` turned the path-scoped add into an effective `git add -A`. Closed with validation (absolute paths, `..`, glob characters, existing regular file only) plus `--literal-pathspecs`. `-f` is never passed: git's refusal to add ignored files is what keeps gitignored secrets out of our commits.
- A `git commit` failure after a successful `git add` left the index staged, and a retry then hit the module's own "these paths already have staged changes" check forever. A rollback of exactly our paths was added.
- A `git push` failure after a successful commit lost the sha from the app's bookkeeping and deadlocked every retry on "nothing staged". Now the commit is recorded and the row is marked published with a message saying a manual push is needed.
- The page computed `article_status_counts` and never used it: every number came from a list capped at 200 rows, so past 200 proposals the screen would show a subset as if it were everything.
- A row whose status fell outside the group list vanished from the page while still counting toward the total. There is no `CHECK` constraint on `status`, so this was reachable — a catch-all group was added.
- Retry did not clear the previous attempt's results, so a failed retry rendered its new error next to "build passed" from the earlier run.
- A row stuck in `writing` (session killed by the watchdog, or lost to a restart) rendered with no buttons at all. A cancel action, available only in that status, was added; it does not kill the process, and its docstring says so.

**The publish gate — three cases, distinguished by what the card is allowed to claim**: `article_verify_cmd` set and exited zero → publish enabled, shown as verified; set and failed → publish blocked; empty → publish enabled, but card and commit message both say **unverified**. Blocking the third case would make the feature useless in `accounting-ai-agent`, whose markdown blog has no build step at all; claiming a verification that never ran would break the one rule the whole feature is modelled on.

**Acceptance**: [`scripts/smoke_articles.py`](../../scripts/smoke_articles.py) — 25 checks, exit 0, including a real temporary git repository where publishing commits only the draft path, leaves an unrelated working-tree file untouched, and refuses a staged target path. `check_i18n.py`, `check_css_tokens.py`, `smoke_ai_radar.py` all green. Eleven touched pages return 200.

**Deferred**:

- **The end-to-end run against a live project has not happened.** It is the one step in the plan that needs a paid session and a commit into someone else's repository, so it runs under human supervision rather than automatically.
- **The ideas-page button does not dim** once an idea is already proposed — that needs a per-idea status lookup.
- **A disabled project's proposals disappear from the queue** with no on-page notice. The exclusion is intended; the silence is not.
- **`commit_ref` is not displayed** on a published card.
- **No sweep for rows stuck in `writing`** — only the manual cancel button.
- **`can_publish` does not guard `verify_cmd` against `None`** the way it guards `publish_mode`.

**Known defect found along the way (unrelated to this wave)**: `scripts/smoke_node_skills.py` prints its result but **does not exit** — the same class already noted for `smoke_dashboard_tiles.py`: an unclosed async connection holding the event loop. A CI run would hang on it.

## Wave B — Article cross-project

**Branch**: `feature/article-cross-project`, range `cec9010`..`d57cf01` — 15 commits, 12 files, +1307/−57.

**Spec**: [`docs/superpowers/specs/2026-08-20-article-cross-project-design.md`](../superpowers/specs/2026-08-20-article-cross-project-design.md)
**Plan**: [`docs/superpowers/plans/2026-08-20-article-cross-project.md`](../superpowers/plans/2026-08-20-article-cross-project.md)
**Extends**: [Wave A — Article pipeline](#wave-a--article-pipeline)
**Issue**: [#35](https://github.com/micode-ai/ai-dreaming-center/issues/35)

**Goal**: an article about one project can be published on another project's site, a person can state a topic themselves, and the writer can ask a question and wait for the answer instead of guessing.

**Problem**: Wave A's pipeline tied a proposal to a single project — the facts, the write and the publish target were all just `project_id`. That model turned out to be the exception rather than the rule: seven of the eleven managed projects have no blog directory at all, so under Wave A's rule their articles could never be written; and the company landing page already publishes articles *about* the other products (`accounting-ai-agent-architecture`, `ai-budget-assistant-ai-architecture`), evidence sitting in its own blog directory that one repository is routinely the venue for many subjects.

Two capabilities were also missing outright. `source="manual"` existed in the data model with no route that ever produced it, so a person could not simply state a topic. And `write-article.md` already instructed the writer to ask when a fact was unverified, but no channel existed for it to ask anything through — the instruction pointed at infrastructure that had never been built.

**What shipped**:

- A nullable `article_proposals.target_project_id` column plus the per-project `article_venue_project` setting, and the pure `resolve_venue_id(subject_id, override_id, configured_slug, enabled) -> int`: override beats setting beats the subject itself, and a slug naming no enabled project falls back rather than failing.
- `_venue_for()` in `project_articles.py`, rewiring `articles_page`, `articles_approve` and `articles_publish` to read every article setting — writer agent, verify command, publish mode, blog dir, the article root — from the resolved **venue**, while the card, the queue row and the questions stay with the **subject**. The venue is pinned onto the row (`pin_article_proposal_venue`) right after a successful dispatch, so publish reproduces approve's decision instead of re-resolving it and risking drift if the setting changes in between.
- `DC_ARTICLE_SUBJECT_DIR` / `DC_ARTICLE_SUBJECT_SLUG` added to the session environment, and a new section in `write-article.md`: the session's own working directory is the venue (format, build, git repository); the subject directory is read-only material for the piece. The delegation section names the subject explicitly so a delegated subagent isn't left to invent facts it was never pointed at.
- The manual add-article form (`POST /p/{slug}/articles/add`): a topic, an intro prompt and a venue selector, with `source="manual"` and evidence that states the truth — a person asked, and when — rather than fabricating a commit reference. The blank-evidence guard moved from the ingest route into `db.add_article_proposal` itself, so it holds structurally for every feeder, present and future.
- A venue selector on a `proposed` card (`POST /p/{slug}/articles/{id}/venue`), settable only before a writer is dispatched.
- The question channel: `write-article.md` documents `POST /api/questions/create` and polling `GET /api/questions/{id}/poll` against the subject's slug, with an explicit "do not invent the fact" rule on `dismissed` or an unanswered question. The card shows a waiting indicator, linking to `/p/{slug}/questions`, for a `writing` row with a pending question.

**Defects review caught during the wave** (all fixed inside their own tasks):

- A fresh `CREATE TABLE` declared `target_project_id` right after `project_id` (index 2), but the guarded `ALTER TABLE` migration path for an already-existing database can only append columns (index 25 on the live db) — same table, two different physical column orders. Moved to the end of the `CREATE TABLE` list to match what migration always produces, with a permanent smoke check asserting the full column order on a fresh database.
- The same footgun was already sitting there from Wave A: `verify_label`, added by an earlier `ALTER TABLE`, was still declared next to `verify_ok` in the `CREATE TABLE` string instead of at its true post-migration position. Moved and covered by the same column-order assertion.
- `articles_publish` re-resolved the venue from scratch instead of reusing approve's decision, so a row could drift if `article_venue_project` changed between the two steps. A status-guard-free `pin_article_proposal_venue` now records the resolution at approve time, and publish reads the pinned value.
- That pin was first placed *before* the `start_command` call, so a dispatch `start_command` itself refuses (the one-in-flight lock, 409) would still lock in a venue decision for an attempt that never ran. Moved to after a successful dispatch and before `start_article_attempt`.
- The delegation instruction in `write-article.md` never told a delegated subagent about `$DC_ARTICLE_SUBJECT_DIR`, so a cross-project delegate would have invented the facts it was never pointed at.
- The manual-add slug fallback for a topic with no ASCII words was `manual-{timestamp}`. Since users write topics in Russian, the all-Cyrillic path (slugify drops non-ASCII, yielding an empty slug) is the *default* case, not an edge case, and a clock-derived fallback breaks dedup both ways — two different topics in the same UTC second collide, the same topic seconds apart does not. Fixed by hashing the normalized topic text instead.
- The blank-evidence rule lived only at the `/articles/ingest` HTTP boundary, resting on every feeder composing a non-empty string by convention. Promoted into `add_article_proposal` itself so a future feeder inherits the rule structurally.
- The venue `<select>` on the card compared its options against the *resolved* venue slug — which, by `resolve_venue_id`'s own fallback chain, always lands on some real project — making the "project's default" option effectively unreachable and silently pinning an unpinned row on save. Fixed by threading the raw per-row override to the template instead of the resolved value.

- A question's `tool_use_id` was derived from the proposal id, and `create_question` returns the **existing** row for a repeated key without updating its text. So a retry of a failed article would have read the *first* attempt's answer as the answer to its own question — or, if that question had been dismissed, been denied any chance to ask. Fixed by tagging the key with the run.
- The "writer is waiting" indicator was computed once per project and shared by every card, while the questions table serves every session for that project. So a question from an unrelated scan would have made **every** in-progress article claim it was waiting on you. Fixed by scoping the question to the proposal.
**Acceptance**: [`scripts/smoke_articles.py`](../../scripts/smoke_articles.py) — 57 checks, exit 0. `scripts/smoke_ai_radar.py`, `check_i18n.py`, `check_css_tokens.py` all green; `python -c "import dreaming.main"` exits 0. Nine touched pages return 200 via `TestClient`, including `/p/budlog/articles` (the one project deliberately configured with a cross-project `article_venue_project`). The regression that matters most: a proposal with `target_project_id` NULL and no `article_venue_project` set was confirmed, project by project, to resolve its venue to the subject itself and read the subject's own `article_blog_dir` and article root, for all three currently-configured projects (`test`, `accounting-ai-agent`, `ai-budget-assistant`) — reproducing Wave A's behaviour exactly. `budlog`'s deliberately different result (`article_venue_project=test`, resolving to `test`) was confirmed as the intended cross-project demonstration, not a regression.

**Deferred**:

- **The live end-to-end run of writing an article has still never happened, in either wave.** Only the *proposal* half has run for real.
- Rows that were already `drafted` before the venue pin existed keep `target_project_id` NULL and remain exposed to venue drift on a direct publish; they self-heal on any approve retry.
- The center detects a *missing* starter-kit command but has no signal for an *outdated* one, so every project's installed copy silently ages as the templates change — this repository's own `.claude/commands/write-article.md` mirror had drifted from the template (missing the Task 6 question-channel section) and was refreshed as part of this task's verification pass; nothing catches the next drift automatically. **Closed 2026-08-21**: `starter_kit.command_stale` and `status().stale` compare content with line endings normalised (the templates here are CRLF and a checkout elsewhere is routinely LF — without that the signal would cry wolf on every copy), the articles page shows a banner beside the buttons that spend a session, and the rotation page shows one beside its overwrite button. The session is **not** blocked: the first sweep across the fleet showed drift comes in two different kinds — 8 of 11 projects hold a `self-study.md` left 1255 bytes behind (identical md5 across all of them), while `budlog` had deliberately swapped the example agent name for its own. Comparison cannot tell those apart, so the banner says "differs" rather than "outdated" and asks for the diff to be read before overwriting.
- The "two different Cyrillic topics" smoke assertion does not force both posts into the same UTC second, so that direction is a probabilistic rather than airtight pin.
- The 409 detail in the venue route interpolates a status read just before the write, so a very narrow race could name a stale status.
- `smoke_node_skills.py` still never exits — the same unclosed-connection class already noted for `smoke_dashboard_tiles.py` in Wave D1/D2 and left as a known issue at the end of Wave A.

## Wave C — Article committed build output

**Branch**: `feature/article-build-output`, range `cdfb3f9`..`e02fe32` — 4 commits, 5 files, +626/−25. No separate plan document: the wave is a single task, and the spec describes it in full.

**Spec**: [`docs/superpowers/specs/2026-08-21-article-committed-build-output-design.md`](../superpowers/specs/2026-08-21-article-committed-build-output-design.md)
**Extends**: [Wave A — Article pipeline](#wave-a--article-pipeline), [Wave B — Article cross-project](#wave-b--article-cross-project)
**Issue**: [#36](https://github.com/micode-ai/ai-dreaming-center/issues/36)

**Goal**: publishing must reach the live site on the project that commits its built site, not only its sources.

**Problem**: waves A and B committed exactly the paths the writer reported. That is right for two projects out of three — `mi-code-ai` and `accounting-ai-agent` commit sources and let CI build. The third works differently, and it is the one the user tried first: `ai-budget-assistant` tracks 208 files of generated site under `docs/marketing/seo/site/blog`, and `web-deploy.yml` copies precisely that directory to the server — "Committed builds (regenerate then commit)" is written in the workflow itself. The first live run proved it: the writer produced a correct 10 KB Polish article with frontmatter matching its 21 siblings, and there was no path from that file to `ai-budget.pl/blog`.

**Rejected design**: "publish runs the build." `build_blog.py` renders every language, generates OG images with PIL and rebuilds the sitemap — minutes inside a POST from a hand-pressed button. The build already has a lawful home: the verify command, which the session runs, not a web request. For this project the build *is* the verification in the strongest sense — it proves the article rendered into the directory the deploy will carry.

**What landed**: one venue setting, `article_publish_extra_paths` — comma- or newline-separated paths relative to the article root, staged alongside `draft_ref`. Empty means wave A/B behaviour byte for byte, so nothing changes for the other two projects.

The asymmetry is the point, not an oversight: these paths **may** name a directory and `draft_ref` may not. `draft_ref` arrives from a Claude session over unauthenticated localhost HTTP, and a directory there would let one report stage a whole subtree. `article_publish_extra_paths` is typed by a human into project settings, and a build output *is* a 208-file subtree. Everything else — refusing `..`, absolute paths and glob characters, the containment check, `--literal-pathspecs`, never passing `-f` — applies to both identically.

**Defects review caught during the wave** (all fixed inside their own tasks):

- The spec's risk table closed the "build output is gitignored" case with "`git add` without `-f` refuses it, and the publish fails with git's own message." Formally true — and dangerous for that reason: it described the outcome but not the state left behind. `git add` is not atomic across paths: having refused the ignored one it still stages the rest — so the article's file stayed in **someone else's** repository index, and a human would have had to clean up after us. Fixed with a shared `_rollback_or_raise` covering both `git add` calls and `git commit`, checking the rollback's own exit code and saying honestly what remains.
- A directory carrying a nested `.git` (a vendored repository inside the build output) would have been staged as a dangling gitlink — a commit referencing an object the repository does not contain. The refusal moved into validation, before any git call.

**Acceptance**: [`scripts/smoke_articles.py`](../../scripts/smoke_articles.py) — 90 assertions, exit 0. `scripts/smoke_ai_radar.py`, `check_i18n.py`, `check_css_tokens.py` all green; `python -c "import dreaming.main"` exits 0. Verified in throwaway repositories, separately from the implementer's own run: the build tree is committed together with the article; an unrelated file a human had staged stays **out** of the commit and stays staged; `draft_ref` still refuses a directory while a configured path accepts one; and every refusal — ignored output, nested `.git`, `..`, absolute path, glob, missing path — leaves the index byte-identical to what it was.

**What the first live publish taught** (article 22 in `ai-budget-assistant`, 2026-08-22):

- Wave C made a build output committable, but could not know the project has **two** generators. The apex `sitemap.xml` — the one `ai-budget.pl` actually serves — is emitted by `build_landing.py` reading the blog's sitemap, and `web-deploy.yml` regenerates nothing; it assembles committed output. The configured `article_verify_cmd` ran only `build_blog.py`, so the article went live and reachable (22 sibling pages link to it, IndexNow pinged every changed page) while the sitemap never listed it. Fixed: the verify command now chains both generators with `&&`, and `article_publish_extra_paths` names both trees. The rule is recorded beside `article_verify_cmd` in [`config.py`](../../dreaming/config.py) — verify must regenerate everything the deploy ships, not just the part nearest the article.
- That second tree was unreachable for a second reason: the project's `.gitignore` excluded the landing directory via `docs/marketing/*`, and publishing never passes `-f` by design. So `git add` would have been refused, wave C would have rolled back and said so honestly — and publishing would still have been impossible. Only the project itself can fix that: a `!docs/marketing/landing/` negation, twin to the one already there for `seo/`.
- `meta_description` ran past 155 characters in pl (160) and fr (161). Not this article's fault: 15 of 22 topics overflow in at least one language, and the generator never checked. `build_blog.py` now warns — deliberately non-fatal, since a hard failure would break the build on 30 legacy overflows that a new article's author cannot fix.
- Incidentally, this project's build output depends on the source's **commit date** (`dateModified` comes from git), so one build-then-commit pass cannot be self-consistent: only a build after the commit stamps the right date. For the pipeline that means a perfectly clean tree after publishing is not something to expect.

**Deferred**:

- `article_publish_mode` for `ai-budget-assistant` is set to `commit`, one notch below the user's chosen `commit+push`: a first live commit touching a 208-file directory deserves human eyes before a push. That is my call, not the user's.
- **A live end-to-end — write, publish, appear on the site — has still never happened in any wave.**
- A huge accidental path (`.`) in the setting passes containment and existence and will commit the working tree. Mitigated only by it being an operator setting shown back on the settings page — the same trust level as `article_publish_mode`.
- The starter-kit installer cannot target an article root inside a nested repository (worked around by hand for `mi-code-ai`). That gap belongs to the installer, not to publishing.

## Not implemented yet

As of `wave-3-full` (last commit `b49aafd`) the deferred list is:

- **Real TTS backfill** (`tts_backfill.backfill_tts` — stub returns 0).
- **Full AskUserQuestion plumbing** — the `orchestrator_questions` table already exists, but API endpoints for create / answer aren't added yet. ProcessManager watchdog already accounts for a pending question ([`process_manager.py:561`](../../dreaming/services/process_manager.py)).
- **codex / continue runners** — the `orchestration_local_runner` config exists but the code only paths claude.
- **work_routing_mode** — the setting exists, unused in code.
- **Real harness integration via UI** — the `HarnessClient` service is ready, but `/p/{slug}/orchestration/start` doesn't call it (uses local claude). Wiring possible via changing `start_command` and checking `await harness_clients.get_for_project(...)`.
- **Smoke tests for Wave 3+** — separate smoke scenarios exist, but no end-to-end orchestration smoke is written.

## Cross-references

- Where each piece of code lives — [`services.md`](services.md), [`routes.md`](routes.md).
- Which settings are active per wave — [`configuration.md`](configuration.md).
- Architecture — [`architecture.md`](architecture.md).
