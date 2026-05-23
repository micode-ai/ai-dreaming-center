---
description: Take a wiki-health snapshot and append it to docs/wiki/wiki-health-trends.md.
---

You are running inside Claude Code, spawned by the AI Dreaming Center
(weekly cron or on-demand) to record a fresh wiki-health datapoint. The
AI Dreaming Center reads `docs/wiki/wiki-health-trends.md` to plot the
trend graph on `/p/{slug}/wiki-health` — without periodic snapshots the
chart stays empty.

## What you have

- `cwd` is the project repository root.
- Wiki dir: `docs/wiki/` (created earlier by `/wiki-bootstrap`).
- Env vars: `LEARNING_SESSION_ID`, `DREAMING_API_URL`, `DREAMING_PROJECT_SLUG`.

## File to update

`docs/wiki/wiki-health-trends.md`. Create it if it doesn't exist with this header:

```markdown
# Wiki Health Trends

Auto-generated snapshots. Each `## label (YYYY-MM-DD)` section is one datapoint;
metrics underneath as ``- `key`: value`` lines. Do not edit by hand — the
AI Dreaming Center appends to this file via the `/wiki-health-scan` command.
```

## What to count

Use today's date (`YYYY-MM-DD`) and these metrics. Skip a metric if you
genuinely can't compute it — the parser tolerates missing keys.

- **`covered`** *(required)* — number of domain pages in `docs/wiki/`.
  Count `.md` files at the wiki root excluding `README.md`, `INDEX.md`,
  any file starting with `_` (archives, lint summaries), and
  `wiki-health-trends.md` itself.

- **`learning_notes`** *(required)* — `.md` files under
  `.claude/agents/learning-notes/` (recursive). Use `0` if the directory
  doesn't exist.

- **`covered_pct`** *(optional)* — `covered / total_modules * 100`, where
  `total_modules` is the count of top-level source directories that look
  like distinct modules (e.g., `apps/*`, `services/*`, `packages/*`,
  `src/*/` — pick whatever fits the repo). Round to one decimal. Skip
  this metric if the repo doesn't have an obvious module layout.

- **`uncovered_p1p2`** *(optional)* — count of modules tagged P1 or P2
  in priorities that lack a wiki page. Skip if you have no priority
  source (e.g., no `PRIORITIES.md` or equivalent).

## What to append

Read the existing file (if any), then append (do **not** overwrite):

```markdown

## Снимок ({YYYY-MM-DD})
- `covered`: 12
- `learning_notes`: 0
- `covered_pct`: 60.0
- `uncovered_p1p2`: 3
```

Substitute the date and your actual metric values. The leading blank
line matters — it separates this section from whatever came before.
**Important:** if a section with today's date already exists, do
nothing (skip the append, jump straight to step 5) — the cron may run
twice in one day and we don't want duplicate points.

## Steps

1. **Read** `docs/wiki/wiki-health-trends.md` if it exists. Check for a
   section dated today.
2. **Skip** if today's date is already present — report success and exit.
3. **Compute** the metrics above using Glob/Read/Bash as needed.
4. **Append** the new section (or create the file with the header +
   the section if it didn't exist). Use the Write/Edit tool — do not
   shell-redirect, the file is UTF-8 and PowerShell mangles encoding.
5. **Report back:**

   ```bash
   curl -s -X POST "$DREAMING_API_URL/api/session/finish" \
     -H "Content-Type: application/json" \
     -d "{\"session_id\":\"$LEARNING_SESSION_ID\",\"status\":\"success\",\"note_path\":\"docs/wiki/wiki-health-trends.md\"}"
   ```

## Rules

- Do **not** edit any file other than `docs/wiki/wiki-health-trends.md`.
- Do **not** delete or rewrite previous sections — append only.
- Section header MUST match the format `## <label> (YYYY-MM-DD)` exactly
  (parens around the date, ISO date, leading `## `). Label can be any
  short phrase; «Снимок» is the default.
- Metric lines MUST be backtick-quoted keys: ``- `covered`: 12``.
  Plain `- covered: 12` won't be parsed.
