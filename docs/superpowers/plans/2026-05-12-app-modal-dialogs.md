# App Modal Dialogs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all native `confirm()` / `prompt()` calls in templates with a unified data-attribute-driven modal system based on the native `<dialog>` element. Add `appAlert()` + server flash infrastructure for future notice/error messages.

**Architecture:** One global partial `_app_modal.html` containing three `<dialog>` elements (confirm, prompt, alert) and one inline `<script>` with a delegated `submit`/`click` listener that reads `data-confirm` / `data-confirm-input` / `data-confirm-variant` attributes. Included from `base.html`. Server flash via short-lived non-HttpOnly cookie read by the partial's JS on `DOMContentLoaded`. Button labels via existing `t()` i18n filter; modal-body text stays in `data-confirm` attributes (matches current hard-coded style).

**Tech Stack:** Jinja2 templates, Tailwind via CDN (inline classes), native HTML `<dialog>` + `showModal()`, vanilla JS (no new files), Python (FastAPI Response cookies for flash).

**Spec reference:** `docs/superpowers/specs/2026-05-12-app-modal-dialogs-design.md`

**Project note — TDD adaptation:** This project has no test suite by design (see `CLAUDE.md`). Each task's verification step is a **manual smoke check** in the browser, not an automated test. Browser instructions assume the dev server is running: `python -m uvicorn dreaming.main:app --port 8086 --reload` from the repo root.

---

## File Structure

| Path | Action | Responsibility |
|------|--------|----------------|
| `dreaming/templates/_app_modal.html` | create | Three `<dialog>` elements + delegated listener + `appConfirm()` / `appAlert()` + flash-cookie reader |
| `dreaming/templates/base.html` | modify | One `{% include "_app_modal.html" %}` before `</body>` |
| `dreaming/i18n/messages_ru.json` | modify | Add 8 keys under `modal.*` |
| `dreaming/i18n/messages_en.json` | modify | Add 8 keys under `modal.*` |
| `dreaming/lib/flash.py` | create | `set_flash(response, msg, level)` / `read_flash(request)` |
| `dreaming/lib/__init__.py` | create (if missing) | Make `dreaming.lib` a package |
| `scripts/check_no_native_dialogs.py` | create | Guard: zero `confirm(`/`alert(`/`prompt(` in templates |
| 15 templates (see Task 3–5) | modify | Replace `onsubmit`/`onclick` with `data-*` attributes |

**Spec deviation flagged at planning time:** §3.1 of the spec defines `data-confirm-action` / `data-confirm-method` for `<button>` triggers that live outside a `<form>`. After re-checking templates during planning, all six `<button onclick="return confirm(...)">` cases (4 in `project_dashboard.html`, 1 each in `project_orchestration_list.html` and `project_rotation.html`) are **wrapped in a `<form>`**, so Pattern A (move `data-confirm` to the form) covers them. The `data-confirm-action` attributes are still implemented in the listener — small forward-compat cost (~5 lines of JS) — but no template uses them today.

---

## Task 1: i18n keys

**Files:**
- Modify: `dreaming/i18n/messages_ru.json` — append 8 keys
- Modify: `dreaming/i18n/messages_en.json` — append the same 8 keys

- [ ] **Step 1.1: Add RU keys**

Append before the closing `}` of `messages_ru.json` (use the Edit tool — `Set-Content` defaults to UTF-16 LE and will corrupt the file; see `CLAUDE.md`):

```json
  "modal.title.confirm": "Подтверждение",
  "modal.title.alert": "Сообщение",
  "modal.btn.confirm": "Подтвердить",
  "modal.btn.cancel": "Отмена",
  "modal.btn.ok": "ОК",
  "modal.btn.delete": "Удалить",
  "modal.input.placeholder": "Введите значение",
  "modal.input.mismatch": "Значение не совпадает"
```

- [ ] **Step 1.2: Add EN keys**

Mirror the same 8 keys in `messages_en.json`:

```json
  "modal.title.confirm": "Confirm",
  "modal.title.alert": "Notice",
  "modal.btn.confirm": "Confirm",
  "modal.btn.cancel": "Cancel",
  "modal.btn.ok": "OK",
  "modal.btn.delete": "Delete",
  "modal.input.placeholder": "Enter value",
  "modal.input.mismatch": "Value does not match"
```

- [ ] **Step 1.3: Verify i18n parity**

Run: `python scripts/check_i18n.py`
Expected: `OK: locales have identical key sets`

- [ ] **Step 1.4: Commit**

```bash
git add dreaming/i18n/messages_ru.json dreaming/i18n/messages_en.json
git commit -m "i18n(modal): add modal.* keys for app-wide confirm/alert dialogs"
```

---

## Task 2: Build `_app_modal.html` and include in `base.html`

