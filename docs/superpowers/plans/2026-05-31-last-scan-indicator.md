# Last-scan Indicator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show "last scan: <status> <relative-time>" next to the scan button on the findings («долги») and ideas («идеи») pages.

**Architecture:** A new `db.get_last_command_session(project_id, agent_name)` returns the most-recent `agent_learning_sessions` row for the scan command. The two routes fetch it and pass `last_scan` into the shared `_scan_action_bar.html` macro, which renders a status badge + a `<time>` element; a tiny `Intl.RelativeTimeFormat` script turns the embedded ISO timestamp into relative text. No schema change.

**Tech Stack:** FastAPI, Jinja2, SQLite, vanilla JS (`Intl.RelativeTimeFormat`), flat-JSON i18n (RU default, EN mirror).

**Spec:** `docs/superpowers/specs/2026-05-31-last-scan-indicator-design.md`

---

## Project verification model (read first)

No pytest suite exists by design (`CLAUDE.md`). Verification = `scripts/smoke_*.py` + `python scripts/check_i18n.py` + manual browser check.
- Cyrillic JSON/templates MUST be edited with the Write/Edit tool (UTF-8), never PowerShell Set-Content.
- Commit footer on every commit: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Run app: `python -m uvicorn dreaming.main:app --port 8086 --reload`.

## File Structure

- **Modify `dreaming/services/db.py`** — add `get_last_command_session` (one query; single responsibility: last-command lookup).
- **Modify `dreaming/i18n/messages_ru.json` + `messages_en.json`** — `scan.last.*` keys.
- **Modify `dreaming/templates/_scan_action_bar.html`** — optional `last_scan=None` param renders badge + `<time>` + a guarded relative-time script.
- **Modify `dreaming/templates/project_findings.html` + `project_ideas.html`** — import the macro `with context` and pass `last_scan=last_scan`.
- **Modify `dreaming/routes/project_findings.py` + `project_ideas.py`** — fetch `last_scan`, add to context.
- **Create `scripts/smoke_last_scan.py`** — verifies the db helper.

## Data facts (verified — don't re-derive)
- `agent_learning_sessions` columns: `id, project_id, agent_name, started_at, finished_at, status, model, error_message`.
- Scan rows have `agent_name = "cmd:{slug}:tech-debt-scan"` (findings) / `"cmd:{slug}:product-idea-scan"` (ideas). `status` ∈ running/success/failed.
- `db.fetch_one(sql, params)` returns a dict-like row or `None`; `db.execute(sql, params)` for inserts.
- The macro is imported WITHOUT context today, so i18n calls inside it need the importing template to use `... import scan_action_bar with context` (findings/ideas). `wiki.html` keeps its plain import and never passes `last_scan`, so its skipped badge branch never references `locale`.

---

## Task 1: `db.get_last_command_session`

**Files:** Modify `dreaming/services/db.py` (add a method in the Sessions section, near `get_or_create_session` ~line 514). Test: `scripts/smoke_last_scan.py`.

- [ ] **Step 1: Write the smoke test** `scripts/smoke_last_scan.py`:

```python
"""Smoke: db.get_last_command_session returns the most-recent scan row, or None."""
from __future__ import annotations
import asyncio, sys, tempfile, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dreaming.services.db import SqliteDB


async def amain() -> int:
    tmp = tempfile.mkdtemp()
    db = SqliteDB(os.path.join(tmp, "t.db"))
    await db.connect()           # adjust to the real init method if different
    pid = 1
    agent = "cmd:acct:tech-debt-scan"
    # None when no row
    assert await db.get_last_command_session(pid, agent) is None, "expected None when no rows"
    # Insert two running sessions; the helper must return the latest by started_at
    s1 = await db.create_session(pid, agent, "sonnet")
    s2 = await db.create_session(pid, agent, "sonnet")
    row = await db.get_last_command_session(pid, agent)
    assert row is not None, "expected a row"
    assert row["status"] == "running", f"unexpected status {row['status']!r}"
    assert "started_at" in row and "finished_at" in row, "missing columns"
    # A different command name must not match
    assert await db.get_last_command_session(pid, "cmd:acct:product-idea-scan") is None
    print("OK get_last_command_session")
    print("ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
```

NOTE: read `dreaming/services/db.py` for the real constructor / connect/init method name (e.g. `SqliteDB(path)` + `await db.connect()` or an `init`/`migrate` call) and adjust the two setup lines so the schema exists. Keep the assertions.

