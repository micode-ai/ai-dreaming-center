# Product Ideas

`/p/{slug}/ideas` — board of product ideas with a status filter and a `→ Jira` button to create a ticket in one click.

## Contents

- [Where ideas come from](#where-ideas-come-from)
- [What the page shows](#what-the-page-shows)
- [Status filter](#status-filter)
- [The → Jira button](#the--jira-button)
- [After the ticket is created](#after-the-ticket-is-created)
- [If the directory is not configured](#if-the-directory-is-not-configured)

## Where ideas come from

Ideas are markdown files in the `product_ideas_dir` directory (configured in settings). They are created by the `weekly_product_ideas_scan_{slug}` cron agent (off by default, opt-in).

File structure is the same as for tech debt:
```
---
id: IDEA-2026-05-001
title: "Add live preview to settings form"
status: backlog
priority: medium
module: ui
created_at: 2026-05-01
jira_ticket: ""
---

# IDEA-2026-05-001 — Add live preview to settings form

## Pain
- Today it's unclear how settings changes look in the UI before Save.

## Proposal
- ...
```

Frontmatter fields: `id`, `title`, `status`, `priority`, `module`, `jira_ticket`. Status — usually `backlog` / `proposed` / `accepted` / `in-progress` / `done` / `rejected`. Free-form string, the UI does not validate.

## What the page shows

Open `/p/{slug}/ideas`. Display logic is the same as for findings:

- If `product_ideas_dir` is not configured — amber banner with a settings link.
- If the directory does not exist — grey "does not exist".
- If parser-error — red.
- If OK — a table titled "N ideas in `{ideas_dir}`".

Table columns:
- `id` — monospace.
- `title` — regular text.
- `status` — monospace badge.
- `priority` — monospace.
- `jira` — either the ticket (if already created) or a `→ Jira` button.

## Status filter

If there is at least one idea — a `<select>` appears in the top right with the unique statuses in the current set + the option "all statuses".

Behaviour:
- You pick a status from the dropdown.
- The form auto-submits (`onchange="this.form.submit()"`).
- The URL becomes `/p/{slug}/ideas?status=backlog`.
- The table is filtered.

To go back to all — pick "all statuses".

Useful for:
- "Show me only backlog — what to take next?"
- "How many `accepted` are already in progress?"
- "Where are the rejected — archive or delete?"

## The → Jira button

For every idea without `jira_ticket` you get a blue `→ Jira` button (a one-button form). POST to `/p/{slug}/ideas/{id}/jira`.

What happens:
1. DC reads the md file, takes `title` and `body`.
2. Via `JiraService` it calls the Jira REST API: `POST /rest/api/3/issue` with a payload containing `project.key`, `summary` (=title), `description` (=body), `issuetype.name='Task'`, `assignee.accountId`.
3. On success (HTTP 201) it takes `key` from the response (e.g. `PROJ-1234`) and rewrites the md file's frontmatter: `jira_ticket: PROJ-1234`.
4. Redirects back to `/ideas`.
5. Now the `jira` column for this idea shows `PROJ-1234` (monospace) instead of the button.

If Jira creds are not configured or are wrong — DC returns 500/4xx with a description. Open `/p/{slug}/settings` and fill in `jira_email`, `jira_api_token`, `jira_user_account_id`, `jira_project_key`.

More — [`../workflows/jira-integration.md`](../workflows/jira-integration.md).

## After the ticket is created

After clicking `→ Jira`:
- The md frontmatter is updated.
- A Task is created in Jira.
- In the UI — `jira_ticket` is shown as plain text. There is no clickable Jira link (yes, it could be added — DC has the Jira base_url already in product_ideas_dir).

If you want a reopen / closed-link:
- Open the Jira ticket manually: copy `PROJ-1234` and paste into the URL.
- Or open the md file and look at the frontmatter.

If you want to delete the idea (after it went to Jira) — there are no UI buttons. Delete the md file by hand or via git.

## If the directory is not configured

By default `product_ideas_dir` is empty. To configure:
1. `/p/{slug}/settings` → group "Paths" → `product_ideas_dir` → Override → type the absolute path.
2. Save.

Create the directory manually (DC will not create it). Then:
- Either wait for the next weekly scan — the agent will write files itself.
- Or manually drop a few md files with the correct frontmatter — the UI picks them up.

## Column filters

A filter row sits under the table headers:

| Column | Filter type |
|---|---|
| id | substring search |
| title | substring search |
| status | dropdown (all / idea / exploring / approved / building / shipped / dropped) |
| priority | substring search |
| refs | dropdown (all / has GH / has run / has Jira / no refs) |
| | "reset" button |

State is **persisted in `localStorage`** under `ideas.filters.{slug}` — survives reload and project switches. When a filter is active a "showing N of M" counter appears next to the row count; if nothing matches — "No rows match the filter".

The server-side `?status=...` query param is still honoured for old bookmarks: it pre-filters server-side and the client filters narrow further (intersection).

## Bulk run

Each row has a checkbox on the left. The header checkbox toggles all **visible** rows (filtered-out rows stay alone). The **Run (N)** button under the row counter pushes the selection into the Orchestrator queue, where they run sequentially. See [orchestration.md → Bulk queue](orchestration.md#bulk-queue--sequential-dispatch-of-many-items) for details.

---

See also:
- [`tech-debt.md`](tech-debt.md) — parallel page for tech debt.
- [`../workflows/jira-integration.md`](../workflows/jira-integration.md) — Jira creds setup.
- [`settings.md`](settings.md) — where `product_ideas_dir` and Jira config live.
- [`../workflows/weekly-scanners.md`](../workflows/weekly-scanners.md) — how to enable the weekly product ideas scan.
- Technical: [`../../features/pipelines.md`](../../features/pipelines.md), [`../../services.md#jira`](../../services.md), [`../../api.md`](../../api.md).