**Files:**
- Create: `dreaming/templates/_app_modal.html`
- Modify: `dreaming/templates/base.html` (insert one include before `</body>`)

- [ ] **Step 2.1: Create the partial**

Use the Write tool (NOT `Set-Content` — Cyrillic content). Full file content:

```html
{# App-wide modal system: confirm / prompt / alert.
   Driven by data-confirm / data-confirm-input / data-confirm-variant attributes
   on <form> or <button>. Also exposes appConfirm(msg, opts) and appAlert(msg, opts)
   for JS callers, and reads a one-shot `flash` cookie set by dreaming.lib.flash. #}

<dialog id="app-confirm-modal" class="app-modal" aria-labelledby="app-confirm-title" aria-describedby="app-confirm-body">
  <div class="bg-white rounded-lg shadow-xl max-w-md w-full">
    <div class="px-5 pt-4 pb-2">
      <h2 id="app-confirm-title" class="font-semibold text-slate-900">{{ "modal.title.confirm" | t(locale=locale) }}</h2>
    </div>
    <div class="px-5 pb-4">
      <p id="app-confirm-body" class="text-sm text-slate-700 whitespace-pre-line"></p>
      <div id="app-confirm-input-wrap" class="mt-3 hidden">
        <input id="app-confirm-input" type="text" class="w-full border rounded p-2 text-sm font-mono"
               placeholder="{{ 'modal.input.placeholder' | t(locale=locale) }}">
        <p id="app-confirm-input-hint" class="mt-1 text-xs text-red-600 hidden">{{ "modal.input.mismatch" | t(locale=locale) }}</p>
      </div>
    </div>
    <div class="px-5 py-3 bg-slate-50 rounded-b-lg flex justify-end gap-2">
      <button type="button" id="app-confirm-cancel" class="text-sm px-3 py-1.5 border rounded text-slate-700 hover:bg-slate-100">{{ "modal.btn.cancel" | t(locale=locale) }}</button>
      <button type="button" id="app-confirm-ok" class="text-sm px-3 py-1.5 rounded text-white"></button>
    </div>
  </div>
</dialog>

<dialog id="app-alert-modal" class="app-modal" aria-labelledby="app-alert-title" aria-describedby="app-alert-body">
  <div class="bg-white rounded-lg shadow-xl max-w-md w-full">
    <div class="px-5 pt-4 pb-2">
      <h2 id="app-alert-title" class="font-semibold text-slate-900">{{ "modal.title.alert" | t(locale=locale) }}</h2>
    </div>
    <div class="px-5 pb-4">
      <p id="app-alert-body" class="text-sm text-slate-700 whitespace-pre-line"></p>
    </div>
    <div class="px-5 py-3 bg-slate-50 rounded-b-lg flex justify-end">
      <button type="button" id="app-alert-ok" class="text-sm px-4 py-1.5 rounded text-white bg-blue-600 hover:bg-blue-700">{{ "modal.btn.ok" | t(locale=locale) }}</button>
    </div>
  </div>
</dialog>

<style>
  dialog.app-modal { padding: 0; border: none; background: transparent; max-width: 28rem; width: calc(100% - 2rem); }
  dialog.app-modal::backdrop { background: rgba(15,23,42,.5); }
</style>

<script>
(function () {
  const I18N = {
    confirm: {{ ("modal.btn.confirm" | t(locale=locale)) | tojson }},
    delete:  {{ ("modal.btn.delete"  | t(locale=locale)) | tojson }},
  };

  const confirmDlg   = document.getElementById('app-confirm-modal');
  const confirmBody  = document.getElementById('app-confirm-body');
  const confirmOk    = document.getElementById('app-confirm-ok');
  const confirmCancel= document.getElementById('app-confirm-cancel');
  const inputWrap    = document.getElementById('app-confirm-input-wrap');
  const inputEl      = document.getElementById('app-confirm-input');
  const inputHint    = document.getElementById('app-confirm-input-hint');

  const alertDlg     = document.getElementById('app-alert-modal');
  const alertBody    = document.getElementById('app-alert-body');
  const alertOk      = document.getElementById('app-alert-ok');

  // ---- core: showConfirm ---------------------------------------------------
  function showConfirm(message, opts) {
    opts = opts || {};
    return new Promise((resolve) => {
      confirmBody.textContent = String(message || '');
      const variant = opts.variant === 'danger' ? 'danger' : 'default';
      const expected = (typeof opts.input === 'string' && opts.input !== '') ? opts.input : null;

      confirmOk.textContent = variant === 'danger' ? I18N.delete : I18N.confirm;
      confirmOk.className = 'text-sm px-3 py-1.5 rounded text-white ' +
        (variant === 'danger' ? 'bg-red-600 hover:bg-red-700' : 'bg-blue-600 hover:bg-blue-700');

      if (expected !== null) {
        inputWrap.classList.remove('hidden');
        inputEl.value = '';
        inputHint.classList.add('hidden');
        confirmOk.disabled = true;
        confirmOk.classList.add('opacity-50', 'cursor-not-allowed');
      } else {
        inputWrap.classList.add('hidden');
        confirmOk.disabled = false;
        confirmOk.classList.remove('opacity-50', 'cursor-not-allowed');
      }

      const cleanup = () => {
        confirmOk.onclick = null;
        confirmCancel.onclick = null;
        inputEl.oninput = null;
        inputEl.onkeydown = null;
        confirmDlg.onclick = null;
        confirmDlg.removeEventListener('cancel', onCancel);
      };
      const onCancel = (e) => { e && e.preventDefault && e.preventDefault(); cleanup(); confirmDlg.close(); resolve(false); };

      confirmOk.onclick     = () => { if (!confirmOk.disabled) { cleanup(); confirmDlg.close(); resolve(true); } };
      confirmCancel.onclick = onCancel;
      confirmDlg.addEventListener('cancel', onCancel);  // ESC
      confirmDlg.onclick    = (e) => { if (e.target === confirmDlg) onCancel(e); };  // backdrop

      if (expected !== null) {
        inputEl.oninput = () => {
          const ok = inputEl.value === expected;
          confirmOk.disabled = !ok;
          confirmOk.classList.toggle('opacity-50', !ok);
          confirmOk.classList.toggle('cursor-not-allowed', !ok);
          inputHint.classList.toggle('hidden', ok || inputEl.value === '');
        };
        inputEl.onkeydown = (e) => { if (e.key === 'Enter' && !confirmOk.disabled) { e.preventDefault(); confirmOk.click(); } };
      }

      confirmDlg.showModal();
      (expected !== null ? inputEl : confirmCancel).focus();
    });
  }

  // ---- core: showAlert -----------------------------------------------------
  function showAlert(message, opts) {
    opts = opts || {};
    return new Promise((resolve) => {
      alertBody.textContent = String(message || '');
      const v = opts.variant;
      alertOk.className = 'text-sm px-4 py-1.5 rounded text-white ' +
        (v === 'error' ? 'bg-red-600 hover:bg-red-700'
         : v === 'success' ? 'bg-green-600 hover:bg-green-700'
         : 'bg-blue-600 hover:bg-blue-700');

      const cleanup = () => { alertOk.onclick = null; alertDlg.onclick = null; alertDlg.removeEventListener('cancel', onClose); };
      const onClose = (e) => { e && e.preventDefault && e.preventDefault(); cleanup(); alertDlg.close(); resolve(); };
      alertOk.onclick = onClose;
      alertDlg.addEventListener('cancel', onClose);
      alertDlg.onclick = (e) => { if (e.target === alertDlg) onClose(e); };

      alertDlg.showModal();
      alertOk.focus();
    });
  }

  // ---- delegated listeners -------------------------------------------------
  function dataOf(el) {
    return {
      message: el.getAttribute('data-confirm'),
      variant: el.getAttribute('data-confirm-variant') || 'default',
      input:   el.getAttribute('data-confirm-input'),
      action:  el.getAttribute('data-confirm-action'),
      method:  (el.getAttribute('data-confirm-method') || 'post').toLowerCase(),
    };
  }

  // Form submit guard
  document.addEventListener('submit', (e) => {
    const form = e.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (!form.hasAttribute('data-confirm')) return;
    e.preventDefault();
    e.stopPropagation();
    const d = dataOf(form);
    showConfirm(d.message, { variant: d.variant, input: d.input }).then((ok) => {
      if (!ok) return;
      form.removeAttribute('data-confirm');
      form.requestSubmit();
    });
  }, true);

  // Button click guard (button has data-confirm but is not inside a confirm-gated form)
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-confirm]');
    if (!btn) return;
    if (!(btn instanceof HTMLButtonElement) && !(btn instanceof HTMLAnchorElement)) return;
    // Skip if button lives inside a form that already has data-confirm — that form's submit listener owns it.
    const ownerForm = btn.closest('form[data-confirm]');
    if (ownerForm) return;
    e.preventDefault();
    e.stopPropagation();
    const d = dataOf(btn);
    showConfirm(d.message, { variant: d.variant, input: d.input }).then((ok) => {
      if (!ok) return;
      if (d.action) {
        const tmp = document.createElement('form');
        tmp.method = d.method;
        tmp.action = d.action;
        tmp.style.display = 'none';
        document.body.appendChild(tmp);
        tmp.submit();
      } else if (btn instanceof HTMLAnchorElement && btn.href) {
        window.location.href = btn.href;
      }
    });
  }, true);

  // ---- flash cookie --------------------------------------------------------
  function readFlashCookie() {
    const m = document.cookie.match(/(?:^|;\s*)flash=([^;]+)/);
    if (!m) return null;
    try { return JSON.parse(decodeURIComponent(m[1])); } catch { return null; }
  }
  function clearFlashCookie() {
    document.cookie = 'flash=; Max-Age=0; Path=/; SameSite=Lax';
  }
  document.addEventListener('DOMContentLoaded', () => {
    const f = readFlashCookie();
    if (f && typeof f.msg === 'string') {
      clearFlashCookie();
      showAlert(f.msg, { variant: f.level || 'info' });
    }
  });

  // ---- public API ----------------------------------------------------------
  window.appConfirm = showConfirm;
  window.appAlert   = showAlert;
})();
</script>
```

