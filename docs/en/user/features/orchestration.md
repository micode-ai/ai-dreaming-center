# Orchestration — running Roman

`/p/{slug}/orchestration` — list of orchestration runs and the new-run form. The detail page at `/{run_id}` shows a tree of nodes (Roman + subagents) and the message stream.

## Contents

- [What is Roman](#what-is-roman)
- [Run list](#run-list)
- [Starting a new run](#starting-a-new-run)
- [Detail page](#detail-page)
- [Polling and updates](#polling-and-updates)
- [Mark completed (manual)](#mark-completed-manual)
- [Resume](#resume)
- [One-Roman-per-project](#one-roman-per-project)
- [Bulk queue — sequential dispatch of many items](#bulk-queue--sequential-dispatch-of-many-items)
- [Chat auto-scroll and sidebar positioning](#chat-auto-scroll-and-sidebar-positioning)

## What is Roman

Roman is the root orchestrator agent. In code `agent_name="roman"`, `role="orchestrator"`. Started via the `claude` CLI with your `goal` as the prompt, and Claude uses the Task tool to delegate to subagents.

Conceptually:
```
[user goal]
     |
     v
+---------+
|  Roman  |  decomposes goal, picks sub-agents
+---------+
   /  |  \
  v   v   v
[A] [B] [C]   <- sub-agents (Task tool spawns)
```

Each subagent is a separate `claude` subprocess. Roman gives them clear tasks, gathers results, aggregates the answer.

In DC you see:
- One **run** in orchestrator_runs (root = Roman).
- Several **nodes** in orchestrator_nodes (one per agent, including Roman as root).
- Several **messages** in orchestrator_messages (text from each agent's stdout).

## Run list

Open `/p/{slug}/orchestration`. At the top — a white card with a form:
- Input "Цель Roman-сессии (например: «декомпозируй фичу X»)" (Goal of the Roman session, e.g. "decompose feature X") (required).
- Blue button `Start Roman`.

Below the form — runs table (if any):
- `run_id` — short UUID (first 8 chars + ellipsis). Clickable link to detail.
- `goal` — truncated (80 chars) goal.
- `status` — coloured monospace: amber `running`, green `completed`, red `failed`.
- `started` — timestamp.
- `finished` — timestamp or `—`.

Sorted newest first.

If there are no runs — text "Нет orchestration runs пока. Запусти Roman через форму выше." (No orchestration runs yet. Start Roman via the form above.)

## Starting a new run

Type a goal in the form and click `Start Roman`.

What happens:
1. POST to `/p/{slug}/orchestration/start`.
2. DC creates an `orchestrator_runs` row: id (UUID), project_id, goal, status='running', started_at=now.
3. Creates an `orchestrator_nodes` row for the root: agent_name='roman', role='orchestrator', status='running'.
4. Spawns `claude` with the goal as prompt and `cwd={working_dir}`.
5. Starts `ClaudeSessionTail` (reads stdout JSONL and writes into orchestrator_events / orchestrator_messages).
6. Starts `SubagentWatcher` (monitors the filesystem `subagents/` under session-dir; when a new JSONL appears — creates a node and subscribes a second tail).
7. Redirects the browser to `/p/{slug}/orchestration/{run_id}`.

From there — watch the run on the detail page.

## Detail page

`/p/{slug}/orchestration/{run_id}`.

At the top — header:
- Breadcrumb `← к списку runs` (← back to runs).
- Heading: the run's goal (full).
- Metadata: full UUID monospace, status (coloured), started, finished, Claude session UUID (if present).
- Buttons depending on status:
  - If `running`: `Mark completed`.
  - If finished with external_id: `Resume` + input "Что дальше? (опц.)" (What next? (opt.)).
  - If finished without external_id: nothing.

Then — the **Nodes** section:
- Heading "Nodes (N)" where N is the count.
- Table: `agent`, `role`, `status`, `started`.
- If there are no nodes — "Нет nodes пока. Watcher активен — подождём ещё пару секунд…" (No nodes yet. Watcher is active — wait a couple of seconds…) (if status running).

Then — the **Messages** section:
- Heading "Messages (N)".
- A list of white cards, one per message. Each card: author, kind (assistant_message / tool_use / tool_result / etc.), timestamp, and `<pre>` with whitespace-pre-wrap — the message text.
- If empty — "Нет messages пока." (No messages yet.)

## Polling and updates

The detail page uses AJAX polling every 2 seconds (while status is `running`):
- Sends GET `/p/{slug}/orchestration/{run_id}/refresh`.
- Receives JSON: `{status, node_count, message_count}`.
- If node_count or message_count changed — `location.reload()` (full page reload).
- If status left `running` — also reload.
- On a pending error — retry after 5 seconds.

That's why you see new nodes and messages "appear" roughly in real time (latency up to 2 seconds + page reload).

Once the run is `completed` or `failed` — polling stops. For further updates — manual refresh.

## Mark completed (manual)

The `Mark completed` button (only for running):
- POST to `/p/{slug}/orchestration/{run_id}/finish`.
- DC marks the run `completed`, finished_at=now.
- Claude's subprocess is **not killed** automatically — it will keep writing into JSONL until natural completion.
- Polling stops.

Use it when:
- The run hangs forever in running but you know Claude already finished (callback didn't arrive).
- You need to "close" a run to start a new one (one-Roman-per-project).
- You manually killed the process (via Task Manager / `kill -9`) and the DB row is stuck.

After Mark completed you can press Resume to continue from the same session_id.

## Resume

The `Resume` button (only for finished with `external_id`):
- In the "Что дальше? (опц.)" input you can type a follow-up prompt or leave it empty (Claude continues without new instructions).
- POST to `/p/{slug}/orchestration/{run_id}/resume`.
- DC spawns a new claude subprocess with `--resume {external_id}` and the given prompt.
- Either a new run is created or the existing one is updated (depends on the implementation) — in any case you get a continuation.
- Redirect to the detail page.

Use it when:
- Roman finished the first half of the task, you read the result, and want to give him extra instructions.
- The run failed mid-way (`failed`) but `external_id` exists — you can try to continue.

## One-Roman-per-project

Only one orchestration run per project can be in `running` status. If you try to start a second one (you click `Start Roman` on a project that already has a running run) — DC redirects you to the existing run instead of creating a new one.

This is to:
- Avoid spawning parallel Romans (they'd spawn the same subagents and get confusing).
- Keep orchestration trees clean.

If you want parallel work:
- Close the existing one (Mark completed or wait for completion).
- Then a new one will start.

Or use another project — its Roman is independent.

## Bulk queue — sequential dispatch of many items

When you need to push a whole batch of tech-debt items, product ideas, or evolutions through the Orchestrator, every `/findings`, `/ideas`, and `/evolutions` table has a checkbox column and a **Run (N)** button.

### How to use

1. The header checkbox toggles all currently **visible** rows (filtered-out rows stay untouched; partial selection shows the indeterminate state).
2. Click **Run (N)** under the row counter. Disabled while N=0; click opens a confirm modal: "Queue N items? They'll run sequentially — Orchestrator takes one run at a time."
3. After confirming — flash message "N items queued for orchestration", redirect back to the source page. The background dispatcher starts feeding them through.

### Queue on `/p/{slug}/orchestration`

Top-of-page banner labelled **Queue**:
- **N pending** (amber, pulse) — how many items haven't been dispatched yet.
- **queue is empty** — every item reached dispatch.
- Per-item chips: kind icon (🐛 finding, 💡 idea, 🧬 evolution) + truncated identifier + status (`pending` / `dispatched` / `failed`). Already-dispatched items link to their run.
- For failed items the error message is shown inline (not just in the tooltip).

### Dispatcher diagnostics

A second badge next to the pending counter explains what the dispatcher is doing right now:

| Badge | Meaning |
|---|---|
| ⚡ **processing** | Slot is free, dispatcher is working through the queue |
| ⏳ **waiting for run abc12345…** | Slot held by a live Orchestrator run; queue resumes when it finishes |
| ⏸ **dispatcher stopped** | Pending items exist but the background task crashed — click "wake dispatcher" |
| ⚠ **slot check error** | Internal error in the slot probe; tooltip shows the exception. Dispatcher keeps going — slot-check is fail-open |

### Queue control buttons

- **wake dispatcher** — restarts the background task. Safe: no-op if already running.
- **retry failed (N)** — flips all failed items back to pending. For evolution conflict-gate failures this won't help (they'll fail again) — use the next button instead.
- **retry with force (N)** (red, with confirm) — same as retry, plus sets `force=1` on the items. Evolution items with a conflict will now pass the gate. The OK button in the modal reads "Retry (force)", not "Delete" (even though the variant is danger).
- **dismiss completed** — removes `dispatched`/`failed` cards, leaves pending alone.
- **clear queue** (with confirm) — wipes the panel entirely. Already-dispatched runs continue running in the DB — this is purely cosmetic.
- **dismiss** — shown when nothing is pending and you just want the completed list gone.

### Caveats

- The queue is **in-memory** and lost on server restart. Already-dispatched runs survive in the DB; only pending items vanish. The dispatcher is restartable from scratch — usually fine.
- **Zombie auto-cancel**: if the slot check finds a DB row with `status='running'` but no live PM process, the dispatcher itself marks the run as `cancelled` (`error_message="auto-cancelled by bulk dispatcher (no live process)"`) — so the queue doesn't wedge on stale "running" rows left over from a kill.
- **Idempotency**: if an item already has a linked live run, re-dispatch reuses it (no duplicates).
- **Evolution conflict-gate**: if ≥2 open evolution proposals target the same agent, dispatch without `force` raises a clear `ValueError`. Solutions — archive the conflicting ones, or use "retry with force".

### On the dashboard

The Orchestration tile shows a blue **+N queued** badge next to the running count (tooltip: "Items queued for sequential Orchestrator dispatch"). Only visible when `pending > 0`.

## Chat auto-scroll and sidebar positioning

**Messages in the chat** — sticky scroll behaviour:
- On every new `message_added` SSE event, if you were near the bottom (last 80px) the page smoothly scrolls down.
- If you've scrolled up to read older messages, the page does NOT yank you back — new messages stack at the bottom, you scroll back manually when ready.
- **On first open of a run** the page automatically scrolls to the last message (after `requestAnimationFrame` so layout has settled). Open a run — you immediately see the latest activity, not the goal header.

**Left sidebar with the run list**: on page load the selected card (`?run_id=...`) is automatically scrolled to the middle of the sidebar — no more losing it below the fold when you have many runs. The scroll happens inside the sidebar; the page itself doesn't move.

---

See also:
- [`cascade.md`](cascade.md) — structured multi-stage runs.
- [`live-log.md`](live-log.md) — for self-study runs (different mechanism).
- [`analytics-extras.md`](analytics-extras.md) — Cascade Costs.
- Technical: [`../../features/orchestration.md`](../../features/orchestration.md), [`../../api.md#orchestration`](../../api.md), [`../../schema.md`](../../schema.md).
