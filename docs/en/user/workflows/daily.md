# A day in the life of the tool

A typical DC workflow, morning–noon–evening. If you use DC actively — you'll be doing something like this every day.

## Contents

- [Morning: post-night check](#morning-post-night-check)
- [Before lunch: review the results](#before-lunch-review-the-results)
- [After lunch: tune custom topics](#after-lunch-tune-custom-topics)
- [Late afternoon: tech-debt and ideas](#late-afternoon-tech-debt-and-ideas)
- [Before leaving: verify cron](#before-leaving-verify-cron)

## Morning: post-night check

You open DC at http://localhost:8086 (or wherever yours runs). The aggregated dashboard at `/` greets you.

1. **Top-line metrics**: look at the 6 numbers up top:
   - Success per week: should be growing every day.
   - Failed / Timeout: should be small, or at least stable.
   - running now: usually 0 in the morning (the night crons should have finished). If something hangs — something got stuck.
   - Tech debt / Ideas: total summed across projects.

2. **Project cards**: skim the cards — each one has its `ok / fail / timeout / running`. If one project suddenly has all timeouts — red flag.

3. **Active sessions (right sidebar)**: if anything is still running — click in, look at what's hanging. A long session may be normal (cascade run), or — a stuck process.

5–10 minutes on the morning sweep.

## Before lunch: review the results

You go into the active project (the one you're working in right now). E.g. `/p/my-app/`.

1. **Recent sessions** on the dashboard: 10–20 latest sessions. Look at:
   - Which agents studied overnight.
   - Are they all `success`, or are some `failed`/`timeout`.
   - When was the agent that matters most to you (e.g. `vera`) last run? If long ago — bump tier to P1 on rotation so the cron picks faster.

2. **If there are failures** — click the row or go to `/p/{slug}/live` (even if not running anymore, the JSONL stays in `~/.claude/projects/`). Figure out the cause:
   - Couldn't find the agent file.
   - Rate limit from the API.
   - Bad prompt in the slash command.
   - Etc.

3. **Notes** on `/p/{slug}/notes` — go through new md files. Good notes — pull into Obsidian, garbage — ignore.

15–20 minutes on review.

## After lunch: tune custom topics

A useful moment: if by midday you've gathered tasks for today's-tomorrow's work, you can "ask" the agents to study specific topics tonight.

1. Open `/p/{slug}/kanban`.
2. Add 1–2 new topics:
   - Title — short description.
   - target_agents — specifically the one it'd help. Or `*` for everyone.
   - question — what specifically.
   - why_important — why now.
3. Save.

This will be mixed into the nightly self-study prompt tonight.

Optionally walk through existing custom topics: those that are no longer relevant — `delete`.

5 minutes.

## Late afternoon: tech-debt and ideas

Around 5–6pm, before leaving, it's typically useful:

1. **Findings** on `/p/{slug}/findings` — look at the tech-debt list. Close (close) those you finished today. Delete (delete) duplicates or wrong items.

2. **Tech-Debt aggregate** on `/p/{slug}/tech-debt` — look at the "By status" card. How many open vs closed? If open > 50 — time to triage.

3. **Ideas** on `/p/{slug}/ideas` — look at the backlog. If there's an obviously useful idea — click `→ Jira` to create a ticket (see [`jira-integration.md`](jira-integration.md)).

4. **Sidecar findings** on `/p/{slug}/sidecar-findings` — if you have reviewer agents running (vera/svetlana), look at what they found today. Critical / high — priority.

15 minutes.

## Before leaving: verify cron

1. **Global**: on `/settings` check:
   - `cron_enabled = true` (default).
   - `cron_expression = 0 3 * * *` (default 3am) or the time that fits you.
   - `agents_per_night = 3` (or however many you want).

2. **Per-project** (if there are specifics): on `/p/{slug}/settings` make sure cron_enabled / cron_expression overrides are what you expect.

3. **Default project**: on `/projects` confirm that at least one project is marked `★`. Not required, but convenient.

4. **Active sessions**: confirm there are no "forgotten" running sessions. If there are — Kill via `/p/{slug}/live`.

5 minutes.

If everything is in order — close the browser, the laptop can go to sleep (KeepAwake already allows it, no running sessions). The cron will start by itself overnight, and by morning you'll have a fresh batch of data.

---

See also:
- [`onboarding.md`](onboarding.md) — for a new user.
- [`nightly-cron.md`](nightly-cron.md) — detailed schedule setup.
- [`weekly-scanners.md`](weekly-scanners.md) — weekly scans (a once-a-week look).
- [`../features/topics-kanban.md`](../features/topics-kanban.md) — Kanban for topics.
