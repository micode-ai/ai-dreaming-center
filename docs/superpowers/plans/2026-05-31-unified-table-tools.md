# Unified Table Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every dashboard table client-side sorting and filtering through one reusable, data-attribute-driven component instead of per-page copy-paste.

**Architecture:** A single static module (`table_tools.js` + `table_tools.css`) auto-initializes on `DOMContentLoaded` over every `<table data-table-tools>`. Tables opt in declaratively (header/row/filter data-attributes); the component owns all sort/filter/persistence/a11y behaviour. The proven inline implementation in `project_findings.html` is extracted into this component (parity gate), then rolled out template-by-template. Hybrid: client-side by default; server-side `?sort=&q=` only point-wise for genuinely large tables (deferred).

**Tech Stack:** Vanilla JS (no framework), Jinja2 templates, FastAPI static files, flat-JSON i18n (RU default, EN mirror).

**Spec:** `docs/superpowers/specs/2026-05-31-unified-table-tools-design.md`

---

## Project verification model (read before starting)

This repo has **no pytest / unit-test suite — by design** (see `CLAUDE.md`). The TDD
loop here is adapted, and this adaptation is intentional:

- **"Failing test" → a deterministic check that fails before the change**: either a
  `scripts/smoke_table_tools.py` assertion, or a documented manual browser check
  with an explicit "before: broken / after: works" observation.
- **Run the app for manual checks:**
  `python -m uvicorn dreaming.main:app --port 8086 --reload`, then open the page.
- **i18n parity is enforced** by `python scripts/check_i18n.py` — run it after any
  i18n change.
- **Cyrillic JSON/templates MUST be written via the Write/Edit tool** (UTF-8).
  PowerShell `Set-Content` corrupts them (UTF-16). (`CLAUDE.md`)
- **Commit message footer** (every commit):
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

## File Structure

**Created:**
- `dreaming/static/table_tools.js` — all client behaviour (sort, filter, persistence, events, a11y). Single responsibility: enhance opted-in tables.
- `dreaming/static/table_tools.css` — sort indicators + filter-row styling, themed dark.
- `scripts/smoke_table_tools.py` — static guard: assets exist, component API present, every shippable `<table>` is opted in or allow-listed.

**Modified:**
- `dreaming/templates/base.html` — load the two assets globally.
- `dreaming/templates/project_findings.html` — refactor onto the component, delete inline JS/CSS, migrate bulk event.
- `dreaming/templates/project_evolutions.html` — migrate its `bulk:rows-changed` listener to `table-tools:changed`.
- ~20 other `dreaming/templates/*.html` table templates — declarative opt-in.
- `dreaming/i18n/messages_ru.json` + `messages_en.json` — shared `table.*` keys.
- Capped routes (audited in Task 9) — optional cap relaxation only.

---

## Data-attribute contract (reference for all rollout tasks)

```
<table data-table-tools
       data-tt-key="ideas.{{ project.slug }}"      (optional: localStorage persistence)
       data-tt-count-tmpl="{shown} / {total}"      (optional: i18n count template)
       data-tt-empty-text="Nothing matches">       (optional: i18n empty message)

  <thead>
    <tr>
      <th data-sort-col="title" data-sort-type="text">Title</th>   (sortable header)
      <th data-sort-col="created" data-sort-type="date">Created</th>
      <th>Actions</th>                                              (no data-sort-col = not sortable)
    </tr>
    <tr data-tt-filter-row>                                        (optional per-column filter row)
      <th><input data-filter-col="title" data-filter-mode="substr"></th>
      <th><select data-filter-col="status" data-filter-mode="exact">…</select></th>
      <th></th>
    </tr>
  </thead>

  <tbody>
    <tr data-filter-row
        data-title="lower-cased title"     (optional explicit values; else cell text is used)
        data-status="open">
      <td data-sort-value="2026-05-31">31 May</td>   (optional per-cell sort override)
      …
    </tr>
  </tbody>
</table>
```

- **Sort value resolution:** `td[data-sort-value]` → row `data-<col>` → cell `textContent`.
- **Filter value resolution:** row `data-<col>` → cell `textContent`.
- **Sort types:** `text` | `num` | `date` (ISO `YYYY-MM-DD…`) | `prio` (critical>high>medium>low) | `status`. Default `text`.
- **`status` caveat:** the rank map covers `running > open > in-progress > blocked > timeout > closed > dropped`. A `status` column whose values aren't in the map sorts them all equal (rank −1) — acceptable, but use `text` if a table's statuses are unrelated to this vocabulary.
- **`date` caveat:** only correct over ISO strings. A column rendering localized/relative dates MUST supply an ISO `data-<col>` or `data-sort-value`.
- **Global search:** `<input data-tt-search>` placed anywhere in the table's container; substring over all cell text of each row.
- **Custom predicate:** `window.tableToolsFilters['refs'] = (rowEl, value) => bool`.
- **Event:** `table-tools:changed` dispatched on the `<table>` after every pass.