- [ ] **Step 2.2: Include the partial from `base.html`**

Edit `dreaming/templates/base.html`: add the include line before `</body>`. Current line 16 reads `</body>`. Replace with:

```html
  {% include "_app_modal.html" %}
</body>
```

- [ ] **Step 2.3: Smoke verification — modal renders, helpers wired**

Start dev server: `python -m uvicorn dreaming.main:app --port 8086 --reload`. Open any project page (e.g. `http://127.0.0.1:8086/`). Open DevTools console and run:

```js
appConfirm("Test message?", {variant: "danger"}).then(r => console.log("result:", r));
```

Expected: red-button confirm modal appears with the message. Click Cancel → console logs `result: false`. Run again, click Delete → `result: true`. ESC and clicking the backdrop both resolve `false`. Then:

```js
appConfirm("Type the name `foo` to continue:", {input: "foo"}).then(r => console.log(r));
```

Expected: input field appears; Confirm button disabled until input value is `foo`; mismatch hint appears while typing wrong value. And:

```js
appAlert("Saved successfully", {variant: "success"});
```

Expected: green-button alert appears.

- [ ] **Step 2.4: Commit**

```bash
git add dreaming/templates/_app_modal.html dreaming/templates/base.html
git commit -m "feat(modal): app-wide _app_modal.html partial with appConfirm/appAlert"
```

