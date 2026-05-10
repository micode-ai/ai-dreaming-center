# UI language

DC supports Russian (default) and English. Toggle with one button in the header.

## Contents

- [Where the toggle is](#where-the-toggle-is)
- [What gets translated](#what-gets-translated)
- [What does not get translated](#what-does-not-get-translated)
- [Default locale](#default-locale)
- [Add your own language](#add-your-own-language)
- [Report a wrong translation](#report-a-wrong-translation)

## Where the toggle is

In the top-right of the header — a small `EN` button (if you're on Russian) or `RU` (if on English). Click it — language switches.

Technically:
- POST to `/locale` with the `locale` parameter (`ru` or `en`).
- DC sets the `dc_locale` cookie for 1 year.
- Redirect back to the same page (via a hidden `next` field).

The cookie is read on every request, and the Jinja `t()` filter inserts the correct translation. The change does not happen without a page reload — a redirect is required.

## What gets translated

The UI shell — headings, buttons, labels, navigation:
- Page titles ("Проекты" / "Projects").
- Tab names ("Ротация" / "Rotation", "Конспекты" / "Notes", "Тех-долг" / "Tech debt").
- Buttons (`Disable` / `Enable`, "Просканировать" / "Scan", "Сохранить" / "Save").
- Column labels (`agent`, `status`, etc. — although many monospace English ones are left as-is).
- Placeholder text (e.g. on an empty state: "Сессий ещё нет" / "No sessions yet").
- UI-side error messages.

Translation files:
- `dreaming/i18n/messages_ru.json` — Russian.
- `dreaming/i18n/messages_en.json` — English.
- Structure: flat key → value. E.g. `"p.dashboard": "Панель"` (ru) or `"Dashboard"` (en).

## What does not get translated

- **Markdown content** of your agents, notes, tech debt, ideas. DC shows them as-is. If you write a note in English — it stays English regardless of UI locale.
- **Agent names** (`vera`, `svetlana`, `roman`) — these are identifiers, not translated.
- **Project slugs** — same.
- **Technical settings keys** (`claude_path`, `cron_expression`) — code identifiers, should not change.
- **claude's stdout** on `/live` — you see what Claude printed. The language Claude generates in depends on the prompts of your agents.
- **JSON API responses** — engineering surface.

The idea is simple: chrome is translated, content is not touched.

## Default locale

On first visit (when the `dc_locale` cookie does not yet exist) DC takes the default from settings:
- Globally — the `default_locale` key (default `ru`).
- The setup wizard has a "Русский / English" dropdown — your pick is written into `config.yaml` as `default_locale`.

To change the default later — open `/settings` → find `default_locale` → type `ru` or `en` → Save.

## Add your own language

Say you want German. Steps:

1. Create the file `dreaming/i18n/messages_de.json` with the same set of keys as `messages_ru.json` / `messages_en.json`. Translate the values.
2. Register the language in the i18n code (see `dreaming/i18n/__init__.py` or similar — there's a list of supported locales there).
3. Add the option to the setup wizard and the header (currently hard-coded for ru/en).
4. Restart uvicorn.

This is a code change, not configuration. If you're not a developer — fork the repo, add the language, open a PR.

## Report a wrong translation

If a translation is awkward — open an issue in the repository with:
- The English/Russian source.
- The current translation.
- A proposed improvement.

Often translations were done automatically (LLM-translation) and may have missed nuance. Any fixes are welcome.

If you're fixing it yourself — open a PR. The files are small (the current `messages_ru.json` is ~40 lines), easy to parse, no conflicts.

---

See also:
- [`settings.md`](settings.md) — the `default_locale` key.
- Technical: [`../../features/i18n.md`](../../features/i18n.md).
