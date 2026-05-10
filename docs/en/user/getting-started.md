# First launch in 15–20 minutes

Step-by-step — from an empty machine to your first running self-study session. If something goes wrong — check the troubleshooting section at the end.

## Contents

- [Prerequisites](#prerequisites)
- [Step 1. Install](#step-1-install-3-5-minutes)
- [Step 2. Start the server](#step-2-start-the-server-1-minute)
- [Step 3. Setup wizard](#step-3-setup-wizard-3-5-minutes)
- [Step 4. Verify](#step-4-verify-1-minute)
- [Step 5. First session](#step-5-first-session-3-5-minutes)
- [Next steps](#next-steps)
- [Troubleshooting](#troubleshooting)

## Prerequisites

- Python 3.10+ installed (verify: `python --version`).
- `claude` CLI installed and on `PATH` (verify: `claude --version`). On Windows it must be `claude.cmd`, on macOS/Linux — the regular `claude`.
- At least one folder of projects under `projects_root`. For most people this is `D:\Work\micode\` or `~/Projects/` — individual repositories live inside, ideally with `.claude/agents/` for self-study.

## Step 1. Install (3–5 minutes)

Open a terminal and run (PowerShell/bash, doesn't matter):

1. Clone the repository:
   ```
   git clone <repo-url>
   cd ai-dreaming-center
   ```
2. Create and activate a venv:
   ```
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1     # PowerShell
   source .venv/Scripts/activate    # bash
   ```
3. Install the package in editable mode:
   ```
   pip install -e .
   ```
   At this step pip pulls FastAPI, Uvicorn, APScheduler, aiosqlite, sse-starlette, jinja2, pydantic-settings, httpx and pyyaml. Takes 1–2 minutes.

## Step 2. Start the server (1 minute)

```
python -m uvicorn dreaming.main:app --port 8086
```

In the console you'll see Uvicorn logs: `INFO: Started server process`, `INFO: Application startup complete.` — the server is alive.

On first launch `config.yaml` does not yet exist — middleware redirects every request to `/setup`.

Open `http://localhost:8086` in the browser. You will be redirected to `http://localhost:8086/setup`.

## Step 3. Setup wizard (3–5 minutes)

On the `/setup` page you'll see the heading "Первичная настройка" (First-time setup) and a form of two blocks:

**Block 1 — "Глобальные настройки" (Global settings)** with three fields:
- `claude_path` — path to the Claude CLI. Default is `"claude"`. If yours lives in a non-standard location — type the absolute path, e.g. `C:\Users\me\AppData\Roaming\npm\claude.cmd`.
- `projects_root` — root directory where DC will look for your projects. Default is empty. Put an absolute path, e.g. `D:\Work\micode`.
- `default_locale` — UI language. Pick `Русский` or `English` from the dropdown.

**Block 2 only appears after scanning.** At the bottom of the form there is a blue button `Просканировать projects_root` (Scan projects_root). Click it.

The page reloads. If `projects_root` has subfolders — you'll see a table titled "Найденные проекты в {path}" (Projects found in {path}) with columns:
- `включить` (enable) — checkbox (checked by default only if the folder has `.claude/`).
- `по умолч.` (default) — radio button (pick the project that will be the default).
- `slug` — short name (editable).
- `label` — human-readable name.
- `путь` (path) — absolute path, readonly.
- `.claude` — checkmark `✓` if `.claude/` exists in the project.

Below the table: "X проектов найдено. Включённые — будут импортированы." (X projects found. The enabled ones will be imported.)

Do this:
1. Untick the checkboxes for projects you don't need right now (you can import them later via `/projects`).
2. Pick one default radio button — that project will open by default when you visit `/p/`. (You can leave the first one.)
3. Click the blue `Сохранить и импортировать` (Save and import).

After the click the page disappears and you land on `/`.

If the scan returns a red banner `Ошибка: ...` (Error: ...) — the path doesn't exist or you don't have permissions. Check that `projects_root` points to an existing directory.

## Step 4. Verify (1 minute)

On `/` you should see:
- The "AI Dreaming Center" heading + a "N active projects" line.
- Six top-line metrics: Успешные / Сбой / Таймаут (Success / Failed / Timeout, weekly), running now, Тех-долг (Tech-debt), Идеи продукта (Product ideas). All zeros.
- Project cards (one per imported project) with link buttons to `/p/{slug}/`.
- On the right: an "Активные сессии" (Active sessions) sidebar — empty.

Click any card → you land on `/p/{slug}/`.

The header should carry a `<select>` with all projects and an `EN/RU` button on the right.

## Step 5. First session (3–5 minutes)

1. On the project page switch to the `Ротация` (Rotation) tab.
2. If `.claude/agents/` has md files — you'll see a table: agent / tier / enabled / last_studied / `Start session` button. At the top a line like "N agents in DB; M on disk in {working_dir}/.claude/agents/".
3. If the table is empty ("0 agents in DB; 0 on disk") — the project has no agents yet. Create at least one `.claude/agents/test.md` (e.g. `# Test agent\nI just read files.`) and refresh the page.
4. Click the blue `Start session` next to any agent.
5. You get redirected to `/p/{slug}/live`. There you'll see a black pre-block streaming claude's stdout.
6. After a few seconds–minutes (depending on the model and the agent) the stream ends with `[stream ended]`. That means the session is done.

Go back to `/p/{slug}/` — a record should appear in "Последние сессии" (Recent sessions) with status `success` (or `failed` / `timeout` if something went wrong).

If the status is `success` and the note has a `note_path` — go to `Конспекты` (Notes), click the file, read it.

## Next steps

- [`features/rotation.md`](features/rotation.md) — more on the rotation table.
- [`features/self-study.md`](features/self-study.md) — what self-study actually does.
- [`workflows/nightly-cron.md`](workflows/nightly-cron.md) — how to configure the nightly schedule.
- [`workflows/onboarding.md`](workflows/onboarding.md) — extended step-by-step walkthrough of every feature.
- [`features/settings.md`](features/settings.md) — settings in 13 groups.

## Troubleshooting

**`claude` CLI not found** — uvicorn logs `FileNotFoundError`. Check `claude --version` in the same shell session. If it works there — set the absolute path in `claude_path` via `/settings` or the env var `DC_CLAUDE_PATH`.

**Port busy** — uvicorn dies with `Address already in use`. Run on another port: `python -m uvicorn dreaming.main:app --port 8087` (and don't forget to update `port` in Settings if you send callbacks from claude back into DC).

**The setup wizard says `Ошибка: ... not found`** — `projects_root` points to a folder that doesn't exist. Create it (`mkdir D:\Work\micode`) or pick another path.

**The scanner found no projects** — `projects_root` has no subfolders. Create at least one, drop a `.git/` or `.claude/agents/` (these are detection markers) inside, rescan.

**The first session is `failed` with `error_message`** — open `/p/{slug}/live`, scroll down — you'll see stderr or the last stdout lines. Often the cause is Claude not understanding the prompt (agent file empty or broken) or a missing API key.

**Session stuck in `running` status but `/live` is empty** — the Claude process was killed by the OS but the DB row got stuck. After 5 minutes the reconcile job will close it. You can wait or manually `/projects/{id}/toggle` (disable+enable) to reset.