---

## Task 1: `table_tools.css`

**Files:**
- Create: `dreaming/static/table_tools.css`

- [ ] **Step 1: Write the stylesheet**

```css
/* table_tools.css — sort indicators + filter-row styling for [data-table-tools]. */
[data-table-tools] th[data-sort-col] {
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}
[data-table-tools] th[data-sort-col]:hover { color: var(--brand, #6366f1); }
[data-table-tools] th[data-sort-col] .tt-ind {
  display: inline-block;
  margin-left: 0.25em;
  font-size: 0.7em;
  opacity: 0.4;
}
[data-table-tools] th[aria-sort="ascending"]  .tt-ind,
[data-table-tools] th[aria-sort="descending"] .tt-ind {
  opacity: 1;
  color: var(--brand, #6366f1);
}
[data-table-tools] th[aria-sort="ascending"]  .tt-ind::before { content: "↑"; }
[data-table-tools] th[aria-sort="descending"] .tt-ind::before { content: "↓"; }
[data-table-tools] th[data-sort-col]:not([aria-sort]) .tt-ind::before,
[data-table-tools] th[aria-sort="none"] .tt-ind::before { content: "↕"; }

[data-table-tools] [data-tt-filter-row] input,
[data-table-tools] [data-tt-filter-row] select {
  width: 100%;
  font-size: 0.75rem;
}
.tt-search {
  font-size: 0.8rem;
  padding: 0.35rem 0.5rem;
  border-radius: 0.5rem;
  border: 1px solid var(--border-subtle, #1e293b);
  background: var(--bg-card, #111827);
  color: var(--text-body, #cbd5e1);
}
.tt-count { font-size: 0.75rem; color: var(--text-faint, #64748b); }
.tt-empty { font-size: 0.85rem; color: var(--text-faint, #64748b); margin-top: 0.75rem; }
.tt-empty[hidden], .tt-count[hidden] { display: none; }
```

- [ ] **Step 2: Verify the file is valid CSS** (no parser will complain — eyeball brace balance). Commit.

```bash
git add dreaming/static/table_tools.css
git commit -m "feat(table-tools): add reusable table css"
```

---

## Task 2: `table_tools.js` — full component

**Files:**
- Create: `dreaming/static/table_tools.js`

- [ ] **Step 1: Write the component**

