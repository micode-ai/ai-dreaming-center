# App-wide modal dialogs (replace native confirm/prompt/alert)

**Date:** 2026-05-12
**Status:** approved by user; pending spec review.

## Problem

Throughout the dreaming-center UI, user-facing decisions and warnings rely on browser-native dialogs:

- ~29 `confirm(...)` calls in 15 templates, gating form submission for destructive ("Delete", "Force-close", "Cancel all running") and non-destructive ("Run Orchestrator", "Create GitHub issue") actions.
- One `prompt(...)` in `dreaming/templates/projects.html` — type-the-slug guard for project deletion.
- No `alert(...)` today, but flash/error messages are needed in future work and should not introduce yet another visual style.

Native dialogs are visually inconsistent with the rest of the app (Tailwind + custom `<dialog>` modals already in use for markdown viewing), cannot be styled or themed, block the JS thread, and on some platforms behave inconsistently (e.g., line breaks in `confirm()` text).

## Goal

A single, app-wide modal system that:

1. Replaces every existing `confirm(...)` and `prompt(...)` call in templates.
2. Provides infrastructure for future `alert`-style notices (both client-driven and server flash).
3. Uses the existing tech stack — Jinja2 templates, Tailwind via CDN, native HTML `<dialog>` — with no new build steps, no new dependencies, no new static JS files.
4. Is declarative-first: most call sites switch by changing inline `onsubmit="return confirm(...)"` to `data-confirm="..."` attributes.

Out of scope:

- Adding flash messages to existing POST handlers (infrastructure added; per-handler adoption is separate work).
- Touching the existing `dialog.note-modal` (markdown viewer modal) — it has different semantics and stays as-is.
- Tests — the project has no test suite by design; verification is manual smoke checking.

## Existing context

- `dreaming/templates/base.html` includes Tailwind CDN + HTMX 2 + `app.css`.
- `dreaming/static/app.css` already defines `dialog.note-modal { ... }` with a `::backdrop` style, used by `project_evolutions.html`, `project_wiki.html`, `project_notes.html`, `project_topics.html`, `_markdown_partial.html` for markdown viewing modals via `<dialog>.showModal()`.
- i18n: `dreaming/services/i18n.py` loads `dreaming/i18n/messages_{ru,en}.json`. Default locale is RU. `scripts/check_i18n.py` enforces key parity between locales. Templates use `{{ "key" | t(locale=locale) }}`.
- Forms throughout the app are plain HTML POST (no HTMX on the affected forms), with confirmation gated via `onsubmit="return confirm('…')"`.

## Design

### 1. Components

**New files:**