---

## Task 3: Migrate simple confirm forms (Pattern A — 9 templates)

These templates use `<form ... onsubmit="return confirm('...');">` only. Mechanical replacement.

**Variant rule:**
- `danger`: Delete, "Force-close ...", "Permanently delete", "Stop", "Kill", "Mark all as cancelled", "Overwrite", "Close question without answer".
- omit (`default`): "Запустить Orchestrator", "Создать GitHub issue", "Continue plan", "Audit contract".

**Files:**
- Modify: `dreaming/templates/project_contracts.html` — 3 forms
- Modify: `dreaming/templates/project_contracts_detail.html` — 3 forms
- Modify: `dreaming/templates/project_findings.html` — 3 forms
- Modify: `dreaming/templates/project_findings_detail.html` — 3 forms
- Modify: `dreaming/templates/project_ideas.html` — 2 forms
- Modify: `dreaming/templates/project_ideas_detail.html` — 2 forms
- Modify: `dreaming/templates/project_plans.html` — 3 forms
- Modify: `dreaming/templates/project_plans_detail.html` — 3 forms
- Modify: `dreaming/templates/project_evolutions.html` — 3 forms
- Modify: `dreaming/templates/project_orchestration_list.html` — 1 form (line ~45; the button-confirm at line ~12 is handled in Task 4)
- Modify: `dreaming/templates/project_orchestration_detail.html` — 1 form
- Modify: `dreaming/templates/project_questions.html` — 1 form

- [ ] **Step 3.1: Per-form replacement**

For each `onsubmit="return confirm('TEXT');"` (or `'TEXT'`), make this exact change:

```diff
- onsubmit="return confirm('TEXT');"
+ data-confirm="TEXT" [data-confirm-variant="danger"]
```

The `data-confirm-variant="danger"` is added only for destructive actions per the variant rule above. Specific call sites and variants:

