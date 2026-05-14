# Topics and Kanban

Two pages about study topics:
- **Topics** (`/p/{slug}/topics`) — read-only weekly checklist of agents from the starter kit.
- **Kanban** (`/p/{slug}/kanban`) — CRUD over custom topics that get mixed into the prompt of the nightly self-study.

## Contents

- [Topics: weekly checklist](#topics-weekly-checklist)
- [Kanban: custom topics](#kanban-custom-topics)
- [Generate-topics button](#generate-topics-button)
- [Weekly auto-scan](#weekly-auto-scan)
- [Form fields](#form-fields)
- [How topics enter self-study](#how-topics-enter-self-study)
- [Deleting a topic](#deleting-a-topic)

## Topics: weekly checklist

Open `/p/{slug}/topics`. DC looks for a markdown file with the checklist in one of two standard places:

1. `{working_dir}/.claude/agents/lessons/_weekly-learning-checklist.md`
2. `{working_dir}/.claude/agents/_weekly-learning-checklist.md`

If the file is found — DC parses it into a list and shows it on the page:
- At the top — the file path.
- Then — a white block with monospace text, one line per checklist item.

If the file is not found — you'll see a warning "Weekly checklist не найден. Ожидаемые пути: ..." (Weekly checklist not found. Expected paths: ...) and the list of the two candidates.

**This is a read-only view of the `_weekly-learning-checklist.md` file.** The file is for human notes (if you use it at all). To get topics into agents, add them on the **Kanban** page — that's also where the «Generate topics» button lives. The Topics page only displays what's in the file; it never writes and doesn't invoke agents.

If you don't have a starter kit — this page will always say "not found". That's fine, the page is optional.

## Kanban: custom topics

`/p/{slug}/kanban` — differs from Topics in that these are your own topics. Not a file, but rows in the SQL table `custom_topics`.

On the page:
- At the top — a white card with the add form.
- Below — the table of existing topics (if any).

## Generate-topics button

To the right of the «Custom topics» heading — the **«Generate topics»** button.
A POST to `/p/{slug}/topics/generate` launches Claude CLI in the project with
the `/topics-scan` command (one-shot, not self-study). The command:

1. reads `git log -50`, `.claude/agents/learning-notes/`,
   `.claude/agents/sidecar-findings/`, `CLAUDE.md`, `README.md`;
2. proposes 5–10 topics for the week;
3. POSTs each one to `/api/p/{slug}/topics/ingest` → rows appear
   in this same table after a page reload.

While the command is running, the button is disabled (`Generating…`).
Session log — at `/p/{slug}/live`.

The command template lives at `templates/starter-kit/commands/topics-scan.md`
— it is installed into the project via starter-kit install.

## Weekly auto-scan

The `weekly_topics_scan` cron job runs the same `/topics-scan` on a schedule
(default: Monday 03:00 local). Disabled by default — enable it per-project on
the Settings page:

- `weekly_topics_scan_enabled` — true/false, default false.
- `weekly_topics_scan_cron` — crontab expression (5 fields), default `0 3 * * 1`.

Under the hood it uses a separate `command_name="weekly-topics-scan"` and
doesn't collide with the manual button (`command_name="topics-scan"`), so the
button and the cron can run in parallel even if they fire in the same minute.

## Form fields

The new-topic form has 5 fields:

1. **Заголовок темы** (`title`, required) — short name of what to study. Example: "Refactor session management — переход на FastAPI dependency injection" (Refactor session management — move to FastAPI dependency injection).
2. **Модуль** (`module`, optional) — module/section name in the project. Example: `auth`, `billing`.
3. **Агенты** (`target_agents`, optional) — who to mix it into. Comma-separated (`vera,svetlana`) or empty (= everyone).
4. **Что именно изучить** (`question`, optional textarea) — the detailed question the agent must answer. Example: "What are the side-effects of the current `auth.login()`? What are the 3 main pain-points?".
5. **Почему важно** (`why_important`, optional textarea) — the rationale, context. Example: "In 2 weeks we begin the rewrite; before then we need an inventory of pain-points".

The `Добавить` (Add) button at the bottom — POST to `/p/{slug}/kanban/add`. A row is inserted with `active=true`.

If you submit an empty `title` — the browser blocks it (HTML required).

## How topics enter self-study

When the nightly cron (or the `Start` button on the **Rotation** page) runs
an agent, DC:
1. Reads `custom_topics` for this `project_id` where `active=1`.
2. Filters by `target_agents`: empty or `*` — for everyone; CSV — only if the
   agent name is in the list.
3. Formats them as a markdown block titled "## Темы на сегодня (из DC)" and
   mixes it into the `/self-study <agent>` prompt via `extra_prompt`.

The helper `dreaming/services/topics_prompt.py:build_topics_extra_prompt`
returns `""` if there are no topics — projects without custom_topics behave
exactly as before (zero regression).

After the session ends `active` stays true (not auto-marked done). Intentional: you may want to keep a topic "in work" for several nights until you decide to delete.

## Deleting a topic

In the table, on the right of each row, there's an underlined red `delete` link. POST to `/p/{slug}/kanban/{id}/delete`.

The row is deleted forever. There is no confirmation — be careful.

If you want to "turn off" rather than delete (so it doesn't get mixed into self-study) — manual UPDATE in DB needed (`UPDATE custom_topics SET active=false WHERE id=...`). The UI has no toggle.

## If there are no topics

If Kanban is empty — you'll see the text "Нет custom topics. Добавь выше — они подмешаются в prompt nightly_learning." (No custom topics. Add some above — they will be mixed into the nightly_learning prompt.)

That's a normal mode: you can not use Kanban at all and rely on the weekly checklist from Topics.

---

See also:
- [`self-study.md`](self-study.md) — what nightly_learning is.
- [`rotation.md`](rotation.md) — managing the agent list.
- [`../workflows/daily.md`](../workflows/daily.md) — Kanban's typical role during the day.
- Technical: [`../../schema.md#custom_topics`](../../schema.md), [`../../features/pipelines.md`](../../features/pipelines.md).