```js
/* table_tools.js — reusable client-side sort + filter for [data-table-tools] tables.
   Opt-in via data-attributes (see docs/superpowers/specs/2026-05-31-unified-table-tools-design.md).
   Auto-initializes on DOMContentLoaded; idempotent (guarded per table). */
(function () {
  "use strict";

  // Registry for custom per-column filter predicates: fn(rowEl, value) => bool.
  window.tableToolsFilters = window.tableToolsFilters || {};

  var PRIO = { critical: 4, high: 3, medium: 2, low: 1, "": 0 };
  var STATUS = { running: 6, open: 5, "in-progress": 4, blocked: 3,
                 timeout: 2, closed: 1, dropped: 0, "": -1 };

  function indexInRow(th) {
    return Array.prototype.indexOf.call(th.parentNode.children, th);
  }

  function sortValue(row, col, colIndex) {
    var cell = row.children[colIndex];
    if (cell && cell.hasAttribute("data-sort-value")) {
      return cell.getAttribute("data-sort-value");
    }
    if (col && row.dataset[col] != null && row.dataset[col] !== "") {
      return row.dataset[col];
    }
    return cell ? cell.textContent.trim() : "";
  }

  function filterValue(row, col, colIndex) {
    if (col && row.dataset[col] != null) return row.dataset[col];
    var cell = colIndex >= 0 ? row.children[colIndex] : null;
    return cell ? cell.textContent.trim().toLowerCase() : "";
  }

  function compare(a, b, type) {
    if (type === "num") {
      var x = parseFloat((a || "").replace(/[^0-9eE+.\-]/g, "")) || 0;
      var y = parseFloat((b || "").replace(/[^0-9eE+.\-]/g, "")) || 0;
      return x - y;
    }
    if (type === "prio") {
      return (PRIO[(a || "").toLowerCase()] || 0) - (PRIO[(b || "").toLowerCase()] || 0);
    }
    if (type === "status") {
      var sa = STATUS[(a || "").toLowerCase()]; var sb = STATUS[(b || "").toLowerCase()];
      return (sa == null ? -1 : sa) - (sb == null ? -1 : sb);
    }
    // text + date (ISO strings sort lexicographically)
    return (a || "").localeCompare(b || "");
  }

  function enhance(table) {
    if (table.__ttInit) return;
    table.__ttInit = true;

    var tbody = table.querySelector("tbody");
    if (!tbody) return;
    var allRows = function () {
      return Array.prototype.slice.call(tbody.querySelectorAll("[data-filter-row], tr"))
        .filter(function (r, i, arr) {
          // prefer explicit [data-filter-row]; fall back to every body <tr>
          var explicit = tbody.querySelector("[data-filter-row]");
          return explicit ? r.hasAttribute("data-filter-row") : true;
        });
    };

    var headers = Array.prototype.slice.call(table.querySelectorAll("thead th[data-sort-col]"));
    var filterControls = Array.prototype.slice.call(
      table.querySelectorAll("[data-tt-filter-row] [data-filter-col]"));
    var searchInput = (table.closest("[data-tt-scope]") || table.parentNode || document)
      .querySelector("[data-tt-search]");

    var storageKey = table.getAttribute("data-tt-key");
    var countTmpl = table.getAttribute("data-tt-count-tmpl") || "{shown} / {total}";
    var emptyText = table.getAttribute("data-tt-empty-text") || "Nothing matches your filters.";

    // Inject sort indicators + a11y wiring.
    headers.forEach(function (th) {
      if (!th.querySelector(".tt-ind")) {
        var ind = document.createElement("span");
        ind.className = "tt-ind";
        th.appendChild(document.createTextNode(" "));
        th.appendChild(ind);
      }
      th.setAttribute("role", "button");
      th.setAttribute("tabindex", "0");
      if (!th.hasAttribute("aria-sort")) th.setAttribute("aria-sort", "none");
    });

    // Inject count + empty-state elements after the table.
    var countEl = document.createElement("span");
    countEl.className = "tt-count"; countEl.hidden = true;
    var emptyEl = document.createElement("p");
    emptyEl.className = "tt-empty"; emptyEl.hidden = true; emptyEl.textContent = emptyText;
    table.parentNode.insertBefore(countEl, table.nextSibling);
    table.parentNode.insertBefore(emptyEl, countEl.nextSibling);

    var state = { sortCol: null, sortType: "text", sortDir: null, filters: {}, search: "" };

    function persist() {
      if (!storageKey) return;
      try { localStorage.setItem(storageKey, JSON.stringify(state)); } catch (e) { /* ignore */ }
    }
    function restore() {
      if (!storageKey) return;
      try {
        var saved = JSON.parse(localStorage.getItem(storageKey) || "{}") || {};
        if (saved && typeof saved === "object") {
          state.sortCol = saved.sortCol || null;
          state.sortType = saved.sortType || "text";
          state.sortDir = saved.sortDir || null;
          state.filters = saved.filters || {};
          state.search = saved.search || "";
        }
      } catch (e) { /* ignore */ }
    }

    function colIndexFor(col) {
      for (var i = 0; i < headers.length; i++) {
        if (headers[i].getAttribute("data-sort-col") === col) return indexInRow(headers[i]);
      }
      // header may be filter-only (no sort); find by filter control position
      return -1;
    }

    function applySort() {
      if (!state.sortCol || !state.sortDir) return;
      var idx = colIndexFor(state.sortCol);
      var rows = allRows();
      rows.sort(function (ra, rb) {
        var c = compare(sortValue(ra, state.sortCol, idx),
                        sortValue(rb, state.sortCol, idx), state.sortType);
        return state.sortDir === "asc" ? c : -c;
      });
      rows.forEach(function (r) { tbody.appendChild(r); });
      headers.forEach(function (th) {
        var isCol = th.getAttribute("data-sort-col") === state.sortCol;
        th.setAttribute("aria-sort", isCol
          ? (state.sortDir === "asc" ? "ascending" : "descending") : "none");
      });
    }

    function rowMatches(row) {
      if (state.search) {
        if (row.textContent.toLowerCase().indexOf(state.search.toLowerCase()) === -1) return false;
      }
      for (var col in state.filters) {
        var raw = state.filters[col];
        if (!raw) continue;
        var v = String(raw).toLowerCase();
        if (window.tableToolsFilters[col]) {
          var ok = false;
          try { ok = !!window.tableToolsFilters[col](row, raw); } catch (e) { ok = true; }
          if (!ok) return false;
          continue;
        }
        var ctrl = filterControls.filter(function (c) {
          return c.getAttribute("data-filter-col") === col;
        })[0];
        var idx = ctrl ? indexInRow(ctrl.closest("th, td") || ctrl) : -1;
        var cellVal = filterValue(row, col, idx);
        var mode = ctrl && ctrl.tagName === "SELECT" ? "exact"
                 : (ctrl && ctrl.getAttribute("data-filter-mode")) || "substr";
        if (mode === "exact") { if (cellVal !== v) return false; }
        else { if (cellVal.indexOf(v) === -1) return false; }
      }
      return true;
    }

    function applyFilter() {
      var rows = allRows();
      var shown = 0;
      var active = !!state.search || Object.keys(state.filters).some(function (k) { return state.filters[k]; });
      rows.forEach(function (r) {
        var ok = rowMatches(r);
        r.hidden = !ok;
        r.classList.toggle("hidden", !ok);
        if (ok) shown++;
      });
      if (active) {
        countEl.textContent = countTmpl.replace("{shown}", shown).replace("{total}", rows.length);
        countEl.hidden = false;
      } else {
        countEl.hidden = true;
      }
      emptyEl.hidden = !(active && shown === 0);
      table.dispatchEvent(new CustomEvent("table-tools:changed", { bubbles: true }));
      // Back-compat for the existing bulk-selection script.
      document.dispatchEvent(new CustomEvent("bulk:rows-changed", { detail: { source: "table-tools" } }));
    }

    // Wire sorting.
    headers.forEach(function (th) {
      var fn = function () {
        var col = th.getAttribute("data-sort-col");
        var type = th.getAttribute("data-sort-type") || "text";
        if (state.sortCol === col) {
          state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
        } else {
          state.sortCol = col; state.sortType = type; state.sortDir = "asc";
        }
        applySort(); persist();
      };
      th.addEventListener("click", fn);
      th.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fn(); }
      });
    });

    // Wire filters.
    filterControls.forEach(function (ctrl) {
      var col = ctrl.getAttribute("data-filter-col");
      var evt = ctrl.tagName === "SELECT" ? "change" : "input";
      ctrl.addEventListener(evt, function () {
        state.filters[col] = ctrl.value;
        applyFilter(); persist();
      });
    });
    if (searchInput) {
      searchInput.addEventListener("input", function () {
        state.search = searchInput.value;
        applyFilter(); persist();
      });
    }

    // Optional reset button.
    var resetBtn = (table.parentNode || document).querySelector("[data-tt-reset]");
    if (resetBtn) {
      resetBtn.addEventListener("click", function () {
        state.filters = {}; state.search = "";
        filterControls.forEach(function (c) { c.value = ""; });
        if (searchInput) searchInput.value = "";
        applyFilter(); persist();
      });
    }

    // Restore persisted state into controls, then apply.
    restore();
    filterControls.forEach(function (c) {
      var col = c.getAttribute("data-filter-col");
      if (state.filters[col] != null) c.value = state.filters[col];
    });
    if (searchInput && state.search) searchInput.value = state.search;
    applySort();
    applyFilter();
  }

  function init() {
    Array.prototype.forEach.call(document.querySelectorAll("table[data-table-tools]"), enhance);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
  window.tableTools = { enhance: enhance, init: init };
})();
```

