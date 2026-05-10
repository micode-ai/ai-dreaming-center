# First day: extended onboarding

Step-by-step from `git clone` to a configured nightly schedule. An extension of [`getting-started.md`](../getting-started.md) with extra detail on preparing a project for DC.

## Contents

- [Day 0: prerequisites](#day-0-prerequisites)
- [Install Claude CLI](#install-claude-cli)
- [Set up `.claude/agents/` in the project](#set-up-claudeagents-in-the-project)
- [Install DC](#install-dc)
- [First session](#first-session)
- [First custom topic](#first-custom-topic)
- [First JSONL via AI Usage](#first-jsonl-via-ai-usage)
- [Day 2: enable weekly scanners](#day-2-enable-weekly-scanners)

## Day 0: prerequisites

You need:
- Python 3.10+.
- Git.
- At least one project on the machine (a repository you'll want to use with DC).
- An Anthropic API key or an active Claude Pro/Team plan.
- Preferably — Obsidian to read the notes nicely rendered.

## Install Claude CLI

DC spawns the `claude` CLI as a subprocess. Without it nothing works.

**On Windows:**
1. Install Node.js (if not already): https://nodejs.org/
2. `npm install -g @anthropic-ai/claude-code` — global install.
3. Verify: `claude --version` in PowerShell. The version should print.
4. On Windows shutil.which finds `claude.cmd` (not the bare `claude`, which is a bash script). DC handles this.

**On macOS:**
1. `brew install claude` or via npm.
2. Verify `claude --version`.

**On Linux:**
1. Via npm or your distro's package manager.

After install — sign in: `claude` (no arguments) opens a browser for login. Or set the API key: `claude config set apiKey <your-key>`.

All this must be done **before** the first DC start, otherwise sessions will fail with auth-error.

## Set up `.claude/agents/` in the project

DC expects your project to have a `.claude/agents/` folder with agent md files. If you don't have any — create at least one.

Minimum example:

1. `cd D:\Work\micode\my-app`
2. `mkdir .claude\agents`
3. Create the file `.claude/agents/test-agent.md` with:
   ```
   ---
   name: test-agent
   description: Test agent to verify DC.
   ---

   # Test agent

   I just read project files and write a summary into `learning-notes/`.

   ## Task

   1. Read README.md and pyproject.toml (or package.json).
   2. Write a summary note into `.claude/agents/learning-notes/{date}-test-agent.md`.
   3. Finish.
   ```

That's a minimal agent. Real agents will be more structured — see agent-team-starter-kit.

If you have the starter kit:
```
git clone https://github.com/RsCloud2022/agent-team-starter-kit.git temp-kit
xcopy /E /Y temp-kit\.claude D:\Work\micode\my-app\.claude
rmdir /S /Q temp-kit
```

That gives you a ready-made set: roman, vera, svetlana, silent-failure-hunter, and slash commands (`/self-study`, `/wiki-bootstrap`, etc.).

## Install DC

Now — DC.

1. `git clone <repo-url> ai-dreaming-center`
2. `cd ai-dreaming-center`
3. `python -m venv .venv`
4. `.\.venv\Scripts\Activate.ps1` (PowerShell) or `source .venv/Scripts/activate` (bash)
5. `pip install -e .`
6. `python -m uvicorn dreaming.main:app --port 8086`

Open http://localhost:8086 — you'll land on `/setup`.

In the setup wizard:
- `claude_path` — keep `claude` (DC picks up `.cmd` on Windows).
- `projects_root` — type `D:\Work\micode` (or wherever your projects are).
- `default_locale` — pick Russian or English.
- Click "Просканировать projects_root" (Scan projects_root).
- In the table you'll see `my-app` (`✓` in the `.claude` column if you created agents above).
- Untick projects you don't need now.
- Pick a default radio for one project.
- Click "Сохранить и импортировать" (Save and import).

Done, DC is configured.

## First session

1. On `/` you'll see the project card.
2. Click → you land on `/p/my-app/`.
3. Switch to the `Ротация` (Rotation) tab.
4. You'll see `test-agent` (or roman/vera/svetlana/etc if starter kit) with tier P2, enabled ✓, last_studied —.
5. Click the blue `Start session`.
6. You're redirected to `/p/my-app/live`. You see Claude come up:
   - JSONL `session_start` event.
   - Reads README.md, package.json, etc.
   - Writes the note.
   - Final `result` event.
7. After a few minutes — `[stream ended]`. The session ended.
8. Go back to `/p/my-app/` — a `success` row should appear in recent sessions.
9. Visit `/p/my-app/notes` — you'll see the note that was written.

## First custom topic

Suppose you want the agent to study something specific next time.

1. Open `/p/my-app/kanban`.
2. In the form on top:
   - Title: "What does function X in module Y do?"
   - Module: leave empty (or type `auth`).
   - Agents: leave empty (= everyone).
   - What specifically: "How does `auth.login()` handle 2FA? What edge cases?"
   - Why important: "We're refactoring auth-flow in 2 weeks."
3. Click `Добавить` (Add).

The topic appears in the table. Next time the agent goes into self-study — this topic is included in its prompt.

## First JSONL via AI Usage

After a couple of sessions go to `/p/my-app/ai-usage`. It may be empty right away — the ai_usage_ingest cron runs every 5 minutes.

Wait 5–10 minutes, refresh:
- Top cards: `Last 7d input/output/cache` — populated.
- The `By model` table — one row with `claude-sonnet-4-5` (or whichever model you use).

If after 15 minutes everything is empty — open `/ai-usage` (global). If empty too:
1. Check `~/.claude/projects/` exists and has JSONLs.
2. Check `claude_projects_dir` in `/settings` (default = `~/.claude/projects/`).
3. Restart uvicorn — the ingest job runs on startup.

If global has data but per-project is empty — mapping issue (`cwd` in JSONL doesn't match `working_dir` in the registry). See [`../features/ai-usage.md`](../features/ai-usage.md).

## Day 2: enable weekly scanners

After the first day of getting acquainted, you can plug in "helpers".

1. **Tech-debt scanner**: on `/p/my-app/settings` find `weekly_tech_debt_scan_enabled` → Override → checkbox true → Save. Also make sure `tech_debt_dir` is set (e.g. `D:\Work\micode\my-app\docs\tech-debt\`). Create the folder if missing.

2. **Product ideas scanner**: same for `weekly_product_ideas_scan_enabled` and `product_ideas_dir`.

3. **Wiki linter**: same for `weekly_wiki_lint_enabled` and `wiki_dir`.

After Save the scheduler re-registers the cron jobs (on the next tick, typically immediately). At cron-expression time (default `0 4 * * 0` — Sunday 4am) the scanner runs. After a week, on `/findings` and `/ideas` you'll see artifacts.

If you want sooner — go to `/p/my-app/wiki` and click `Run /wiki-bootstrap`. That runs Claude now (off-cron).

More: [`weekly-scanners.md`](weekly-scanners.md).

---

See also:
- [`daily.md`](daily.md) — a typical day after onboarding.
- [`new-project.md`](new-project.md) — add a second project.
- [`jira-integration.md`](jira-integration.md) — Jira setup.
- [`nightly-cron.md`](nightly-cron.md) — nightly in detail.
- [`../features/`](../features/) — feature guides.