- [ ] **Step 2: Run it — expect FAIL** (`AttributeError: get_last_command_session`):
`python scripts/smoke_last_scan.py`

- [ ] **Step 3: Implement the helper** in `db.py` (add near `get_or_create_session`):

```python
    async def get_last_command_session(self, project_id: int, agent_name: str) -> dict | None:
        """Most-recent session row for a composite command agent_name
        (e.g. 'cmd:slug:tech-debt-scan'). Returns a dict with status/started_at/
        finished_at/error_message, or None if the command never ran."""
        row = await self.fetch_one(
            "SELECT status, started_at, finished_at, error_message "
            "FROM agent_learning_sessions "
            "WHERE project_id=? AND agent_name=? "
            "ORDER BY started_at DESC LIMIT 1",
            (project_id, agent_name),
        )
        return dict(row) if row else None
```

- [ ] **Step 4: Run smoke — expect `ALL OK`.**
- [ ] **Step 5: Commit**

```bash
git add dreaming/services/db.py scripts/smoke_last_scan.py
git commit -m "feat(db): get_last_command_session for last-scan lookup"
```

---

## Task 2: i18n keys

**Files:** Modify `dreaming/i18n/messages_ru.json` + `messages_en.json` (Edit tool — Cyrillic).

- [ ] **Step 1: Add to RU** (near other `scan.*`/common keys):
```
"scan.last.label": "Последний скан",
"scan.last.never": "не запускался",
"scan.last.running": "идёт",
"scan.last.success": "успешно",
"scan.last.failed": "ошибка"
```
- [ ] **Step 2: Add mirrored EN:**
```
"scan.last.label": "Last scan",
"scan.last.never": "never run",
"scan.last.running": "running",
"scan.last.success": "success",
"scan.last.failed": "failed"
```
- [ ] **Step 3:** `python scripts/check_i18n.py` → `OK: locales have identical key sets`.
- [ ] **Step 4: Commit**
```bash
git add dreaming/i18n/messages_ru.json dreaming/i18n/messages_en.json
git commit -m "i18n(scan): last-scan indicator keys"
```

---

## Task 3: render the indicator in `_scan_action_bar.html`

**Files:** Modify `dreaming/templates/_scan_action_bar.html`.

- [ ] **Step 1:** Change the macro signature to add `last_scan=None`:
`{% macro scan_action_bar(action_url, running, label, running_label, hint='', last_scan=None) %}`

- [ ] **Step 2:** Inside the macro, BEFORE the `<form>`, add the indicator block. The effective status is `running` (the live `scan_running` already passed as the `running` param) else the DB row's status. Use `finished_at` for finished runs, else `started_at`.

```html
  {% if last_scan is not none or running %}
  {% set _st = 'running' if running else (last_scan.status if last_scan else None) %}
  {% set _ts = (last_scan.finished_at or last_scan.started_at) if last_scan else None %}
  <span class="text-xs flex items-center gap-1.5" style="color: var(--text-faint);">
    <span>{{ "scan.last.label" | t(locale=locale) }}:</span>
    {% if _st == 'running' %}
      <span style="color: var(--status-running, #38bdf8);">● {{ "scan.last.running" | t(locale=locale) }}</span>
    {% elif _st == 'success' %}
      <span style="color: var(--status-success, #34d399);">✓ {{ "scan.last.success" | t(locale=locale) }}</span>
    {% elif _st == 'failed' %}
      <span style="color: var(--status-failed, #f87171);"
            {% if last_scan and last_scan.error_message %}title="{{ last_scan.error_message }}"{% endif %}>✕ {{ "scan.last.failed" | t(locale=locale) }}</span>
    {% else %}
      <span>{{ "scan.last.never" | t(locale=locale) }}</span>
    {% endif %}
    {% if _ts %}
    <time data-scan-ts="{{ _ts }}" title="{{ _ts[:19] }}">{{ _ts[:16] }}</time>
    {% endif %}
  </span>
  {% endif %}
```

- [ ] **Step 3:** At the END of the file (after `{% endmacro %}`), add the relative-time script (guarded so it binds once even if the macro renders twice):