- [ ] **Step 2: Commit**

```bash
git add dreaming/static/table_tools.js
git commit -m "feat(table-tools): add reusable sort+filter component"
```

---

## Task 3: Wire assets into base layout

**Files:**
- Modify: `dreaming/templates/base.html` (CSS after line 22 `app.css`; JS deferred)

- [ ] **Step 1: Add the CSS link** immediately after the `app.css` link:

```html
  <link rel="stylesheet" href="/static/app.css">
  <link rel="stylesheet" href="/static/table_tools.css">
```

- [ ] **Step 2: Add the deferred script** inside `<head>` (defer guarantees DOM ready), just before `{% block head %}`:

```html
  <script defer src="/static/table_tools.js"></script>
  {% block head %}{% endblock %}
```

- [ ] **Step 3: Manual check** — start the app, open any page, confirm in DevTools Network that `/static/table_tools.js` and `.css` return 200. Commit.

```bash
git add dreaming/templates/base.html
git commit -m "feat(table-tools): load component globally from base layout"
```

---

## Task 4: Shared i18n keys

**Files:**
- Modify: `dreaming/i18n/messages_ru.json`, `dreaming/i18n/messages_en.json` (Write/Edit tool only — Cyrillic)

- [ ] **Step 1: Add keys to RU** (place near other shared/common keys):