| File | Line(s) | Action text (verbatim) | Variant |
|---|---|---|---|
| `project_contracts.html` | 49 | `Запустить Orchestrator: аудит контракта «{{ it.name }}» против реального кода?` | default |
| `project_contracts.html` | 55 | `Создать GitHub issue из этого контракта?` | default |
| `project_contracts.html` | 61 | `Удалить файл {{ it.relative_path }}?` | danger |
| `project_contracts_detail.html` | 19 | `Запустить Orchestrator: аудит контракта против реального кода?` | default |
| `project_contracts_detail.html` | 25 | `Создать GitHub issue из этого контракта?` | default |
| `project_contracts_detail.html` | 44 | `Удалить {{ path }}?` | danger |
| `project_findings.html` | 62 | `Запустить Orchestrator с этим finding как целью?` | default |
| `project_findings.html` | 67 | `Создать GitHub issue?` | default |
| `project_findings.html` | 72 | `Удалить {{ it.id }}?` | danger |
| `project_findings_detail.html` | 18 | `Запустить Orchestrator с этим finding как целью?` | default |
| `project_findings_detail.html` | 23 | `Создать GitHub issue из этого finding?` | default |
| `project_findings_detail.html` | 36 | `Удалить {{ item_id }}?` | danger |
| `project_ideas.html` | 62 | `Запустить Orchestrator с этой идеей как целью?` | default |
| `project_ideas.html` | 67 | `Создать GitHub issue?` | default |
| `project_ideas_detail.html` | 20 | `Запустить Orchestrator с этой идеей как целью?` | default |
| `project_ideas_detail.html` | 25 | `Создать GitHub issue из этой идеи?` | default |
| `project_plans.html` | 53 | `Запустить Orchestrator продолжать выполнение «{{ it.title or it.name }}»?` | default |
| `project_plans.html` | 58 | `Создать GitHub issue из этого плана?` | default |
| `project_plans.html` | 63 | `Удалить файл плана {{ it.name }}.md?` | danger |
| `project_plans_detail.html` | 18 | `Запустить Orchestrator продолжать этот план?` | default |
| `project_plans_detail.html` | 23 | `Создать GitHub issue из этого плана?` | default |
| `project_plans_detail.html` | 40 | `Удалить {{ name }}.md?` | danger |
| `project_evolutions.html` | 51 | `Запустить Orchestrator: применить эту правку к ` + backtick + `.claude/agents/{{ it.agent_name }}.md` + backtick + `?` | default |
| `project_evolutions.html` | 57 | `Создать GitHub issue из этого evolution?` | default |
| `project_evolutions.html` | 63 | `Удалить файл {{ it.relative_path }}?` | danger |
| `project_orchestration_list.html` | 45 | `Удалить run {{ r.id[:8] }}…?\nЭто удалит и все его messages/nodes/events. Файлы которые Orchestrator написал на диск — НЕ удаляются.` | danger |
| `project_orchestration_detail.html` | 30 | `Удалить run полностью (вместе с messages/nodes/events)?\nФайлы которые Orchestrator написал на диск НЕ удаляются.` | danger |
| `project_questions.html` | 40 | `Закрыть вопрос без ответа? Агент получит пустую строку.` | danger |

Concrete example (project_contracts.html:48–49 before → after):

```diff
-      <form method="post" action="/p/{{ project.slug }}/contracts/orchestrate" class="inline"
-            onsubmit="return confirm('Запустить Orchestrator: аудит контракта «{{ it.name }}» против реального кода?');">
+      <form method="post" action="/p/{{ project.slug }}/contracts/orchestrate" class="inline"
+            data-confirm="Запустить Orchestrator: аудит контракта «{{ it.name }}» против реального кода?">
```

And for destructive (project_contracts.html:60–61):

```diff
-      <form method="post" action="/p/{{ project.slug }}/contracts/delete" class="inline ml-1"
-            onsubmit="return confirm('Удалить файл {{ it.relative_path }}?')">
+      <form method="post" action="/p/{{ project.slug }}/contracts/delete" class="inline ml-1"
+            data-confirm="Удалить файл {{ it.relative_path }}?" data-confirm-variant="danger">
```

Note: the `\n` in `project_orchestration_detail.html:30` survives as a literal `\n` in the data attribute and renders as a newline via CSS `white-space: pre-line` (already in the partial). No special escaping needed.

- [ ] **Step 3.2: Smoke — exercise each migrated category**

With the dev server running, navigate to and exercise at least one form per migrated file:

- `/p/<slug>/contracts` → click Audit → modal with default Confirm button.
- `/p/<slug>/contracts` → click del → modal with red Delete button.
- `/p/<slug>/findings` → both Orchestrator and del.
- `/p/<slug>/ideas` → both buttons.
- `/p/<slug>/plans` → Orchestrator + del.
- `/p/<slug>/evolutions` → Apply + del.
- `/p/<slug>/orchestration/<id>` → Delete run (multi-line body).
- `/p/<slug>/questions` → Close without answer.

For each: Cancel doesn't submit; Confirm submits and produces the expected redirect.

- [ ] **Step 3.3: Commit**

```bash
git add dreaming/templates/project_contracts.html dreaming/templates/project_contracts_detail.html \
        dreaming/templates/project_findings.html dreaming/templates/project_findings_detail.html \
        dreaming/templates/project_ideas.html dreaming/templates/project_ideas_detail.html \
        dreaming/templates/project_plans.html dreaming/templates/project_plans_detail.html \
        dreaming/templates/project_evolutions.html dreaming/templates/project_orchestration_list.html \
        dreaming/templates/project_orchestration_detail.html dreaming/templates/project_questions.html
git commit -m "refactor(templates): migrate simple confirm() forms to data-confirm attributes"
```