```html
<script>
(function () {
  if (window.__scanRelInit) return;
  window.__scanRelInit = true;
  function rel(iso) {
    var then = Date.parse(iso); if (isNaN(then)) return null;
    var s = Math.round((then - Date.now()) / 1000);
    var loc = document.documentElement.lang || "en";
    var rtf = new Intl.RelativeTimeFormat(loc, { numeric: "auto" });
    var abs = Math.abs(s);
    if (abs < 60) return rtf.format(Math.round(s), "second");
    if (abs < 3600) return rtf.format(Math.round(s / 60), "minute");
    if (abs < 86400) return rtf.format(Math.round(s / 3600), "hour");
    return rtf.format(Math.round(s / 86400), "day");
  }
  function paint() {
    document.querySelectorAll("time[data-scan-ts]").forEach(function (el) {
      var r = rel(el.getAttribute("data-scan-ts"));
      if (r) el.textContent = r;
    });
  }
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", paint);
  else paint();
})();
</script>
```

NOTE: this `<script>` sits at module scope in the partial. Because the partial is imported as a macro (not `{% include %}`), the script tag is NOT emitted just by importing — it is only emitted if the file is rendered. To guarantee the script reaches the page, emit it from the macro body instead: move the `<script>...</script>` to the very end of the macro body (just before `{% endmacro %}`), still wrapped in the `window.__scanRelInit` guard. Do that rather than leaving it after `{% endmacro %}`.

- [ ] **Step 4: Commit**
```bash
git add dreaming/templates/_scan_action_bar.html
git commit -m "feat(scan): render last-scan badge + relative time in action bar"
```

---

## Task 4: wire routes + templates

**Files:** Modify `dreaming/routes/project_findings.py`, `dreaming/routes/project_ideas.py`, `dreaming/templates/project_findings.html`, `dreaming/templates/project_ideas.html`.

- [ ] **Step 1 (findings route):** in `findings_page`, after `scan_running = ...`, add:
```python
    last_scan = None
    try:
        last_scan = await request.app.state.db.get_last_command_session(
            project.id, f"cmd:{project.slug}:tech-debt-scan")
    except Exception:
        last_scan = None
```
and add `"last_scan": last_scan,` to the TemplateResponse context dict.

- [ ] **Step 2 (ideas route):** in `ideas_page`, after `scan_running = ...`, add the same with `f"cmd:{project.slug}:product-idea-scan"`, and add `"last_scan": last_scan,` to its context.

- [ ] **Step 3 (findings template):** change the import line
`{% from "_scan_action_bar.html" import scan_action_bar %}`
to
`{% from "_scan_action_bar.html" import scan_action_bar with context %}`
and add `last_scan=last_scan` to the `scan_action_bar(...)` call.

- [ ] **Step 4 (ideas template):** same two edits (`with context` + `last_scan=last_scan` on the call at lines ~13-18).

- [ ] **Step 5: Verify import still works + i18n:**
```bash
python -c "import sys; sys.path.insert(0,'.'); import dreaming.main; print('import OK')"
python scripts/check_i18n.py
```

- [ ] **Step 6: Commit**
```bash
git add dreaming/routes/project_findings.py dreaming/routes/project_ideas.py dreaming/templates/project_findings.html dreaming/templates/project_ideas.html
git commit -m "feat(scan): pass last_scan into findings & ideas action bars"
```

---

## Task 5: final verification

- [ ] **Step 1:** `python scripts/smoke_last_scan.py` → `ALL OK`.
- [ ] **Step 2:** `python scripts/check_i18n.py` → OK.
- [ ] **Step 3:** `python -c "import dreaming.main"` → clean import.
- [ ] **Step 4 (manual, requires running app + a project with a scan):**
  - Open `/p/<slug>/findings` and `/p/<slug>/ideas`. With no prior scan → "Последний скан: не запускался".
  - Trigger a scan; while running → "идёт" badge. After it finishes → "успешно/ошибка" + relative time (hover shows exact). Switch locale (`dc_locale` cookie en/ru) → relative time + labels localize.
  - Open `/p/<slug>/wiki` (also uses the macro without `last_scan`) → unchanged, no badge, no error.
- [ ] **Step 5:** use `superpowers:requesting-code-review` before merge.

## Notes for the worker
- **DRY:** indicator lives once in the shared macro. **YAGNI:** no scan history, no re-run control, no progress.
- Don't touch the per-item `orchestration_run` refs link — unrelated.
- The `with context` import change is required ONLY for findings/ideas (they render the badge). Leave `wiki.html`'s plain import alone.
- Status colors reuse existing `--status-*` CSS vars with hex fallbacks.
