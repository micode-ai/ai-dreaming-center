# Add a new project to a running instance

Suppose DC is already installed and running. You already have N projects in the registry. Now you've created a new repo and want to plug it in.

## Contents

- [Step 1. Prepare the project on disk](#step-1-prepare-the-project-on-disk)
- [Step 2. Import via `/projects`](#step-2-import-via-projects)
- [Step 3. Per-project settings (optional)](#step-3-per-project-settings-optional)
- [Step 4. Verify cron jobs](#step-4-verify-cron-jobs)
- [Step 5. First session](#step-5-first-session)
- [Removal if something went wrong](#removal-if-something-went-wrong)

## Step 1. Prepare the project on disk

DC expects the new project to be a folder under `projects_root`. Example: `projects_root = D:\Work\micode\`, new project = `D:\Work\micode\my-new-project\`.

Minimum for detection:
1. The folder exists.
2. (Preferably) `.git/` inside — DC uses that as a project marker.
3. (Preferably for self-study) `.claude/agents/` with at least one md file.

If you have only a git-inited repo without agents — DC still detects it, but Rotation will be empty until you drop md files.

You can copy the starter kit:
```
git clone https://github.com/RsCloud2022/agent-team-starter-kit.git temp-kit
xcopy /E /Y temp-kit\.claude D:\Work\micode\my-new-project\.claude
rmdir /S /Q temp-kit
```

## Step 2. Import via `/projects`

The DC server is already running (uvicorn is up).

1. Open http://localhost:8086/projects (or attach to the running instance).
2. Scroll down to the "Импорт из projects_root" (Import from projects_root) block.
3. The input shows the current `projects_root` (e.g. `D:\Work\micode`). You can keep it — or override for a one-off scan (if the new project is somewhere else).
4. Click the blue `Просканировать и импортировать новые` (Scan and import new) button.

DC scans the given path. Already-registered projects (matched by `working_dir`) are skipped. New ones are added:
- slug = lowercase(folder name), `_` replaced with `-`.
- label = folder name as-is (with first letter capitalised).
- working_dir = absolute path.
- enabled = true.
- is_default = false.

After the redirect to `/projects` you'll see a new row in the table.

Done — the project is imported. Cron jobs were registered automatically (`nightly_learning_{slug}` will fire at cron_expression tonight).

## Step 3. Per-project settings (optional)

If the new project needs settings different from global:

1. Open `/p/{slug}/settings`.
2. Find the key you want to override. Often:
   - `tech_debt_dir`, `product_ideas_dir`, `wiki_dir` — paths specific to this project.
   - `cron_expression` — if this project should learn at a different time.
   - `agents_per_night` — if this project has many agents and you want more per night.
   - `jira_project_key` — if a different Jira project.
3. Click the `Override` radio, type the value in the field, click Save.

Changes persist in the `project_settings` table, take effect immediately. No restart needed.

## Step 4. Verify cron jobs

You want to confirm the nightly cron is really registered.

There is no "list of cron jobs" page in the UI yet (TODO for future waves). Indirect ways:
- Restart uvicorn in noisy mode (`--log-level debug`) — APScheduler will log: "Adding job nightly_learning_my-new-project trigger=cron(0 3 * * *) ...".
- In `data/dreaming.db-jobs` (or the bundled APScheduler jobstore — path depends on configuration) you can inspect jobs via SQL.
- Easier: wait for cron-expression. If at 3:00am a session starts for the new project — it works.

If cron didn't auto-register — restarting DC usually resolves it: lifespan rescans the projects table and registers jobs.

## Step 5. First session

To confirm end-to-end without waiting overnight:

1. Open `/p/{slug}/rotation`.
2. If there are md files in `.claude/agents/` — you'll see the table. If not — create at least one and refresh.
3. Click `Start session` next to any agent.
4. You'll be redirected to `/p/{slug}/live`. Watch the session run.
5. After completion — on the dashboard `/p/{slug}/` you'll see one record.

Done. The project is wired up, cron works, manual launch works.

## Removal if something went wrong

If you imported by mistake (wrong folder, wrong slug):

1. On `/projects` find the row.
2. Click the red `Delete`.
3. The JS prompt asks for the slug — type it exactly as in the column.
4. The row is removed, cron jobs unregister.

If you only want to rename the slug — delete and re-import. The UI doesn't support slug editing.

If you want to disable temporarily (without losing history):
- The `Disable` button next to `Delete`. Cron jobs unregister, but the data is preserved. `Enable` again — everything comes back.

---

See also:
- [`onboarding.md`](onboarding.md) — first launch with the setup wizard.
- [`../features/projects.md`](../features/projects.md) — registry management.
- [`nightly-cron.md`](nightly-cron.md) — configuring the nightly schedule.
- [`../features/settings.md`](../features/settings.md) — where to change settings.