---

## Task 4: Migrate button-confirm forms (Pattern A on enclosing form)

These templates have `<button onclick="return confirm('...')">` where the button is the submit of a wrapping `<form>`. Move `data-confirm` to the `<form>` and drop the `onclick`.

**Files:**
- Modify: `dreaming/templates/project_dashboard.html` — 4 buttons (lines ~64, ~106, ~113, ~134)
- Modify: `dreaming/templates/project_orchestration_list.html` — 1 button (line ~12)
- Modify: `dreaming/templates/project_rotation.html` — 1 button (line ~31)

- [ ] **Step 4.1: project_dashboard.html — line ~62-67 (Force-close all stale)**

```diff
-  <form method="post" action="/p/{{ project.slug }}/sessions/force-close-stale">
-    <button class="text-xs bg-amber-600 text-white rounded px-3 py-1"
-            onclick="return confirm('Mark all running rows for this project as cancelled?');">
+  <form method="post" action="/p/{{ project.slug }}/sessions/force-close-stale"
+        data-confirm="Mark all running rows for this project as cancelled?" data-confirm-variant="danger">
+    <button class="text-xs bg-amber-600 text-white rounded px-3 py-1">
       Force-close all stale
     </button>
   </form>
```

- [ ] **Step 4.2: project_dashboard.html — line ~106 (Stop/Force-close)**

```diff
-      <form method="post" action="/p/{{ project.slug }}/sessions/{{ s.id }}/stop" class="inline">
-        <button class="text-xs border border-amber-500 text-amber-700 rounded px-2 py-1 mr-1"
-                onclick="return confirm('{{ "Stop running process for " if is_live else "Force-close orphan row for " }}{{ s.agent_name }}?');">
+      <form method="post" action="/p/{{ project.slug }}/sessions/{{ s.id }}/stop" class="inline"
+            data-confirm="{{ "Stop running process for " if is_live else "Force-close orphan row for " }}{{ s.agent_name }}?" data-confirm-variant="danger">
+        <button class="text-xs border border-amber-500 text-amber-700 rounded px-2 py-1 mr-1">
```

- [ ] **Step 4.3: project_dashboard.html — line ~113 (Delete session row)**

```diff
-      <form method="post" action="/p/{{ project.slug }}/sessions/{{ s.id }}/delete" class="inline">
-        <button class="text-xs border border-red-400 text-red-700 rounded px-2 py-1"
-                onclick="return confirm('Permanently delete this session row?{{ "  (process is still running — it will be killed first)" if is_live else "" }}');">
+      <form method="post" action="/p/{{ project.slug }}/sessions/{{ s.id }}/delete" class="inline"
+            data-confirm="Permanently delete this session row?{{ "  (process is still running — it will be killed first)" if is_live else "" }}" data-confirm-variant="danger">
+        <button class="text-xs border border-red-400 text-red-700 rounded px-2 py-1">
```

- [ ] **Step 4.4: project_dashboard.html — line ~134 (Kill running)**

```diff
-      <form method="post" action="/p/{{ project.slug }}/live/kill/{{ agent }}" class="inline">
-        <button class="text-xs border border-amber-500 text-amber-700 rounded px-2 py-1"
-                onclick="return confirm('Kill running process for {{ agent }}?');">
+      <form method="post" action="/p/{{ project.slug }}/live/kill/{{ agent }}" class="inline"
+            data-confirm="Kill running process for {{ agent }}?" data-confirm-variant="danger">
+        <button class="text-xs border border-amber-500 text-amber-700 rounded px-2 py-1">
```

- [ ] **Step 4.5: project_orchestration_list.html — line ~12 (Force-close all stale)**

```diff
-  <form method="post" action="/p/{{ project.slug }}/orchestration/force-close-stale">
-    <button class="text-xs bg-amber-600 text-white rounded px-3 py-1"
-            onclick="return confirm('Mark all running orchestration runs for this project as cancelled?');">
+  <form method="post" action="/p/{{ project.slug }}/orchestration/force-close-stale"
+        data-confirm="Mark all running orchestration runs for this project as cancelled?" data-confirm-variant="danger">
+    <button class="text-xs bg-amber-600 text-white rounded px-3 py-1">
```

The second confirm in this file (line ~45, "Удалить run …") is handled by Task 3. After this step, verify both are gone:

```bash
grep -nE "(confirm|prompt|alert)\(" dreaming/templates/project_orchestration_list.html
```

Expected: no matches.

