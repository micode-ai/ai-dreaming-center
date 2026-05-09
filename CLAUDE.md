# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project purpose

Multi-project FastAPI dashboard that orchestrates Claude CLI sessions per micode project. The container repo is at `D:\Work\micode\ai-dreaming-center\`. Per-project work happens via `working_dir` from each row of the `projects` table — the agents live in their respective project's `.claude/agents/` folder, NOT in this repo.

## Development commands

```bash
pip install -e .
python -m uvicorn dreaming.main:app --port 8086 --reload
```

No test suite, linter, or formatter is configured (per design — inherited from ALC). Smoke checks live in `scripts/smoke_*.py` and are run manually after each wave.

## Architecture

Singletons live on `app.state` and are created in the lifespan: `db: SqliteDB`, `projects: ProjectsService`, `templates: Jinja2Templates`, `i18n: I18n`, `process_manager: ProcessManager`, `orchestration_hub: OrchestrationHub` (stub Wave 0; real in Wave 3), `scheduler: AsyncIOScheduler`, `resolver_factory: get_resolver`.

Routes always read `request.state.project` (set by `project_resolver_middleware` for `/p/{slug}/...` paths) instead of querying by slug themselves.

## Reserved URL paths

`/docs`, `/redoc`, `/openapi.json` — FastAPI auto-registers these. Do not override.

## Per-project key resolution

Use `ConfigResolver.get(project, key, default)` for any value that may be overridden per-project. Settings UI persists overrides into `project_settings (project_id, key, value)` as JSON-encoded scalars.

## Adding a scheduled job

Add a new entry to `_PER_PROJECT_JOBS` in `dreaming/services/scheduler.py`. Register/unregister hooks fire on project toggle/delete/import via `dreaming/routes/projects.py` and `dreaming/routes/setup.py`.

## Spec & wave plans

- Spec: `docs/superpowers/specs/2026-05-09-ai-dreaming-center-design.md`
- Wave plans: `docs/superpowers/plans/2026-05-09-wave-{N}-*.md`

Each wave produces a git tag (`wave-0`, `wave-1`, `wave-2`, `wave-2.5`, `wave-5`).

## Conventions

- User-facing strings in templates use `{{ "key" | t(locale=locale) }}`. RU is the default; EN keys must mirror RU keys (verified by `scripts/check_i18n.py`).
- New JSON files / templates with Cyrillic content MUST be written via the Write/Edit tool (UTF-8). PowerShell `Set-Content` defaults to UTF-16 LE and breaks the parser.
- Modern Starlette TemplateResponse: `templates.TemplateResponse(request, "name.html", {ctx_keys_without_request})`.
