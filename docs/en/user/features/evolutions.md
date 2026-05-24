# Evolutions — proposed edits for agents

`/p/{slug}/evolutions` — table of evolution proposals: markdown files containing edits for individual agents (`.claude/agents/<name>.md`). They're written by the `/evolve-agent` slash-command during self-study — the agent decides what in its own instructions should be improved and drops the proposal into `evolutions_dir` (default `.claude/agents/_context/`).

## Contents

- [Where they come from](#where-they-come-from)
- [The proposals table](#the-proposals-table)
- [Filters](#filters)
- [Apply — apply a proposal](#apply--apply-a-proposal)
- [Conflict gate and force-apply](#conflict-gate-and-force-apply)
- [Create GitHub issue](#create-github-issue)
- [Change status](#change-status)
- [Delete](#delete)
- [Bulk run](#bulk-run)
- [Rubric panel](#rubric-panel)

## Where they come from

Evolution files appear when:
- A self-study session is started either via the **Start session** button on `/p/{slug}/rotation` or by the `nightly_learning` cron.
- During the `/self-study {agent}` session the agent uses the `/evolve-agent` slash-command, which writes markdown into `evolutions_dir`.
- There is no separate "generate evolutions" button — they're a side-effect of self-study.

File names are usually `YYYY-MM-DD-<slug>.md`; frontmatter contains at least `agent`, `status`, and optionally `title`, `conflict`, `github_issue`, `orchestration_run`.

## The proposals table

Columns:
- **agent** — name of `.claude/agents/<agent>.md` this proposal targets.
- **name** — short file name (without `.md`). Clickable — opens a modal with rendered markdown plus a raw link.
- **status** — select: `proposed` / `active` / `applied` / `archived` / `rejected`. Changes via auto-submitted form.
- **conflict** — `⚠` if it overlaps with another open proposal targeting the same agent.
- **title** — `title` from frontmatter.
- **refs** — `GH` (link to github_issue) + `run` (link to orchestration_run).
- **(actions)** — Apply / → GH / del / raw buttons.

## Filters

A filter row sits under the headers:

| Column | Filter |
|---|---|
| agent | substring search |
| name | substring search |
| status | dropdown (all / 5 statuses) |
| conflict | dropdown (all / conflict only / no conflict) |
| title | substring search |
| refs | dropdown (all / has GH / has run / no refs) |
| (actions) | "reset" button |

State is persisted in `localStorage` under `evolutions.filters.{slug}` — per project.

## Apply — apply a proposal

The **Apply** button (purple) — POST `/p/{slug}/evolutions/apply` with the file's relative_path. Click brings up a confirm modal:

> Run Orchestrator: apply this edit to `.claude/agents/<agent>.md`?

After confirm — an Orchestrator run is spawned with this goal:
1. Read the current agent file.
2. Apply the "Proposed change" section of the evolution file.
3. If the change conflicts with other sections — add an "## Open questions" section instead of overwriting.
4. Update the evolution file's frontmatter to `status: applied` + `applied_at`.
5. Finish the run.

The evolution file's frontmatter is updated with `orchestration_run: <run_id>` — you'll then see the `run` link in the "refs" column.

You're redirected to `/p/{slug}/orchestration/{run_id}` so you can watch progress.

## Conflict gate and force-apply

If ≥2 open evolution proposals target the same agent — all of them are automatically flagged `has_conflict=true` (even without explicit `conflict: true` in frontmatter). This is a guard against two simultaneous applies stomping on each other.

In the table these rows show:
- A `⚠` in the conflict column.
- The Apply button turns **red**, labelled **Apply (force)**.
- A hidden `force=1` field in the form.
- The confirm modal becomes danger-styled:

  > ⚠ CONFLICT: another open evolution proposal targets agent «<agent>». Apply anyway? This may overwrite parallel changes.

  The OK button reads "Apply (force)", not "Delete" (even though the variant is danger).

The server enforces the gate too: POST `/evolutions/apply` without `force=1` on a conflicting file returns HTTP 409 with a clear message — even if the frontend tries to submit directly.

### What to do about conflicts

- **Resolve manually**: review the files, pick one, mark the rest `status: rejected` or delete them. `has_conflict` clears automatically.
- **Apply with force** — if you're sure they complement each other or older proposals are stale.
- **Set `conflict: false` in frontmatter** — an "I checked, there's no real conflict" signal. After that Apply works without force.

## Create GitHub issue

The **→ GH** button — POST `/p/{slug}/evolutions/github`. Creates a GitHub issue from the evolution file's content (via the `gh` CLI). On success frontmatter gains `github_issue: <url>`, the button disappears, and the `GH` link in "refs" appears.

If `gh` isn't configured or has no repo access — the operation fails with a clear error.

## Change status

The status select (auto-submit) — POST `/p/{slug}/evolutions/status` rewrites `status:` in frontmatter. Use it to:
- Archive stale ones (`archived`).
- Reject obviously bad ones (`rejected`).
- Mark as already-applied-by-hand (`applied`).

## Delete

The **del** button (red) — POST `/p/{slug}/evolutions/delete`. Confirm modal:

> Delete file `<relative_path>`?

OK button — "Delete" (danger variant). The file is unlinked from disk — git history isn't touched, but if it wasn't committed, it's gone for good.

## Bulk run

Each row has a checkbox on the left. The header checkbox toggles all **visible** rows (filtered-out rows stay alone). The **Run (N)** button under the row counter queues the selection for the Orchestrator — they run sequentially.

Evolution-specific bulk caveats:
- If your selection includes conflicting items — they'll land in `failed` (conflict without force).
- On `/p/{slug}/orchestration` the queue banner has a **retry with force (N)** button — flips failed back to pending with `force=1`. That's what you want when you intentionally want to apply a batch of conflicting evolutions.

For details on the queue, dispatcher, and retry — see [orchestration.md → Bulk queue](orchestration.md#bulk-queue--sequential-dispatch-of-many-items).

## Rubric panel

Top of the page (when data exists) — a **Rubric stats** panel: distribution of `verdict`s from the rubric blocks inside evolution files. Buckets:
- **auto** (green) — `verdict: auto-apply` (safe to apply automatically).
- **review** (amber) — `verdict: review` (needs human review).
- **reject** (red) — `verdict: reject` (don't apply).
- **incomplete** (grey) — rubric block present but not filled.

If no file has a rubric block yet — a hint is shown: "No file has a rubric block yet. Older /evolve-agent versions don't emit them — expected. New proposals with frontmatter rubric: will populate this panel."

This is an **informational** panel — it doesn't drive any action, just shows the health of the proposal pool.

---

See also:
- [`rotation.md`](rotation.md) — where self-study (which produces evolutions) is launched.
- [`self-study.md`](self-study.md) — how self-study works and where `/evolve-agent` plugs in.
- [`orchestration.md`](orchestration.md) — where Apply dispatches the run; Bulk queue section.
- [`settings.md`](settings.md) — `evolutions_dir` and `context_overrides_dir`.
- Technical: [`../../features/orchestration.md`](../../features/orchestration.md), [`../../routes.md`](../../routes.md).
