# Tech debt

Two pages about technical debt:
- **Findings** (`/p/{slug}/findings`) — flat list of every tech-debt item with close/delete operations.
- **Tech-Debt** (`/p/{slug}/tech-debt`) — aggregate: total, by_status, top modules.

## Contents

- [Where items come from](#where-items-come-from)
- [Findings: flat list](#findings-flat-list)
- [Detail: a single note](#detail-a-single-note)
- [Close](#close)
- [Delete](#delete)
- [Tech-Debt: aggregate](#tech-debt-aggregate)
- [If the directory is not configured](#if-the-directory-is-not-configured)

## Where items come from

Tech-debt items are markdown files in the `tech_debt_dir` directory (configured in settings, no default — you have to set it). Files are created by the `weekly_tech_debt_scan_{slug}` cron agent (off by default).

A file's structure:
```
---
id: TD-2026-05-001
title: "auth/login has 3 different code paths"
status: open
priority: high
module: auth
created_at: 2026-05-01
---

# TD-2026-05-001 — auth/login has 3 different code paths

Description...

## Symptoms
- ...

## Proposal
- ...
```

Frontmatter is required. DC reads the fields: `id`, `title`, `status`, `priority`, `module`. Body — free-form markdown.

`status` — usually `open` / `in-progress` / `closed`. The UI accepts any string, there's no filter.

## Findings: flat list

Open `/p/{slug}/findings`.

If `tech_debt_dir` is not configured — an amber banner "Каталог tech-debt не настроен" (Tech-debt directory not configured) with a settings link. If configured but absent — grey text "Каталог `{td_dir}` не существует." (Directory `{td_dir}` does not exist.) If there is a md parsing error — a red banner with the error message.

If all is well — you'll see:
- At the top a line "N items in `{td_dir}`".
- A table with columns: `id`, `title`, `status`, `priority`, `module`, and `close`/`delete` buttons in the last column.
- The ID in the first column is clickable, leading to the detail page.

The status badge is monospace, neutral colour (no colour scale).

If items > 50–100 — the table gets long, you scroll manually. No pagination yet.

## Detail: a single note

Clicking the ID in the `id` column leads to `/p/{slug}/findings/{id}`.

You'll see:
- Breadcrumbs: link `← к findings` (← back to findings).
- Heading (`title` from frontmatter).
- Metadata (status, priority, module, date).
- Body markdown — rendered to HTML (for readability).
- `close` and `delete` buttons (mirroring the list actions).

If the file was deleted from disk between list load and click — 404.

## Close

The `close` button (only for items with `status != 'closed'`):
- POST to `/p/{slug}/findings/{id}/close`.
- DC rewrites the frontmatter: changes `status: open` → `status: closed`.
- The file stays on disk.
- The item stays in the table, but the `close` button is no longer shown.

Smart move: close = soft-delete. The history stays in git, you can come back, you can reopen manually (by editing the file).

If the frontmatter has no `status` field — DC adds one.

## Delete

The `delete` button (red):
- JS-confirm: "Удалить {id}?" (Delete {id}?). You hit OK.
- POST to `/p/{slug}/findings/{id}/delete`.
- DC removes the file from disk (`os.unlink`).
- Redirects back to `/findings`.

Permanently deleted. If the repo is under git — restore via `git restore <path>`.

Use when:
- The item was a mistake / duplicate.
- The item is no longer relevant and you don't need any history.

In most cases prefer close.

## Tech-Debt: aggregate

Open `/p/{slug}/tech-debt`. This is statistics, not editing.

If `tech_debt_dir` is not configured / does not exist / parser-error — same warnings as in findings.

If OK — you'll see:
- Two cards on top: "Всего" (Total) (big number) and "По статусу" (By status) (status → count list).
- Heading "Top modules".
- A table of the top-10 modules by item count: `module` / `count`.
- At the bottom — "Источник: `{td_dir}` · полный список: findings" (Source: `{td_dir}` · full list: findings).

Use for:
- Quick check: how much debt has piled up?
- Where is it bad? Which module is top-1 by items?
- Progress: how many closed vs open?

## If the directory is not configured

By default `tech_debt_dir` is empty. To set it:
1. Open `/p/{slug}/settings`.
2. In the "Paths" group (or where tech_debt_dir is) pick `Override` and type the absolute path, e.g. `D:\Work\micode\my-app\docs\tech-debt\`.
3. Save.

The directory must exist. DC does not create it — make it manually or let the scanner create it.

After configuring and the first weekly scan — items appear on `/findings`.

## Column filters

A filter row sits under the table headers, one per column:

| Column | Filter type |
|---|---|
| id, title, module, complexity, autonomy, confidence | substring search |
| status | dropdown (all / open / in-progress / blocked / closed / dropped) |
| priority | dropdown (all / critical / high / medium / low) |
| created | date substring (`YYYY-MM-DD` — type `2026-05` to filter by month) |
| refs | dropdown (all / has GH / has run / has Jira / no refs) |
| (actions) | "reset" button |

State is stored in `localStorage` under `findings.filters.{slug}`. Works alongside header-click sorting and the server-side `?status=...` / `?module=...` query params.

## Bulk run

Each row has a checkbox on the left. The header checkbox toggles all **visible** rows. The **Run (N)** button under the row counter pushes the selection into the Orchestrator queue, which runs them one at a time (Orchestrator takes one run per project at a time). See [orchestration.md → Bulk queue](orchestration.md#bulk-queue--sequential-dispatch-of-many-items).

---

See also:
- [`ideas.md`](ideas.md) — parallel page for product ideas.
- [`settings.md`](settings.md) — where `tech_debt_dir` lives.
- [`../workflows/weekly-scanners.md`](../workflows/weekly-scanners.md) — how to enable the weekly tech-debt scan.
- Technical: [`../../features/pipelines.md`](../../features/pipelines.md), [`../../routes.md`](../../routes.md).
