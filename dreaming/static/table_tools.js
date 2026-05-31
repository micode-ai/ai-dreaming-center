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
    if (col && row.dataset[col] != null) return row.dataset[col].toLowerCase();
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
      var explicit = tbody.querySelector("[data-filter-row]");
      return Array.prototype.slice.call(
        explicit ? tbody.querySelectorAll("[data-filter-row]") : tbody.querySelectorAll("tr"));
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
    var resetBtn = (table.closest("[data-tt-scope]") || table.parentNode || document).querySelector("[data-tt-reset]");
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
