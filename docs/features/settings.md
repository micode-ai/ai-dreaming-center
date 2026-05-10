# Settings: global + per-project

DC поддерживает 92 ключа конфигурации (см. [`configuration.md`](../configuration.md)). Большая часть может быть override'нута per-project. Чейн: project_settings → global → built-in default.

## Содержание

- [Override-with-fallback](#override-with-fallback)
- [SETTINGS_GROUPS](#settings_groups)
- [Global UI](#global-ui)
- [Per-project UI](#per-project-ui)
- [Boolean checkbox idiom](#boolean-checkbox-idiom)
- [Secret поля](#secret-поля)
- [ConfigResolver caching](#configresolver-caching)
- [save_yaml flow](#save_yaml-flow)

## Override-with-fallback

Code:

```python
resolver = ConfigResolver(projects, global_settings)
value = await resolver.get(project, "tech_debt_dir", default="")
```

Алгоритм ([`config_resolver.py:23`](../../dreaming/services/config_resolver.py)):

1. Если `project` is not None:
   - Загружает `project_settings` для проекта (cache'ит per-resolver).
   - Если `key` есть — возвращает (decoded JSON value).
2. Иначе/нет в overrides:
   - `getattr(global_settings, key, SENTINEL)`.
   - Если != SENTINEL — возвращает.
3. Иначе:
   - Если `default == SENTINEL` — возвращает None.
   - Иначе — возвращает `default`.

`SENTINEL = object()` — позволяет различать «default не передан» от «default=None».

Чтобы делать `resolver` per-request:

```python
resolver = request.app.state.resolver_factory(request)
# фабрика создаёт fresh ConfigResolver, pure-Python — дёшево
```

## SETTINGS_GROUPS

[`dreaming/config.py:140`](../../dreaming/config.py) — список из 13 групп:

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

Это структура для UI: каждая группа становится `<fieldset>` с заголовком в формах `/settings` и `/p/{slug}/settings`. Полная таблица defaults — в [`configuration.md`](../configuration.md).

## Global UI

`GET /settings` ([`settings.py:46`](../../dreaming/routes/settings.py)) рендерит форму, group by `SETTINGS_GROUPS`.

Каждое поле:
- bool → checkbox.
- int → `<input type=number>`.
- float → `<input type=number step=any>`.
- str → `<input type=text>` (или `type=password` если имя содержит token/api_key).

`POST /settings` ([`settings.py:57`](../../dreaming/routes/settings.py)):
1. Iterate over `settings.model_fields` (Pydantic поля).
2. Если поле есть в form → `_coerce(value, current_default)` → save.
3. Если поле — bool и НЕТ в form → save False (HTML idiom для unchecked).
4. `_save_yaml(new_values)` → merge в `config.yaml`.
5. `request.app.state.settings = type(settings).load()` → reload in-memory.

## Per-project UI

`GET /p/{slug}/settings` ([`project_settings.py:28`](../../dreaming/routes/project_settings.py)) — для каждого ключа группы рендерит:

```
+---------------------------------+
| key: tech_debt_dir              |
| Global value: D:\Vault\td       |
| Override:                       |
|  ( ) inherit (use global)       |
|  ( ) override [____________]    |
+---------------------------------+
```

Форма submit'ится как:

```
action_tech_debt_dir = "inherit" | "override"
value_tech_debt_dir = "<some path>"
```

`POST /p/{slug}/settings` ([`project_settings.py:58`](../../dreaming/routes/project_settings.py)):

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

Семантика:
- "inherit" — DELETE override row.
- "override" с непустым value — UPSERT.
- "override" с пустым value (для не-bool полей) — DELETE (т.е. эквивалентно inherit).
- bool override — всегда сохраняется (true или false).

После save — 303 redirect на ту же `/p/{slug}/settings`.

## Boolean checkbox idiom

HTML checkbox при unchecked состоянии **не отправляется** в form data. Это создаёт неоднозначность: «не было в form» — это «не указал» или «явно убрал галочку»?

В DC оба варианта решения:

### Global form

[`settings.py:62–70`](../../dreaming/routes/settings.py):

```python
for k in settings.model_fields:
    if k in form:
        new_values[k] = _coerce(form[k] or "", current_val)
    elif isinstance(getattr(settings, k), bool):
        # Unchecked checkbox — explicit False
        new_values[k] = False
```

То есть для bool — отсутствие = False. Для остальных типов — отсутствие = «не указал, не меняем». Это работает потому что в global form **все** поля выводятся, и невыставленный non-bool — explicit empty input (= оставляем default).

### Per-project form

В per-project form каждое bool-поле **также** имеет hidden input с value="false":

```html
<input type="hidden" name="value_<key>" value="false">
<input type="checkbox" name="value_<key>" value="true">
```

При отправке если checkbox unchecked — отправится только hidden с "false". Если checked — оба, а browser отправляет последний (т.е. "true").

Логика в [`project_settings.py:73`](../../dreaming/routes/project_settings.py): `raw.lower() in ("true", "on", "1", "yes")`.

Это standard HTML pattern и работает в браузерах надёжно.

## Secret поля

Поля, имя которых содержит `token`, `api_key`, `secret`, `password` — рендерятся в шаблоне как `<input type="password">`. Логика — в Jinja-шаблоне `settings.html`.

Список secret-полей по умолчанию (см. [`configuration.md`](../configuration.md)):
- `codex_api_key`, `anthropic_auth_token`, `anthropic_api_key`, `openai_proxy_api_key`.
- `jira_api_token`.
- `harness_api_key`.

В `config.yaml` они хранятся в plain text. **Не коммить** этот файл в репозиторий — у тебя должен быть `.gitignore`. Можно предпочесть env vars (`DC_JIRA_API_TOKEN=...`).

## ConfigResolver caching

[`ConfigResolver._cache: dict[int, dict]`](../../dreaming/services/config_resolver.py:16) — per-project ID мап на словарь `key → value` из `project_settings`.

Загружается лениво при первом `get(project, ...)`:

```python
async def _project_settings(self, project: Project) -> dict:
    if project.id not in self._cache:
        self._cache[project.id] = await self.projects.all_settings(project.id)
    return self._cache[project.id]
```

`invalidate_project(project_id)` — стирает запись.

**Жизненный цикл**:
- `resolver_factory(request)` создаёт **fresh** `ConfigResolver` per-request.
- Кэш живёт только в течение request'а.
- Между requests'ами cache не делится — простая модель, нет проблем с stale-данными.

Если меняешь `project_settings` runtime'ом и хочешь сразу видеть в текущем request — вручную `resolver.invalidate_project(id)` после set_setting.

`HarnessClientCache.invalidate(project_id)` — отдельная история. Она хранит инстансы httpx-клиентов, и их нужно прибить если меняешь `harness_*` настройки на лету. В текущем коде она вызывается только из тестов — на production придётся перезапускать DC если меняешь harness URL.

## save_yaml flow

`_save_yaml(values)` ([`settings.py:21`](../../dreaming/routes/settings.py), [`setup.py:14`](../../dreaming/routes/setup.py)):

```python
def _save_yaml(values: dict) -> None:
    p = Path("config.yaml")
    cur = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    cur = cur or {}
    cur.update(values)
    p.write_text(yaml.safe_dump(cur, allow_unicode=True), encoding="utf-8")
```

**Important**:
- Path относительный → CWD должен быть корнем проекта.
- `allow_unicode=True` чтобы Cyrillic не escape'ился.
- UTF-8 без BOM.
- `yaml.safe_dump` сортирует ключи по умолчанию — после save файл может измениться по structure.

Reload:

```python
request.app.state.settings = type(settings).load()
```

`type(settings)` — это `AppSettings`, а `.load()` — classmethod ([`config.py:131`](../../dreaming/config.py)).

## Cross-references

- Список всех 92 ключей: [`configuration.md`](../configuration.md).
- ConfigResolver service: [`services.md`](../services.md#config_resolverpy--configresolver).
- Schema project_settings: [`schema.md`](../schema.md#project_settings).
- Routes: [`routes.md`](../routes.md#settings).