```
"table.search": "Поиск…",
"table.reset": "Сбросить",
"table.shown_count": "{shown} из {total}",
"table.empty": "Ничего не найдено по фильтрам."
```

- [ ] **Step 2: Add the mirrored EN keys:**

```
"table.search": "Search…",
"table.reset": "Reset",
"table.shown_count": "{shown} of {total}",
"table.empty": "Nothing matches your filters."
```

- [ ] **Step 3: Verify parity**

Run: `python scripts/check_i18n.py`
Expected: no missing-key errors.

- [ ] **Step 4: Commit**

```bash
git add dreaming/i18n/messages_ru.json dreaming/i18n/messages_en.json
git commit -m "i18n(table-tools): shared table search/reset/count/empty keys"
```

---

## Task 5: Refactor `project_findings.html` onto the component (PARITY GATE)

This is the acceptance test for the component design. Findings is the most complex
table (sortable headers, per-column filter row incl. the `refs` predicate,
persistence, shown-count, empty-state, bulk integration). If the component can
fully replace findings' inline code with no behaviour loss, it is sound.

**Files:**
- Modify: `dreaming/templates/project_findings.html`

- [ ] **Step 1: Record current behaviour (the "before").** Start the app, open
  `/p/<slug>/findings`. Confirm and note: header sort toggles asc/desc; priority
  sorts critical→low; per-column text filters; status/priority selects; the `refs`
  select (gh/run/jira/none); "shown N of M"; empty-state; localStorage persistence
  across reload; bulk "select all visible" respects filtered rows.

- [ ] **Step 2: Convert the markup.** On `<table id="td-table">` add
  `data-table-tools data-tt-key="findings.{{ project.slug }}"`,
  `data-tt-count-tmpl="{{ 'table.shown_count' | t(locale=locale) }}"`,
  `data-tt-empty-text="{{ 'table.empty' | t(locale=locale) }}"`.
  - Headers: replace `class="td-th-sort" data-col="X" data-type="Y"` with
    `data-sort-col="X" data-sort-type="Y"` (map `data-type="prio"` → `data-sort-type="prio"`;
    text → `text`). Remove the hand-rolled `<span class="sort-ind">`.
  - Filter row: add `data-tt-filter-row` to the `<tr id="td-filters">`; replace
    `data-td-filter="X"` with `data-filter-col="X"` on each input/select.
  - Rows: add `data-filter-row` to each `<tr data-td-row>`; keep the existing
    `data-id/data-title/data-status/data-priority/...` (the component reads them).
    Keep `data-has-gh/run/jira` for the refs predicate.
  - Reset button: change `id="td-filter-reset"` to also carry `data-tt-reset`.

- [ ] **Step 3: Register the `refs` custom predicate.** Replace the two big inline
  `<script>` IIFEs (the sort block and the filter block) with a single small script:

```html
<script>
window.tableToolsFilters = window.tableToolsFilters || {};
window.tableToolsFilters.refs = function (row, value) {
  if (value === "gh")   return row.dataset.hasGh === "1";
  if (value === "run")  return row.dataset.hasRun === "1";
  if (value === "jira") return row.dataset.hasJira === "1";
  if (value === "none") return !(row.dataset.hasGh === "1" || row.dataset.hasRun === "1" || row.dataset.hasJira === "1");
  return true;
};
</script>
```

  Delete the old `<style>` block for `.td-th-sort` (now in `table_tools.css`).
  **Keep** the third IIFE (the `td-bulk-form` selection script) — but change its
  `document.addEventListener('bulk:rows-changed', update)` to also work with the
  component's event; the component already re-emits `bulk:rows-changed`, so this
  listener keeps working unchanged. Verify the `visibleCbs()` check uses
  `.hidden` class (the component sets both `.hidden` and the `hidden` attribute).

- [ ] **Step 4: Verify parity (the "after").** Reload `/p/<slug>/findings` and
  re-run every observation from Step 1. All must match. Pay special attention to:
  refs filter, priority sort order, persistence across reload, and bulk
  "select all visible" after filtering.

- [ ] **Step 5: Commit**

```bash
git add dreaming/templates/project_findings.html
git commit -m "refactor(findings): use shared table-tools component (parity)"
```