- [ ] **Step 4.6: project_rotation.html — line ~31 (Reinstall starter-kit)**

```diff
-      <form method="post" action="/p/{{ project.slug }}/starter-kit/install" class="mt-2">
+      <form method="post" action="/p/{{ project.slug }}/starter-kit/install" class="mt-2"
+            data-confirm="Overwrite existing starter-kit files with the latest template?" data-confirm-variant="danger">
         <input type="hidden" name="force" value="1">
-        <button class="text-xs border rounded px-2 py-1"
-                onclick="return confirm('Overwrite existing starter-kit files with the latest template?');">
+        <button class="text-xs border rounded px-2 py-1">
           Reinstall (overwrite)
         </button>
       </form>
```

- [ ] **Step 4.7: Smoke**

- `/p/<slug>/dashboard` → trigger all 4 buttons (need a running session row or orphan to exercise some — at minimum click Delete on any session row).
- `/p/<slug>/orchestration` → trigger Force-close all stale + Delete a run.
- `/p/<slug>/rotation` → trigger Reinstall (only visible if starter-kit is installed).

For each: red Delete-style button, Cancel doesn't submit, Confirm submits.

- [ ] **Step 4.8: Commit**

```bash
git add dreaming/templates/project_dashboard.html dreaming/templates/project_orchestration_list.html dreaming/templates/project_rotation.html
git commit -m "refactor(templates): migrate button-onclick confirms to data-confirm on forms"
```

---

## Task 5: Migrate `prompt()` slug guard (projects.html)

**Files:**
- Modify: `dreaming/templates/projects.html` — line 27–30

- [ ] **Step 5.1: Replace the prompt-guarded form**

```diff
-      <form method="post" action="/projects/{{ p.id }}/delete" class="inline"
-            onsubmit="return prompt('Введите slug `{{ p.slug }}` чтобы удалить:')==='{{ p.slug }}'">
+      <form method="post" action="/projects/{{ p.id }}/delete" class="inline"
+            data-confirm="Введите slug `{{ p.slug }}` чтобы подтвердить удаление проекта:"
+            data-confirm-input="{{ p.slug }}"
+            data-confirm-variant="danger">
         <button class="text-xs px-2 py-1 border rounded text-red-600">Delete</button>
       </form>
```

- [ ] **Step 5.2: Smoke**

Navigate to `/projects`. Click Delete on a project (use a throwaway one if needed — or stop before final confirm to avoid actually deleting):

- Modal opens with body text and an input field.
- Delete button is disabled (greyed) until the slug is typed exactly.
- Wrong value → red hint "Значение не совпадает".
- Right value → Delete enables; Enter or click submits and the project is deleted.
- Cancel/ESC/backdrop don't submit.

- [ ] **Step 5.3: Commit**

```bash
git add dreaming/templates/projects.html
git commit -m "refactor(projects): migrate slug-prompt to data-confirm-input modal"
```

---

## Task 6: Server flash infrastructure

**Files:**
- Create: `dreaming/lib/__init__.py` (empty file) — only if `dreaming/lib/` doesn't already exist
- Create: `dreaming/lib/flash.py`

- [ ] **Step 6.1: Check / create the `dreaming/lib/` package**

Cross-platform check (works on Windows PowerShell and POSIX):

```bash
python -c "import pathlib; print(pathlib.Path('dreaming/lib').exists())"
```

If it prints `False`: create `dreaming/lib/__init__.py` as an empty file via the Write tool. If `True`: skip creation, just ensure `__init__.py` exists.

- [ ] **Step 6.2: Write `dreaming/lib/flash.py`**

```python
"""One-shot server flash messages, rendered client-side via _app_modal.html."""
from __future__ import annotations
import json
from typing import Literal
from urllib.parse import quote, unquote

from fastapi import Request
from starlette.responses import Response


Level = Literal["info", "success", "error"]


def set_flash(response: Response, msg: str, level: Level = "info") -> None:
    """Attach a one-shot flash cookie to a response (typically a redirect).

    The cookie is non-HttpOnly because _app_modal.html's client script reads it
    on DOMContentLoaded, then deletes it. Only short, server-authored,
    user-visible text should ever be placed here — never credentials or tokens.

    The JSON payload is URL-encoded so that commas, semicolons, quotes, or
    Cyrillic characters in `msg` survive the cookie round-trip (Starlette's
    set_cookie does not URL-encode values). The client uses decodeURIComponent.
    """
    payload = quote(json.dumps({"msg": msg, "level": level}, ensure_ascii=False))
    response.set_cookie(
        key="flash",
        value=payload,
        max_age=10,
        path="/",
        httponly=False,
        samesite="lax",
    )


def read_flash(request: Request) -> dict | None:
    """Server-side read of the flash cookie. Currently unused — the client owns
    consumption — but provided for routes that may want to render the flash
    inline instead of relying on the modal."""
    raw = request.cookies.get("flash")
    if not raw:
        return None
    try:
        return json.loads(unquote(raw))
    except (json.JSONDecodeError, ValueError):
        return None
```

