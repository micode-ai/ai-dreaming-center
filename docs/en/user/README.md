# AI Dreaming Center — User Documentation

This is the collection of end-user-oriented guides — "how to use" the tool. If you are a developer and want to understand how DC works internally (code, DB schema, API) — head to `../README.md` (technical index).

## Quick start

- [`getting-started.md`](getting-started.md) — install and first session in 15–20 minutes.
- [`overview.md`](overview.md) — what AI Dreaming Center is, who it's for and why.
- [`features/out-of-the-box.md`](features/out-of-the-box.md) — out-of-the-box setup: starter-kit, directory autoconfig, session controls.
- [`workflows/onboarding.md`](workflows/onboarding.md) — extended "first day" from scratch to a configured nightly cron.

## Feature guides

Each menu item in the project header = a separate file here:

- [`features/projects.md`](features/projects.md) — project registry: add, disable, delete.
- [`features/self-study.md`](features/self-study.md) — what self-study is and how to run it manually / via cron.
- [`features/rotation.md`](features/rotation.md) — agent table: tier, enabled, the `Start session` button.
- [`features/live-log.md`](features/live-log.md) — watching the live stdout stream, the `Kill` button.
- [`features/topics-kanban.md`](features/topics-kanban.md) — weekly checklist (read-only) and kanban for custom topics.
- [`features/notes.md`](features/notes.md) — browser for agent notes.
- [`features/tech-debt.md`](features/tech-debt.md) — findings list, detail, close/delete + tech-debt aggregate.
- [`features/ideas.md`](features/ideas.md) — product ideas board and the `→ Jira` button.
- [`features/wiki.md`](features/wiki.md) — project wiki status and `Run /wiki-bootstrap`.
- [`features/ai-usage.md`](features/ai-usage.md) — token and cost analytics (per-project + global).
- [`features/orchestration.md`](features/orchestration.md) — running Roman, watching live, resume, **Bulk queue** for mass-dispatching findings/ideas/evolutions.
- [`features/evolutions.md`](features/evolutions.md) — proposed edits for agents: Apply / force-apply / conflict-gate / filters.
- [`features/cascade.md`](features/cascade.md) — cascade pipeline: contract → design → … → qa.
- [`features/analytics-extras.md`](features/analytics-extras.md) — Evolutions, Loops, Plans, Cascade Costs, Sidecar findings, Contracts.
- [`features/settings.md`](features/settings.md) — global vs per-project settings.
- [`features/language.md`](features/language.md) — switching between Russian and English.

## Typical scenarios

- [`workflows/daily.md`](workflows/daily.md) — a day in the life of the tool.
- [`workflows/onboarding.md`](workflows/onboarding.md) — extended first launch.
- [`workflows/new-project.md`](workflows/new-project.md) — add a new project to a running instance.
- [`workflows/jira-integration.md`](workflows/jira-integration.md) — configure Jira creds and create a ticket from an idea.
- [`workflows/nightly-cron.md`](workflows/nightly-cron.md) — configuring the nightly schedule.
- [`workflows/weekly-scanners.md`](workflows/weekly-scanners.md) — enabling the weekly scanners.

## Reference

- [`faq.md`](faq.md) — frequently asked questions.
- [`glossary.md`](glossary.md) — glossary of terms.

## If something is unclear

First open [`faq.md`](faq.md). If the answer is not there — check the technical [`../troubleshooting.md`](../troubleshooting.md) (it has diagnostic commands). If still nothing — file an issue in the repository.
