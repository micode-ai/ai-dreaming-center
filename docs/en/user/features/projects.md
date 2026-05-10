# Project management

The project registry is a table of every directory registered in DC. Each entry = one project with a unique slug, label, working dir, and flags.

## Contents

- [What the registry is](#what-the-registry-is)
- [The `/projects` page](#the-projects-page)
- [Importing from projects_root](#importing-from-projects_root)
- [Toggle Disable / Enable](#toggle-disable--enable)
- [Delete (with confirmation)](#delete-with-confirmation)
- [Default project](#default-project)
- [Changing slug / label](#changing-slug--label)

## What the registry is

DC keeps the project list in the SQLite table `projects`. Each row:
- `slug` — short unique name (`my-app`, `wishlist`).
- `label` — human-readable name (visible in the header).
- `working_dir` — absolute path to the project folder on disk.
- `enabled` — boolean: whether to show in the dropdown and register cron jobs.
- `is_default` — boolean: one project may be the default.

DC scans the subfolders of `projects_root` itself and does nothing automatically: you explicitly pick which folders to register, via the setup wizard or via `/projects`.

## The `/projects` page

Open `http://localhost:8086/projects`. You'll see:

- Heading "Проекты" (Projects).
- If the registry is non-empty — a table with columns: `slug`, `label`, `working_dir` (small font), `enabled` (`✓` or `—`), `default` (`★` or empty), and the `Disable`/`Enable` and `Delete` buttons on the right.
- If the registry is empty — the text "Нет зарегистрированных проектов" (No registered projects) and a `→ /setup` link.
- Below — an "Импорт из projects_root" (Import from projects_root) block with an input and a `Просканировать и импортировать новые` (Scan and import new) button.

## Importing from projects_root

Useful when: adding new projects to a running instance without recreating the registry.

Steps:
1. On `/projects` scroll down to the "Импорт из projects_root" block.
2. The input shows the current `projects_root` from settings. Keep or change (for a one-off scan).
3. Click the blue `Просканировать и импортировать новые` button.
4. DC scans the given path, filters out already-registered ones (by `working_dir`), and imports all new ones with `enabled=true`, `is_default=false`. The slug is auto-generated from the folder name (lowercase, `_` replaced with `-`).
5. You're redirected back to `/projects` with the updated table.

If `projects_root` has no new projects — the table is unchanged.

## Toggle Disable / Enable

The `Disable` (or `Enable` if already disabled) button — POST to `/projects/{id}/toggle`.

What happens on Disable:
- In the DB `enabled=false`.
- The scheduler auto-unregisters every cron job of this project (`nightly_learning_{slug}`, `weekly_*_{slug}`).
- The project disappears from the header dropdown (but stays in the `/projects` table).
- All its metrics on the aggregated `/` dashboard stop counting.
- Sessions and runs in the DB are not deleted.

Enable — the reverse: cron jobs are re-created, the project comes back to the dropdown.

Use disable when:
- You temporarily don't want crons to run for the project.
- You don't want to see it in the UI right now.
- You want to "archive" without losing history.

## Delete (with confirmation)

The `Delete` button (red) — POST to `/projects/{id}/delete` with a guard: a JS prompt asks "Введите slug `{slug}` чтобы удалить:" (Enter slug `{slug}` to delete:). You must type it exactly as in the slug column, otherwise the POST is not sent.

What happens on Delete:
- All rows in `agent_learning_sessions`, `agent_learning_rotation`, `custom_topics`, `orchestrator_runs`, `orchestrator_nodes`, `orchestrator_messages`, `ai_usage_events`, `project_settings` for this `project_id` are cascade-deleted via ON DELETE CASCADE FK.
- Markdown artifacts on disk (`.claude/agents/`, `tech_debt_dir`, `product_ideas_dir`, notes, wiki) are **not removed** — DC doesn't manage filesystem objects of the project.
- Cron jobs are unregistered.
- The row in `projects` is gone.

Use delete when:
- The project is completely no longer needed.
- The slug needs to change (delete and re-import).

**Warning:** delete is irreversible for DB data. If in doubt — `Disable` first.

## Default project

The default is one project with `is_default=true`. Picked in the setup wizard (the radio button in the "default" column). You can't switch the default via UI after setup — you have to edit the DB directly.

What default means:
- On `/` (root), if there is a default — DC shows the aggregated dashboard anyway (default is only used in a few routes for hints).
- You can live without a default — the UI still works.

## Changing slug / label

Via UI — **not possible**. The UI has no edit form for project rows. If you need to change a slug:

1. Stop DC (uvicorn Ctrl+C).
2. Open `data/dreaming.db` in a SQLite client (DB Browser, sqlite3 CLI).
3. Run:
   ```
   UPDATE projects SET slug='new-slug' WHERE slug='old-slug';
   ```
4. Start DC again.

Note: if you have customised cron expressions or artifacts whose paths contain the slug — don't forget to update those too. Often it's easier to delete and re-create.

If you only want to change the label:
```
UPDATE projects SET label='New Label' WHERE slug='my-app';
```

---

See also:
- [`../workflows/new-project.md`](../workflows/new-project.md) — step-by-step add a new project.
- [`../workflows/onboarding.md`](../workflows/onboarding.md) — first launch with the setup wizard.
- Technical details — [`../../features/multi-project.md`](../../features/multi-project.md) and [`../../schema.md`](../../schema.md).
