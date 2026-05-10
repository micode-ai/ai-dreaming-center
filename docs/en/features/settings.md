# Settings: global + per-project

DC supports 92 configuration keys (see [`configuration.md`](../configuration.md)). Most of them can be overridden per-project. Chain: project_settings → global → built-in default.

## Contents

- [Override-with-fallback](#override-with-fallback)
- [SETTINGS_GROUPS](#settings_groups)
- [Global UI](#global-ui)
- [Per-project UI](#per-project-ui)
- [Boolean checkbox idiom](#boolean-checkbox-idiom)
- [Secret fields](#secret-fields)
- [ConfigResolver caching](#configresolver-caching)
- [save_yaml flow](#save_yaml-flow)

## Override-with-fallback

Code:

```python
resolver = ConfigResolver(projects, global_settings)
value = await resolver.get(project, "tech_debt_dir", default="")
```

Algorithm ([`config_resolver.py:23`](../../../dreaming/services/config_resolver.py)):

1. If `project` is not None:
   - Loads `project_settings` for the project (caches per-resolver).
   - If `key` is present — returns (decoded JSON value).
2. Else / not in overrides:
   - `getattr(global_settings, key, SENTINEL)`.
   - If != SENTINEL — returns it.
3. Otherwise:
   - If `default == SENTINEL` — returns None.
   - Otherwise — returns `default`.

`SENTINEL = object()` — lets us distinguish "default not given" from "default=None".

To make `resolver` per-request:

```python
resolver = request.app.state.resolver_factory(request)
# the factory creates a fresh ConfigResolver, pure-Python — cheap
```

## SETTINGS_GROUPS

[`dreaming/config.py:140`](../../../dreaming/config.py) — list of 13 groups:

```python
SETTINGS_GROUPS: list[tuple[str, list[str]]] = [
    ("Database", ["db_path"]),
    ("Projects", ["projects_root", "default_locale"]),
    ("Server", ["host", "port"]),
    ("Claude CLI / runners", [...]),
    ("Self-study", [...]),
    ("Scheduling — nightly", [...]),
    ("Scheduling — weekly (opt-in)", [...]),
    ("Watchdogs", [...]),
    ("Paths (Obsidian / artifacts)", [...]),
    ("Jira", [...]),
    ("Harness (orchestration)", [...]),
    ("AI Usage ingest", [...]),
    ("Routing", ["work_routing_mode"]),
]
```

That's the structure for the UI: each group becomes a `<fieldset>` with the heading on the `/settings` and `/p/{slug}/settings` forms. The full table of defaults — in [`configuration.md`](../configuration.md).

## Global UI

`GET /settings` ([`settings.py:46`](../../../dreaming/routes/settings.py)) renders the form, group by `SETTINGS_GROUPS`.

Each field:
- bool → checkbox.
- int → `<input type=number>`.
- float → `<input type=number step=any>`.
- str → `<input type=text>` (or `type=password` if the name contains token/api_key).

`POST /settings` ([`settings.py:57`](../../../dreaming/routes/settings.py)):
1. Iterate over `settings.model_fields` (Pydantic fields).
2. If the field is in form → `_coerce(value, current_default)` → save.
3. If the field is bool and NOT in form → save False (HTML idiom for unchecked).
4. `_save_yaml(new_values)` → merge into `config.yaml`.
5. `request.app.state.settings = type(settings).load()` → reload in-memory.

## Per-project UI

`GET /p/{slug}/settings` ([`project_settings.py:28`](../../../dreaming/routes/project_settings.py)) — for each key of a group renders:

```
+---------------------------------+
| key: tech_debt_dir              |
| Global value: D:\Vault\td       |
| Override:                       |
|  ( ) inherit (use global)       |
|  ( ) override [____________]    |
+---------------------------------+
```

The form submits as:

```
action_tech_debt_dir = "inherit" | "override"
value_tech_debt_dir = "<some path>"
```

`POST /p/{slug}/settings` ([`project_settings.py:58`](../../../dreaming/routes/project_settings.py)):

```python
for group_name, keys in SETTINGS_GROUPS:
    for k in keys:
        action = form.get(f"action_{k}")
        if action == "inherit":
            await svc.unset_setting(project.id, k)
        elif action == "override":
            global_v = getattr(settings, k, "")
            if isinstance(global_v, bool):
                raw = form.get(f"value_{k}", "")
                val = raw.lower() in ("true", "on", "1", "yes")
                await svc.set_setting(project.id, k, val)
            else:
                raw = (form.get(f"value_{k}") or "").strip()
                if raw:
                    val = _coerce(raw, global_v)
                    await svc.set_setting(project.id, k, val)
                else:
                    # empty override → treat as unset
                    await svc.unset_setting(project.id, k)
```

Semantics:
- "inherit" — DELETE the override row.
- "override" with non-empty value — UPSERT.
- "override" with empty value (for non-bool fields) — DELETE (i.e. equivalent to inherit).
- bool override — always saved (true or false).

After save — 303 redirect to the same `/p/{slug}/settings`.

## Boolean checkbox idiom

An HTML checkbox in unchecked state **is not sent** in form data. That creates ambiguity: "not in form" — does that mean "not specified" or "explicitly unchecked"?

In DC there are two solutions for this:

### Global form

[`settings.py:62–70`](../../../dreaming/routes/settings.py):

```python
for k in settings.model_fields:
    if k in form:
        new_values[k] = _coerce(form[k] or "", current_val)
    elif isinstance(getattr(settings, k), bool):
        # Unchecked checkbox — explicit False
        new_values[k] = False
```

For bool — absence = False. For other types — absence = "not specified, don't change". This works because in the global form **every** field is rendered, and a missing non-bool is an explicit empty input (= keep the default).

### Per-project form

In the per-project form every bool field **also** has a hidden input with value="false":

```html
<input type="hidden" name="value_<key>" value="false">
<input type="checkbox" name="value_<key>" value="true">
```

On submit, if checkbox is unchecked — only the hidden "false" is sent. If checked — both are sent and the browser sends the last one (i.e. "true").

Logic in [`project_settings.py:73`](../../../dreaming/routes/project_settings.py): `raw.lower() in ("true", "on", "1", "yes")`.

Standard HTML pattern, works reliably across browsers.

## Secret fields

Fields whose name contains `token`, `api_key`, `secret`, `password` are rendered in the template as `<input type="password">`. Logic — in the Jinja `settings.html` template.

Default secret-field list (see [`configuration.md`](../configuration.md)):
- `codex_api_key`, `anthropic_auth_token`, `anthropic_api_key`, `openai_proxy_api_key`.
- `jira_api_token`.
- `harness_api_key`.

In `config.yaml` they are stored as plain text. **Do not commit** this file to a repository — keep a `.gitignore`. You may prefer env vars (`DC_JIRA_API_TOKEN=...`).

## ConfigResolver caching

[`ConfigResolver._cache: dict[int, dict]`](../../../dreaming/services/config_resolver.py:16) — per-project-ID map to a dict `key → value` from `project_settings`.

Loaded lazily on the first `get(project, ...)`:

```python
async def _project_settings(self, project: Project) -> dict:
    if project.id not in self._cache:
        self._cache[project.id] = await self.projects.all_settings(project.id)
    return self._cache[project.id]
```

`invalidate_project(project_id)` wipes the entry.

**Lifecycle**:
- `resolver_factory(request)` creates a **fresh** `ConfigResolver` per request.
- The cache lives only for the duration of the request.
- Cache is not shared between requests — simple model, no stale-data problems.

If you change `project_settings` at runtime and want to see the change in the current request — manually `resolver.invalidate_project(id)` after set_setting.

`HarnessClientCache.invalidate(project_id)` is a separate story. It holds httpx client instances and they need to be killed when you change `harness_*` settings on the fly. Currently this is called only from tests — in production you have to restart DC if you change a harness URL.

## save_yaml flow

`_save_yaml(values)` ([`settings.py:21`](../../../dreaming/routes/settings.py), [`setup.py:14`](../../../dreaming/routes/setup.py)):

```python
def _save_yaml(values: dict) -> None:
    p = Path("config.yaml")
    cur = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    cur = cur or {}
    cur.update(values)
    p.write_text(yaml.safe_dump(cur, allow_unicode=True), encoding="utf-8")
```

**Important**:
- The path is relative → CWD must be the repo root.
- `allow_unicode=True` so Cyrillic doesn't get escaped.
- UTF-8 without BOM.
- `yaml.safe_dump` sorts keys by default — the file may change in structure after save.

Reload:

```python
request.app.state.settings = type(settings).load()
```

`type(settings)` is `AppSettings`, and `.load()` is a classmethod ([`config.py:131`](../../../dreaming/config.py)).

## Cross-references

- List of all 92 keys: [`configuration.md`](../configuration.md).
- ConfigResolver service: [`services.md`](../services.md#config_resolverpy--configresolver).
- Schema project_settings: [`schema.md`](../schema.md#project_settings).
- Routes: [`routes.md`](../routes.md#settings).