---

## Task 6: Convert `project_ideas.html` + `project_evolutions.html` (parity, like findings)

**CRITICAL — these are NOT simple opt-ins.** Both templates already contain their
**own complete inline filter/bulk implementations** (`data-ideas-filter`/
`data-ideas-row`; `data-evo-filter`/`data-evo-row`), each with its own
`localStorage` key, shown-count, empty-state, refs predicate, and bulk script.
They must be converted **exactly like findings (Task 5)** — rewrite attributes to
the new contract **AND delete the inline filter (and sort, if present) `<script>`/
`<style>` blocks**. If you merely add `data-table-tools`, the component runs
*concurrently* with the old code → double-filtering, fighting shown-counts,
flickering. (These two are the other consumers in the three-template
`bulk:rows-changed` inventory: findings + ideas + evolutions.)

### Task 6a — `project_ideas.html`

**Files:** Modify `dreaming/templates/project_ideas.html`

- [ ] **Step 1: Record before-behaviour** on `/p/<slug>/ideas` (filters: id, title,
  status select, priority, refs select gh/run/jira/none; persistence; bulk).
- [ ] **Step 2: Convert markup.** On `<table id="ideas-table">` add
  `data-table-tools data-tt-key="ideas.{{ project.slug }}"` +
  `data-tt-count-tmpl`/`data-tt-empty-text` (as Task 5 Step 2). Headers: add
  `data-sort-col`/`data-sort-type` (id→`text`, title→`text`, status→`status`,
  priority→`prio`) — note ideas currently has **no** sort, so this *adds* sorting
  (a feature gain). Filter row → `data-tt-filter-row`; rename `data-ideas-filter`
  → `data-filter-col`. Reset button `#ideas-filter-reset` → add `data-tt-reset`.
  Rows: `data-ideas-row` → `data-filter-row`; keep `data-id/title/status/priority`
  and `data-has-gh/run/jira`.
- [ ] **Step 3: Replace inline JS.** Delete the inline filter IIFE (and any sort
  IIFE/`<style>`). Add the refs predicate (identical to findings):

```html
<script>
window.tableToolsFilters = window.tableToolsFilters || {};
window.tableToolsFilters.refs = function (row, value) {
  if (value === "gh")   return row.dataset.hasGh === "1";
  if (value === "run")  return row.dataset.hasRun === "1";
  if (value === "jira") return row.dataset.hasJira === "1";
  if (value === "none") return !(row.dataset.hasGh === "1" || row.dataset.hasRun === "1" || row.dataset.hasJira === "1");
  return true;
};
</script>
```

  **Keep** the ideas bulk-selection IIFE (it relies on `bulk:rows-changed`, which
  the component re-emits).
- [ ] **Step 4: Parity check** on `/p/<slug>/ideas` — all Step 1 behaviour plus the
  new column sorting. Commit:

```bash
git commit -am "refactor(ideas): use shared table-tools component (parity + adds sort)"
```

### Task 6b — `project_evolutions.html`

**Files:** Modify `dreaming/templates/project_evolutions.html`

- [ ] **Step 1: Record before-behaviour** on `/p/<slug>/evolutions` (filters: agent,
  name, status, conflict select 1/0, title, refs select gh/run/none; persistence;
  bulk — note the danger-variant "apply force" for conflicts must still work).
- [ ] **Step 2: Convert markup.** On `<table id="evo-table">` add
  `data-table-tools data-tt-key="evolutions.{{ project.slug }}"` + count/empty.
  Headers: `data-sort-col`/`data-sort-type` (agent→`text`, name→`text`,
  status→`status`, title→`text`). Filter row → `data-tt-filter-row`; rename
  `data-evo-filter` → `data-filter-col`. The **`conflict`** select (values `1`/`0`
  matching `data-conflict`) is a **plain exact-match select — no predicate
  needed**. Reset → `data-tt-reset`. Rows: `data-evo-row` → `data-filter-row`;
  keep `data-conflict`, `data-has-gh/run`.
- [ ] **Step 3: Replace inline JS.** Delete the inline filter IIFE. Add the
  evolutions refs predicate (**gh/run/none — NO jira**):

```html
<script>
window.tableToolsFilters = window.tableToolsFilters || {};
window.tableToolsFilters.refs = function (row, value) {
  if (value === "gh")  return row.dataset.hasGh === "1";
  if (value === "run") return row.dataset.hasRun === "1";
  if (value === "none") return !(row.dataset.hasGh === "1" || row.dataset.hasRun === "1");
  return true;
};
</script>
```

  **Keep** the evolutions bulk-selection IIFE.