- [ ] **Step 6.3: Smoke — set a cookie via DevTools, verify modal appears once**

This step requires no server-side change. Start the dev server, open any page, and in DevTools console:

```js
document.cookie = "flash=" + encodeURIComponent(JSON.stringify({msg: "Файл удалён", level: "success"})) + "; Path=/; Max-Age=10; SameSite=Lax";
location.reload();
```

Expected:
1. After reload, a green alert modal appears with "Файл удалён".
2. Click OK to close.
3. Reload the page again. The modal does **not** reappear (cookie was cleared client-side).
4. Run `document.cookie` in console — no `flash=...` entry.

- [ ] **Step 6.4: Commit**

```bash
git add dreaming/lib/__init__.py dreaming/lib/flash.py
git commit -m "feat(flash): server-flash helper (set_flash/read_flash) for one-shot alerts"
```

---

## Task 7: Native-dialog guard script

**Files:**
- Create: `scripts/check_no_native_dialogs.py`

- [ ] **Step 7.1: Write the script**

```python
"""Fail with non-zero exit if any template still uses native confirm/alert/prompt.

Walks dreaming/templates/**/*.html programmatically (no shell glob — works on
Windows PowerShell and POSIX alike). The pattern matches a function call only
(`confirm(`, `alert(`, `prompt(`), so HTML attributes like 'data-confirm=' and
words inside translated strings are not false-positives.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path


PATTERN = re.compile(r"\b(confirm|alert|prompt)\s*\(")


def main() -> int:
    base = Path(__file__).resolve().parent.parent / "dreaming" / "templates"
    bad: list[tuple[Path, int, str]] = []
    for html in base.rglob("*.html"):
        for i, line in enumerate(html.read_text(encoding="utf-8").splitlines(), 1):
            if PATTERN.search(line):
                bad.append((html, i, line.strip()))
    if not bad:
        print("OK: no native confirm/alert/prompt in templates")
        return 0
    print(f"Found {len(bad)} native dialog call(s):")
    for path, lineno, snippet in bad:
        rel = path.relative_to(base.parent.parent)
        print(f"  {rel}:{lineno}: {snippet}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7.2: Run the script — must report zero**

```bash
python scripts/check_no_native_dialogs.py
```

Expected: `OK: no native confirm/alert/prompt in templates` with exit code 0.

If non-zero: list of remaining call sites is printed. Fix them by repeating the Task 3/4/5 pattern, then re-run.

- [ ] **Step 7.3: Commit**

```bash
git add scripts/check_no_native_dialogs.py
git commit -m "chore(scripts): add check_no_native_dialogs.py guard against confirm/alert/prompt regressions"
```

---

## Task 8: Final cross-cutting smoke

- [ ] **Step 8.1: Run both guards**

```bash
python scripts/check_i18n.py
python scripts/check_no_native_dialogs.py
```

Both must print `OK:` and exit 0.

- [ ] **Step 8.2: Full UI smoke sweep**

Dev server running. Walk through each migrated page once and trigger at least one modal:

- `/projects` → Delete a throwaway project (type slug to confirm)
- `/p/<slug>/dashboard` → click Delete on a session row (or another visible action)
- `/p/<slug>/orchestration` → Force-close all stale (if visible) or Delete a run
- `/p/<slug>/contracts` → Audit / Delete
- `/p/<slug>/findings` → Orchestrator / Delete
- `/p/<slug>/ideas` → Orchestrator / GH
- `/p/<slug>/plans` → Orchestrator / Delete
- `/p/<slug>/evolutions` → Apply / Delete
- `/p/<slug>/questions` → Close without answer
- `/p/<slug>/rotation` → Reinstall (if visible)

For each: Cancel doesn't submit; backdrop click doesn't submit; ESC doesn't submit; Confirm/Delete submits and produces expected redirect.

Verify that the existing markdown viewer modal (`dialog.note-modal`) on `/p/<slug>/evolutions` and `/p/<slug>/wiki` still opens and closes correctly — i.e. nothing in our new partial broke it.

- [ ] **Step 8.3: No additional commit needed**

This task is verification only; no code changes.

---

## Out of scope (deferred to future work)

- Adding `set_flash(...)` calls to existing POST handlers — infrastructure is in place but per-handler adoption is separate work, one PR per route group when needed.
- A toast/notification system to replace the alert modal — the `appAlert` API can later be re-pointed at toasts without touching call sites.
- Replacement of `dialog.note-modal` (markdown viewer) with the new pattern — different semantics; out of scope.