- `dreaming/templates/_app_modal.html` — single partial holding three `<dialog>` elements (confirm, prompt, alert) plus a single `<script>` block with the listener and the `appConfirm` / `appAlert` JS helpers. ~150 lines. Tailwind classes inline (matches project convention; no new CSS).
- `dreaming/lib/flash.py` — `set_flash(response, msg, level="info")` and `read_flash(request) -> dict|None`. ~20 lines. Stores a JSON-encoded short-lived cookie (`Max-Age=10`, `SameSite=Lax`, non-HttpOnly so the partial's JS can read it).

**Modified files:**

- `dreaming/templates/base.html` — `{% include "_app_modal.html" %}` placed immediately before `</body>`.
- `dreaming/i18n/messages_ru.json` + `dreaming/i18n/messages_en.json` — 8 new keys under the `modal.*` prefix.
- 15 templates listed in §5 — replace inline `onsubmit`/`onclick` with `data-*` attributes.

**Unchanged:**

- `dreaming/static/app.css` (everything via Tailwind inline, matching the rest of the project).
- `dialog.note-modal` and the markdown-viewer modals.
- Existing route handlers (server-flash adoption is per-handler work outside this spec).

### 2. i18n keys

Added to both `messages_ru.json` and `messages_en.json`:

| Key | RU | EN |
|---|---|---|
| `modal.title.confirm` | Подтверждение | Confirm |
| `modal.title.alert` | Сообщение | Notice |
| `modal.btn.confirm` | Подтвердить | Confirm |
| `modal.btn.cancel` | Отмена | Cancel |
| `modal.btn.ok` | ОК | OK |
| `modal.btn.delete` | Удалить | Delete |
| `modal.input.placeholder` | Введите значение | Enter value |
| `modal.input.mismatch` | Значение не совпадает | Value does not match |

The button shown for confirm depends on `data-confirm-variant`: `danger` uses `modal.btn.delete`, other variants use `modal.btn.confirm`. Cancel and the input strings are common.

The body text of each prompt (e.g., "Удалить файл X?") stays hard-coded in the `data-confirm` attribute of the call site — it's the specific question, not a label, and is already in RU today.

### 3. Public API

#### 3.1 Declarative — the primary migration path

```html
<!-- confirm: form submit guard -->
<form method="post" action="/.../delete"
      data-confirm="Удалить файл X?"
      data-confirm-variant="danger">…</form>

<!-- confirm: button click (button outside any form or with its own action) -->
<button type="button"
        data-confirm="Force-close orphan row for X?"
        data-confirm-action="/.../close"
        data-confirm-method="post"
        data-confirm-variant="danger">×</button>

<!-- type-to-confirm (replaces prompt() guard) -->
<form method="post" action="/projects/{id}/delete"
      data-confirm="Введите slug `my-slug` чтобы подтвердить удаление проекта:"
      data-confirm-input="my-slug"
      data-confirm-variant="danger">…</form>
```

Attribute reference:

| Attribute | Required | Values | Effect |
|---|---|---|---|
| `data-confirm` | yes | string | Body text shown in modal. Presence triggers the listener. |
| `data-confirm-variant` | no | `default` (default) / `danger` | Controls confirm-button label (Confirm vs Delete) and styling (red vs neutral). |
| `data-confirm-input` | no | string | Switches to prompt-modal. User must type this exact value to enable the confirm button. |
| `data-confirm-action` | no | URL | For `<button>` triggers: target action when synthesizing a POST. Ignored on `<form>`. |
| `data-confirm-method` | no | `post` (default) / `get` | Method for the synthesized form. Ignored on `<form>`. |

#### 3.2 Imperative — for future JS-driven code

```js
appConfirm(message, {variant: "danger", input: "my-slug"})
  .then(ok => { if (ok) … });

appAlert(message, {variant: "success"});  // variant: 'info' | 'success' | 'error'
```

Both return a Promise. `appConfirm` resolves to `true` (user confirmed) or `false` (cancelled / ESC / backdrop). `appAlert` resolves to `undefined` once the user closes the modal (callers can `await` to chain UI work after acknowledgement, but typically don't). They use the same three `<dialog>` elements as the declarative path; they are wrappers around `dialog.showModal()` plus a one-shot event listener that resolves the promise.

#### 3.3 Server flash

```python
# In a route handler:
from dreaming.lib.flash import set_flash

@router.post("/p/{slug}/contracts/delete")
async def delete_contract(...):
    ...
    response = RedirectResponse("/p/{slug}/contracts", status_code=303)
    set_flash(response, "Файл удалён", level="success")
    return response
```

`set_flash` writes a cookie `flash={"msg":"...","level":"..."}` with `Max-Age=10`, `SameSite=Lax`. The partial's JS reads the cookie on `DOMContentLoaded`, deletes the cookie via `document.cookie = "flash=; Max-Age=0; ..."`, and calls `appAlert(msg, {variant: level})`. The cookie's short max-age plus client-side deletion ensures each flash is shown once.

The cookie is intentionally non-HttpOnly (the partial's JS must read it). Threat model: flash payload is always server-authored, short user-visible text only — never credentials, tokens, or sensitive data. Rendering goes through the modal's text content (`textContent`, not `innerHTML`), so XSS via flash message is not possible even if a handler were ever to interpolate user input directly into a flash. Implementers should still avoid putting raw user input in flash messages as a hygiene rule.

Server-flash adoption in handlers is **out of scope** for this spec — the infrastructure is added so future PRs can opt in.

### 4. Data flow

#### 4.1 Confirm on a form

```
[user clicks submit button]
  → submit event on <form data-confirm="...">
  → global listener: e.preventDefault(), e.stopPropagation()
  → dialog.showModal() with body from data-confirm; focus → Cancel button
  → user: clicks Confirm, or Cancel, or Esc, or backdrop
  → on Confirm:
       - remove data-confirm attribute from form (prevents listener recursion)
       - form.requestSubmit() → standard POST
  → on Cancel/Esc/backdrop: dialog.close(); form not submitted
```

Removing the attribute is the simplest re-entry guard. Re-adding it after the form actually submits is unnecessary — the page is about to navigate.

#### 4.2 Confirm on a button (outside a form)

```
[user clicks button data-confirm + data-confirm-action]
  → click event
  → global listener: e.preventDefault()
  → dialog.showModal()
  → on Confirm:
       - synthesize hidden <form method=[data-confirm-method] action=[data-confirm-action]>
         appended to body
       - copy any data-confirm-field-* attributes into hidden inputs (extension point)
       - form.submit()
```

Used only when a button is genuinely not inside a form (rare — see §5.3 for the four cases in `project_dashboard.html` / `project_rotation.html`).

#### 4.3 Prompt (type-to-confirm)

```
[submit/click → listener detects data-confirm-input is set]
  → dialog.showModal() with body, label, and <input type="text" required>
  → Confirm button is disabled until input.value === data-confirm-input (live `input` event)
  → Enter key in input triggers Confirm (only if enabled)
  → on Confirm: same submission flow as 4.1 / 4.2
```

#### 4.4 Alert (flash via cookie)

```
[handler] set_flash(response, "Файл удалён", "success")
  → Set-Cookie: flash={"msg":"...","level":"success"}; Max-Age=10; SameSite=Lax; Path=/
  → 303 redirect to listing page
[next page] base.html renders, _app_modal.html script:
  → DOMContentLoaded: read 'flash' cookie
  → if present: JSON.parse, delete cookie, appAlert(msg, {variant: level})
```

#### 4.5 ESC / backdrop / focus

- ESC: native `<dialog>` fires `cancel` event → resolve `false` (confirm/prompt) or `undefined` (alert).
- Backdrop click: detected via `e.target === dialog` (same pattern as `project_evolutions.html:115-116`). Same resolution as ESC.
- Initial focus: Cancel button for confirm/prompt (safe default — Enter does not trigger destructive actions); OK button for alert; input field for prompt.
- Focus trap and tab order: handled natively by `<dialog>`. No manual key handling.
- `aria-labelledby` → modal title; `aria-describedby` → body paragraph.

### 5. Migration

#### 5.1 Templates touched (per grep at 2026-05-12)

| File | confirm | prompt | button-confirm |
|---|---:|---:|---:|
| `dreaming/templates/project_contracts.html` | 3 | — | — |
| `dreaming/templates/project_contracts_detail.html` | 3 | — | — |
| `dreaming/templates/project_findings.html` | 3 | — | — |
| `dreaming/templates/project_findings_detail.html` | 3 | — | — |
| `dreaming/templates/project_ideas.html` | 2 | — | — |
| `dreaming/templates/project_ideas_detail.html` | 2 | — | — |
| `dreaming/templates/project_plans.html` | 3 | — | — |
| `dreaming/templates/project_plans_detail.html` | 3 | — | — |
| `dreaming/templates/project_evolutions.html` | 3 | — | — |
| `dreaming/templates/project_orchestration_list.html` | 1 | — | 1 |
| `dreaming/templates/project_orchestration_detail.html` | 1 | — | — |
| `dreaming/templates/project_dashboard.html` | — | — | 4 |
| `dreaming/templates/project_questions.html` | 1 | — | — |
| `dreaming/templates/project_rotation.html` | — | — | 1 |
| `dreaming/templates/projects.html` | — | 1 | — |
| **Total** | **28** | **1** | **6** |

#### 5.2 Replacement patterns

**A. Form with `onsubmit="return confirm('...')"`** (majority — 25+ call sites):

```diff
- <form method="post" action="..." onsubmit="return confirm('Удалить X?');">
+ <form method="post" action="..." data-confirm="Удалить X?" data-confirm-variant="danger">
```

Variant assignment:

- `danger` — Delete, Force-close, "Mark all as cancelled", "Stop running process", "Overwrite", "Kill running process", "Permanently delete", project deletion.
- `default` (attribute can be omitted) — "Run Orchestrator", "Create GitHub issue", "Continue plan", "Close question without answer", "Audit contract".

**B. `<button>` with `onclick="return confirm('...')"` inside a `<form>`** (1 case — `project_orchestration_list.html:12`):

```diff
- <button onclick="return confirm('Mark all running...?');">
+ <button data-confirm="Mark all running...?" data-confirm-variant="danger">
```

The listener catches `click` on the button before the form `submit` fires; same effect as on the form itself.

**C. `<button>` with `onclick="return confirm('...')"` and `formaction`/wrapping form** (4 cases in `project_dashboard.html` lines 64, 106, 113, 134 + 1 in `project_rotation.html:31`):

Each case is reviewed individually during implementation. Two sub-cases:

- If the button submits an enclosing form: move `data-confirm` to that form (pattern A).
- If the button needs its own action: add `data-confirm-action` + `data-confirm-method` (pattern B variant for buttons outside forms).

**D. `prompt()` for slug confirmation** (1 case — `projects.html:28`):

```diff
- <form method="post" action="/projects/{{ p.id }}/delete"
-       onsubmit="return prompt('Введите slug `{{ p.slug }}` чтобы удалить:')==='{{ p.slug }}'">
+ <form method="post" action="/projects/{{ p.id }}/delete"
+       data-confirm="Введите slug `{{ p.slug }}` чтобы подтвердить удаление проекта:"
+       data-confirm-input="{{ p.slug }}"
+       data-confirm-variant="danger">
```

#### 5.3 Post-migration check

A grep guard:

```bash
grep -nE '\b(confirm|alert|prompt)\s*\(' dreaming/templates/**/*.html
```

Must return zero matches after migration. To make this enforceable, add a small check to `scripts/check_i18n.py` (or a new `scripts/check_no_native_dialogs.py`) that fails manual-smoke if any match remains. The script is run manually like the other smoke checks (there is no CI in this project). Note: on Windows PowerShell the recursive glob may not expand; the script should walk `dreaming/templates/**/*.html` programmatically (e.g., `pathlib.Path.glob`) rather than relying on the shell.

### 6. Verification

The project has no test suite. Manual smoke checks after implementation:

1. For each of the 15 affected templates, exercise at least one trigger:
   - The custom modal opens with correct body text and locale-correct buttons.
   - ESC, Cancel, and backdrop-click close the modal; the underlying action does **not** execute.
   - Confirm executes the action and produces the expected redirect/state change.
2. On `/projects` — attempt to delete a project: typing a wrong slug keeps Confirm disabled; the correct slug enables it and triggers the deletion.
3. Trigger a server flash from one handler (temporary scaffold for verification — reverted after smoke): set a flash, follow the redirect, see the alert modal appear once and not on subsequent loads.
4. `grep` guard from §5.4 returns zero matches.
5. `python scripts/check_i18n.py` passes (RU/EN parity holds with the new keys).

### 7. Trade-offs and rejected alternatives

**Overriding `window.confirm` / `window.prompt` / `window.alert`.** Rejected: these APIs are synchronous; a modal is inherently asynchronous. The only way to fake sync is a hidden re-submit flag pattern, which is more invasive than just changing the call sites to declarative attributes.

**A JS helper function (`appConfirm(event, this, msg)` called from `onsubmit`).** Rejected: keeps inline JS, more boilerplate per call site than data-attributes, and provides no advantage given that the migration is mechanical either way.

**Per-page modal partials.** Rejected: would multiply DOM, complicate keyboard/focus handling, and split the implementation across 15 files instead of one.

**External library (SweetAlert2 etc.).** Rejected: adds a dependency, breaks the no-build no-NPM philosophy of the project, and the native `<dialog>` already does what we need.

**Building a real toast/notification system instead of `alert`-modal.** Considered but deferred: toasts have different ergonomics (auto-dismiss, stacking, non-modal) and are not what the user asked for. The current modal-based alert is sufficient for the flash use-case; a toast system can be added later if needed without re-touching the call sites that use `appAlert` (the function can later route to a toast).

## Acceptance criteria

- `dreaming/templates/_app_modal.html` exists and is included from `base.html`.
- `dreaming/lib/flash.py` exists with `set_flash` and `read_flash`.
- All 8 new i18n keys exist in both `messages_ru.json` and `messages_en.json`; `scripts/check_i18n.py` passes.
- All 15 listed templates have been migrated to `data-confirm` / `data-confirm-input` attributes.
- `grep -nE '\b(confirm|alert|prompt)\s*\(' dreaming/templates/**/*.html` returns zero matches.
- Manual smoke checks pass (§6).
- The existing `dialog.note-modal` (markdown viewer) continues to work unchanged.