- [ ] **Step 4: Parity check** on `/p/<slug>/evolutions` — Step 1 behaviour plus new
  sorting; verify the conflict "apply force" danger modal still fires. Commit:

```bash
git commit -am "refactor(evolutions): use shared table-tools component (parity + adds sort)"
```

---

## Task 7: Rollout — large list tables

Apply the **data-attribute contract** to each template below. For each:
1. Read its `<thead>`; add `data-table-tools` + `data-tt-key="<page>.{{ project.slug }}"`.
2. Mark each meaningful `<th>` with `data-sort-col`/`data-sort-type` (derive type:
   ids/text→`text`, counts→`num`, dates→`date` with ISO `data-sort-value` if the
   cell renders a localized date, priority→`prio`, status→`status`).
3. Add `data-filter-row` to body rows. Add a `<tr data-tt-filter-row>` with the
   useful filter controls (text input per searchable text column; `<select>` for
   small enumerations like status). Add a `data-tt-search` input + `data-tt-reset`
   button in the page's action bar.
4. For cells containing widgets (forms/selects/links) whose text isn't the sort
   key, add explicit row `data-<col>` values (lower-cased) like findings does.

**Worked example — `project_tech_debt.html` "Top modules" table** (`:40`):

```html
<table class="w-full bg-white rounded shadow text-sm"
       data-table-tools data-tt-key="techdebt-mods.{{ project.slug }}">
  <thead class="text-left border-b"><tr>
    <th class="p-2" data-sort-col="module" data-sort-type="text">module</th>
    <th class="p-2 text-right" data-sort-col="count" data-sort-type="num">count</th>
  </tr></thead>
  <tbody>
  {% for mod, n in by_module %}
  <tr class="border-b" data-filter-row data-module="{{ (mod or '')|lower }}" data-count="{{ n }}">
    <td class="p-2 font-mono text-xs">…unchanged…</td>
    <td class="p-2 text-right">{{ n }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>
```

**Target templates (one commit each):**

> `project_ideas.html` and `project_evolutions.html` are **handled in Task 6**, not
> here — do not add them to this list.

- [ ] `project_plans.html`
- [ ] `project_tech_debt.html` — has **two** tables: the "Top modules" table (worked
  example above) **and** a second findings-like table earlier in the file. Convert
  **both** (the smoke guard demands every `<table>` opt in).
- [ ] `project_topics.html`
- [ ] `project_notes.html`
- [ ] `project_contracts.html`
- [ ] `project_questions.html`
- [ ] `project_orchestration_list.html` (the `.data-table` run list at `:407` — note
  there are **two** `.data-table` tables in this file; opt both in)

For each: **manual check** sort + filter on that page before committing.

```bash
git commit -am "feat(table-tools): enable sort+filter on <page>"
```

---

## Task 8: Rollout — small / summary tables

Minimum treatment: sortable headers + a single `data-tt-search` box (no per-column
filter row, no persistence key unless useful). Apply to the remaining table
templates:

- [ ] `project_ai_usage.html` (top-sessions, by-agent, learning-recent tables)
- [ ] `global_ai_usage.html`
- [ ] `project_cascade_costs.html`
- [ ] `project_sidecar_findings.html`
- [ ] `project_loops.html`, `project_loops_templates.html`
- [ ] `project_kanban.html`
- [ ] `project_dashboard.html`
- [ ] `session_log.html`
- [ ] `projects.html`, `setup.html`
- [ ] `project_wiki_health.html`
- [ ] `project_rotation.html`
- [ ] `ai_radar.html` / `project_ai_radar.html` (only if they contain a real `<table>`)

Skip any "table" that is a 2–3 row fixed layout where sort is meaningless — but
since the user asked for uniform coverage, default to adding sortable headers
unless the table has a single data row. **Manual check each; commit per page or
small batch.**

```bash
git commit -am "feat(table-tools): enable sort on summary tables (<batch>)"
```

---

## Task 9: Audit capped routes (hybrid boundary)

**Files (read; modify only to relax a cap):**
- `dreaming/routes/project_orchestration.py` (`list_runs(limit=50)`)
- `dreaming/routes/project_session_log.py`
- `dreaming/routes/project_dashboard.py`
- `dreaming/routes/project_kanban.py`
- `dreaming/routes/project_cascade_costs.py`
- `dreaming/routes/project_questions.py`
- `dreaming/routes/ai_radar.py`

