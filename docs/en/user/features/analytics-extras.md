# Extra analytics

Six "auxiliary" pages in the project header, all read-only:

- **Evolutions** (`/p/{slug}/evolutions`) — list of agent overrides from `_context/`.
- **Loops** (`/p/{slug}/loops`) — reflex-loop files.
- **Plans** (`/p/{slug}/plans`) — Roman plans with progress.
- **Cascade Costs** (`/p/{slug}/cascade-costs`) — cost of orchestration runs.
- **Sidecar findings** (`/p/{slug}/sidecar-findings`) — JSON reports from reviewer agents.
- **Contracts** (`/p/{slug}/contracts`) — module/page contracts.

## Contents

- [Evolutions](#evolutions)
- [Loops](#loops)
- [Plans](#plans)
- [Cascade Costs](#cascade-costs)
- [Sidecar findings](#sidecar-findings)
- [Contracts](#contracts)

## Evolutions

`/p/{slug}/evolutions` — list of agent "evolutions". An evolution is an override markdown file describing a change in a particular agent's behaviour (a personality patch, basically). Lives in `evolutions_dir` or `context_overrides_dir` (under `_context/{agent}/`).

What the page shows:
- If the directory does not exist — grey text "Каталог `{path}` не существует. Переопредели `evolutions_dir` или `context_overrides_dir` в Settings, или создай папку." (Directory `{path}` does not exist. Override `evolutions_dir` or `context_overrides_dir` in Settings, or create the folder.)
- If parser-error — red "Ошибка: ..." (Error: ...).
- If there are evolutions — a table:
  - `agent` — agent name.
  - `name` — evolution file name.
  - `status` — status (active / archived / proposed / etc).
  - `conflict` — `⚠` if there are conflict markers in the file.
  - `title` — short description.

Use for:
- Audit: which overrides are applied.
- Conflict hunt: the ⚠ marker.

The UI does not allow editing — view-only. You manage via filesystem: add/remove/rename a file — refresh the page.

## Loops

`/p/{slug}/loops` — agent reflex-loops. A loop is a markdown description of a self-correcting cycle the agent runs (e.g. "find bug → fix → test → if test fails, repeat").

What it shows:
- If `loops_dir` is not configured — "loops_dir не настроен. См. Settings." (loops_dir is not configured. See Settings.)
- If the directory does not exist / error / empty — corresponding text.
- If there are loops — a table:
  - `name` — loop file name.
  - `title` — title.
  - `status` — running / completed / paused.
  - `iterations` — iteration count (number, right-aligned).

Use for:
- Understanding which loops are active in the project.
- History audit: 10 iterations is a lot.

Also read-only. Usually created by agents in the course of their work.

## Plans

`/p/{slug}/plans` — markdown plans that Roman/agents write with a tasks checklist. Live in `plans_dir`.

What it shows:
- If `plans_dir` is not configured — "plans_dir не настроен. См. Settings." (plans_dir is not configured. See Settings.)
- If the directory does not exist / is empty — corresponding text.
- If there are plans — a table:
  - `name` — file name.
  - `title` — title.
  - `status` — pending / in-progress / done.
  - `progress` — visual progress bar: a bar (32 units wide, green fill) + text `done/total`.

Progress is counted by DC from checkboxes in the md file:
- `[x]` — done.
- `[ ]` — todo.
- `done / (done + todo)` — percent.

If Roman writes a plan as a `## Tasks` section with checkboxes — DC automatically parses and counts.

Use for:
- Spotting plans at 80% — close to done.
- Pending ones — waiting to start.

## Cascade Costs

`/p/{slug}/cascade-costs` — cost of orchestration runs (including cascades and regular Roman runs) in USD.

Source: `orchestrator_events` with the `cost_usd` field (from Claude's final result-event). Aggregated per run.

What it shows:
- If error — "Ошибка: ..." (Error: ...).
- If no runs — "Нет orchestration runs. Cascade pipelines поднимаются в Wave 3." (No orchestration runs. Cascade pipelines come up in Wave 3.)
- If there is data — two cards on top:
  - **Runs (latest 50)** — number.
  - **Total cost USD** — `$X.XXXX`.
  - Table latest-50:
    - `run_id` — short UUID.
    - `goal` — truncated.
    - `status`.
    - `events` — number of events with a cost.
    - `cost USD` — `$X.XXXX`.

Use for:
- "How much did orchestration cost me last month?"
- "Which run was the most expensive?"
- "Cascade vs regular Roman — where is more cost?"

Self-study costs are **not** included here — they live in [`ai-usage.md`](ai-usage.md).

## Sidecar findings

`/p/{slug}/sidecar-findings` — JSON reports from reviewer agents (vera, svetlana, silent-failure-hunter). Each report is a finding with a severity level.

What it shows:
- If `sidecar_findings_dir` is not configured / no folder / error — corresponding text.
- If there is data — severity filter dropdown (critical / high / medium / low / info) + table:
  - `reviewer` — who wrote it (vera / svetlana / etc).
  - `id` — finding id.
  - `title` — what was found.
  - `severity` — level.
  - `module` — code module.
  - `file` — file.
  - `rule` — rule/category.

The filter works the same as for ideas: pick from the dropdown — auto-submit, URL `?severity=critical` — the table is filtered.

Use for:
- "Which critical findings are open right now?"
- "Which reviewer most often finds problems in `auth/`?"
- Triage before a sprint.

Unlike tech-debt findings — these are JSON, not markdown. The UI has no close/delete (no conventions). Manage via filesystem.

## Contracts

`/p/{slug}/contracts` — formal contracts of modules and pages. Useful for the cascade flow (where contract is a separate stage).

What it shows:
- If `contracts_dir` is not configured / no folder — corresponding text.
- If there is data — a table:
  - `name` — contract name.
  - `kind` — module / page / API / other.
  - `module` — which module it covers.
  - `page` — which page (if it applies).
  - `status` — draft / accepted / deprecated.
  - `last review` — timestamp of the last review.

Use for:
- Audit: is everything covered by contracts.
- Hunt for deprecated: what needs revisiting.

---

See also:
- [`tech-debt.md`](tech-debt.md) — parallel page for tech debt.
- [`ideas.md`](ideas.md) — for product ideas.
- [`orchestration.md`](orchestration.md), [`cascade.md`](cascade.md) — where these artifacts are used.
- [`settings.md`](settings.md) — where `*_dir` keys are configured.
- Technical: [`../../features/analytics.md`](../../features/analytics.md), [`../../features/pipelines.md`](../../features/pipelines.md).
