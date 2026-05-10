# Topics and Kanban

Two pages about study topics:
- **Topics** (`/p/{slug}/topics`) — read-only weekly checklist of agents from the starter kit.
- **Kanban** (`/p/{slug}/kanban`) — CRUD over custom topics that get mixed into the prompt of the nightly self-study.

## Contents

- [Topics: weekly checklist](#topics-weekly-checklist)
- [Kanban: custom topics](#kanban-custom-topics)
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

**This is a read-only page.** The checklist is generated and edited by the starter-kit agent itself (e.g. `team-lead.md`) during its own self-study. The UI does not let you add/remove items — only read.

If you don't have a starter kit — this page will always say "not found". That's fine, the page is optional.

## Kanban: custom topics

`/p/{slug}/kanban` — differs from Topics in that these are your own topics. Not a file, but rows in the SQL table `custom_topics`.

On the page:
- At the top — a white card with the add form.
- Below — the table of existing topics (if any).

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

When the nightly cron (or manual `Start session`) runs an agent, DC:
1. Reads every `custom_topics` for this `project_id` where `active=true`.
2. Filters by `target_agents`: if `*` or empty — everyone, if csv — does it contain agent_name.
3. Mixes them into the prompt via template variables of the `/self-study` slash command. The exact mechanism depends on the starter kit's implementation, but typically env vars or extra args.

For example, if there's a topic "Refactor auth" with `target_agents=vera`, and tonight the cron runs Vera — her prompt will include a section "Custom topics for tonight: …".

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