- [ ] **Step 1:** For each route, record the cap and the realistic max row count.
- [ ] **Step 2: Decide and document** per route, in a short comment at the cap site:
  either *"cap left as-is; table-tools filters the current page"* (and add a
  `data-tt-search` placeholder hint that says so), or *"cap raised to N because
  full set is small"*. Do NOT add server-side `?sort=&q=` in this plan — that is
  explicitly deferred (spec §Out of scope).
- [ ] **Step 3: Commit** any cap changes.

```bash
git commit -am "chore(table-tools): document/relax row caps for client-side filtering"
```

---

## Task 10: Smoke guard

**Files:**
- Create: `scripts/smoke_table_tools.py`

- [ ] **Step 1: Write the smoke script**

```python
"""Smoke guard for the shared table-tools component.

Cheap, no-network static checks:
  1. Both static assets exist and are non-empty.
  2. table_tools.js exposes the auto-init API and the custom-predicate registry.
  3. base.html loads both assets.
  4. Every shipped <table> in templates/ is either opted into data-table-tools
     or explicitly allow-listed (so a new bare table is caught in review).
"""
from __future__ import annotations
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "dreaming" / "static"
TEMPLATES = ROOT / "dreaming" / "templates"

# Tables intentionally without sort/filter (justify each entry).
ALLOWLIST: set[str] = {
    # Dead/unused template (run detail UI lives in project_orchestration_list.html).
    "project_orchestration_detail.html",
}

def _check_assets() -> None:
    js = (STATIC / "table_tools.js").read_text(encoding="utf-8")
    css = (STATIC / "table_tools.css").read_text(encoding="utf-8")
    assert "querySelectorAll(\"table[data-table-tools]\")" in js, "auto-init selector missing"
    assert "tableToolsFilters" in js, "custom-predicate registry missing"
    assert "table-tools:changed" in js, "change event missing"
    assert "[data-table-tools]" in css, "css not scoped to component"
    print("OK assets present + API intact")

def _check_base_wires() -> None:
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert "/static/table_tools.js" in base, "base.html does not load table_tools.js"
    assert "/static/table_tools.css" in base, "base.html does not load table_tools.css"
    print("OK base.html wires assets")

def _check_tables_opted_in() -> list[str]:
    offenders = []
    for tpl in TEMPLATES.glob("*.html"):
        if tpl.name in ALLOWLIST:
            continue
        html = tpl.read_text(encoding="utf-8")
        for m in re.finditer(r"<table\b[^>]*>", html):
            if "data-table-tools" not in m.group(0):
                offenders.append(f"{tpl.name}: {m.group(0)[:60]}")
    return offenders

def main() -> int:
    _check_assets()
    _check_base_wires()
    offenders = _check_tables_opted_in()
    if offenders:
        print("Tables NOT opted into table-tools (add data-table-tools or ALLOWLIST):")
        for o in offenders:
            print("  -", o)
        return 1
    print("OK all tables opted in")
    print("ALL OK")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it.** `python scripts/smoke_table_tools.py`
  Expected after all rollout tasks: `ALL OK`. (Earlier in the rollout it will list
  un-converted tables — that's the guard doing its job. Run it as a progress meter.)

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke_table_tools.py
git commit -m "test(table-tools): static smoke guard for opt-in + assets"
```

---

## Task 11: Final verification

- [ ] **Step 1:** `python scripts/smoke_table_tools.py` → `ALL OK`.
- [ ] **Step 2:** `python scripts/check_i18n.py` → no errors.
- [ ] **Step 3:** Manual sweep — open findings, ideas, plans, orchestration list,
  one ai-usage page. On each: sort a column, type in search/filter, confirm count +
  empty-state, reload to confirm persistence (where keyed).
- [ ] **Step 4:** Use `superpowers:requesting-code-review` before merge.

---

## Notes for the worker

- **DRY:** all behaviour lives in `table_tools.js`. Templates only declare
  attributes — never add per-table sort/filter JS (the `refs` predicate is the one
  sanctioned exception, via the registry).
- **YAGNI:** no server-side sort/filter, no pagination UI, no multi-column sort.
- **Idempotent:** the component guards with `table.__ttInit`; re-init is safe.
- **Cyrillic files via Write/Edit only.** Run `check_i18n.py` after i18n edits.
- **Commit per task**; keep the bulk `bulk:rows-changed` alias until a later,
  separate cleanup once **all three** original consumers (findings, ideas,
  evolutions — Tasks 5 & 6) are confirmed migrated.
