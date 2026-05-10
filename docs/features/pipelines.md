# Read-only pipelines

Несколько read-only страниц на проекте, которые отображают состояние markdown / JSON артефактов с диска. Все следуют одному паттерну: `resolver.get(setting_key) → list_X(dir) → render`.

## Содержание

- [Tech-Debt](#tech-debt)
- [Product Ideas → Jira](#product-ideas--jira)
- [Contracts](#contracts)
- [Sidecar findings](#sidecar-findings)
- [Wiki](#wiki)
- [Topics (weekly checklist)](#topics-weekly-checklist)
- [Kanban (custom topics)](#kanban-custom-topics)
- [Notes browser](#notes-browser)

## Tech-Debt

**Source**: [`dreaming/services/tech_debt.py`](../../dreaming/services/tech_debt.py), [`project_findings.py`](../../dreaming/routes/project_findings.py), [`project_tech_debt.py`](../../dreaming/routes/project_tech_debt.py).

**Setting**: `tech_debt_dir` (per-project, см. [`configuration.md`](../configuration.md#group-paths-obsidian--artifacts)).

**Layout**: `{tech_debt_dir}/items/TD-*.md` (ALC-style) либо `{tech_debt_dir}/TD-*.md` (flat micode-style). Парсер автоматически фоллбэчит ([`tech_debt.py:73`](../../dreaming/services/tech_debt.py)).

**Frontmatter** (YAML):

```yaml
---
id: TD-042
title: Refactor auth flow
status: open                # open | in_progress | closed
priority: P2                # P0 | P1 | P2 | P3
module: auth
created: 2026-04-01
created_by: alisa-frontend
source: weekly-tech-debt-scan
complexity: M
autonomy: low
confidence: high
release: R12
jira: RGS-1234              # optional
blocked_by: [TD-038, TD-040]
contract: contracts/auth.md
---
```

### Pages

| Method+Path | Описание |
|---|---|
| GET `/p/{slug}/findings` | Список TD items. |
| GET `/p/{slug}/findings/{id}` | Detail с body markdown. |
| POST `/p/{slug}/findings/{id}/close` | `close_tech_debt_item` — переписывает `^status:.*$` на `status: closed`. |
| POST `/p/{slug}/findings/{id}/delete` | `delete_tech_debt_item` — `path.unlink()`. |
| GET `/p/{slug}/tech-debt` | Aggregate: by_status, by_module top-10. |

### close behavior

[`close_tech_debt_item`](../../dreaming/services/tech_debt.py:191):
1. Найти файл (`{td_dir}/{id}.md`, либо через `read_tech_debt_item`).
2. `re.subn(r"(?m)^status:\s*.*$", "status: closed", text, count=1)`.
3. Если match не нашёлся — добавляет в frontmatter (или создаёт frontmatter если его не было).
4. Перезаписывает файл UTF-8.

Это **destructive** — файл изменяется. Бэкап в git'е, не в DC.

## Product Ideas → Jira

**Source**: [`dreaming/services/product_ideas.py`](../../dreaming/services/product_ideas.py), [`project_ideas.py`](../../dreaming/routes/project_ideas.py).

**Setting**: `product_ideas_dir`.

**Frontmatter**:

```yaml
---
id: PI-007
title: Quick OAuth onboarding
status: new                 # new | accepted | rejected | shipped
impact: high                # low | medium | high
effort: M                   # S | M | L | XL
confidence: high
priority: P1
module: auth
user_segment: pro
competitor: Notion
source: research
source_agent: ideas-scanner
created: 2026-04-15
target_release: R12
jira_epic: RGS-9999
jira_task: RGS-1010
jira_ticket: RGS-1010
value_hypothesis: |
  Quicker onboarding -> +5% conversion
---
```

### Pages

| Method+Path | Описание |
|---|---|
| GET `/p/{slug}/ideas?status=` | Board, filter by status. |
| POST `/p/{slug}/ideas/{id}/jira` | Создать Jira Task через `jira.create_task` + persist `jira_ticket: <key>` в frontmatter. |

### Jira flow

`POST /ideas/{item_id}/jira` ([`project_ideas.py:54`](../../dreaming/routes/project_ideas.py)):

1. Найти idea по id (или slug).
2. `jira_pk_override = await resolver.get(project, "jira_project_key", None)` — per-project override.
3. `jira.create_task(settings, summary=f"[{slug}] {title}", item_id, item_url, description, project_key_override, kind="идея")`.
4. Persist key обратно в .md frontmatter:

```python
new_text, n = re.subn(r"(?m)^jira_ticket:\s*.*$", f"jira_ticket: {key}", text, count=1)
if n == 0 and text.startswith("---\n"):
    end = text.find("\n---", 4)
    if end > 0:
        new_text = text[:end] + f"\njira_ticket: {key}" + text[end:]
```

Если Jira не настроен или вернул ошибку — `JiraError` → 400.

## Contracts

**Source**: [`dreaming/services/contracts.py`](../../dreaming/services/contracts.py), [`project_contracts.py`](../../dreaming/routes/project_contracts.py).

**Setting**: `contracts_dir`. Default fallback: `{obsidian_vault}/03-Team/specs/contracts`.

**Frontmatter**:

```yaml
---
kind: module                # module | page | unknown
module: auth
page: ""                     # для kind=page
status: active               # draft | active | deprecated
last_review_at: 2026-04-01
---
```

### Pages

| Method+Path | Описание |
|---|---|
| GET `/p/{slug}/contracts` | Список контрактов. |

Парсер ([`contracts.list_contracts`](../../dreaming/services/contracts.py:43)) сканит `*.md` рекурсивно через `rglob`, скипает `_*.md` и `.*.md`.

## Sidecar findings

**Source**: [`dreaming/services/sidecar_findings.py`](../../dreaming/services/sidecar_findings.py), [`project_sidecar_findings.py`](../../dreaming/routes/project_sidecar_findings.py).

**Setting**: `sidecar_findings_dir`. Default: `{obsidian_vault}/03-Team/sidecar-findings`.

Sidecar reviewers (vera, svetlana, silent-failure-hunter и т.д.) пишут JSON:

```json
[
  {
    "id": "F-001",
    "title": "Missing input validation",
    "severity": "high",
    "module": "auth",
    "file": "src/auth.py",
    "rule": "RULE-XSS-1"
  }
]
```

Поддерживается также формат `{"findings": [...]}` или `{"items": [...]}` ([`sidecar_findings.py:45`](../../dreaming/services/sidecar_findings.py)).

`reviewer` — это `parent_dir.name` либо `file_stem` (sidecar_findings.py:43).

### Pages

| Method+Path | Описание |
|---|---|
| GET `/p/{slug}/sidecar-findings?severity=` | Список с filter by severity. |

## Wiki

**Source**: [`dreaming/services/wiki_data.py`](../../dreaming/services/wiki_data.py), [`project_wiki.py`](../../dreaming/routes/project_wiki.py).

**Setting**: `wiki_dir`.

`get_wiki_status(wiki_dir)` возвращает [`WikiStatus`](../../dreaming/services/wiki_data.py:11):
- `wiki_dir`, `exists`, `domains_count`, `domains` (first 20 names).

Layout: `{wiki_dir}/domains/*.md` либо `{wiki_dir}/*.md` (fallback).

### Pages

| Method+Path | Описание |
|---|---|
| GET `/p/{slug}/wiki` | Status: existence, domains_count, first 20 domains. |
| POST `/p/{slug}/wiki/bootstrap` | Запуск slash-команды `/wiki-bootstrap` через `pm.start_command`. |

### Wiki bootstrap

[`wiki_bootstrap_run`](../../dreaming/routes/project_wiki.py:33) — POST handler:

```python
await pm.start_command(
    project,
    command_name="wiki-bootstrap",
    prompt="/wiki-bootstrap",
    claude_path=settings.claude_path,
    working_dir=project.working_dir,
    model=settings.model,
    max_turns=50,
    timeout_minutes=60,
    env_overrides={
        "DREAMING_PROJECT_SLUG": project.slug,
        "DREAMING_API_URL": f"http://localhost:{settings.port}",
    },
)
```

Composite key в `pm.running`: `cmd:{slug}:wiki-bootstrap`.

После успешного start — 303 на `/p/{slug}/live` чтобы посмотреть live логи. На RuntimeError — 409.

## Topics (weekly checklist)

**Source**: [`dreaming/services/checklist.py`](../../dreaming/services/checklist.py), [`project_topics.py`](../../dreaming/routes/project_topics.py).

**Layout**:
- `{working_dir}/.claude/agents/lessons/_weekly-learning-checklist.md` (preferred)
- `{working_dir}/.claude/agents/_weekly-learning-checklist.md` (fallback)

**Format**:

```markdown
---
week: W18
---
# Learning checklist W18

## Приоритет недели        <- skip
- общая задача             <- skipped

## alisa-frontend
- React 19 hooks
- Тесты с MSW

## vera-reviewer
- OWASP rules
```

Skip-секции: «Приоритет недели», «Общие (любой агент)» — они и подсекции.

`parse_weekly_checklist(text)` возвращает `list[ChecklistTopic]` с `number=1, 2, 3, ...` и `target_agents=[<agent_name>]`.

### Pages

| Method+Path | Описание |
|---|---|
| GET `/p/{slug}/topics` | Read-only weekly checklist. |

Read-only: чтобы редактировать, иди в Obsidian / git'е.

## Kanban (custom topics)

**Source**: [`schema.md`](../schema.md#custom_topics), [`project_kanban.py`](../../dreaming/routes/project_kanban.py).

DB таблица `custom_topics`. Per-проектный CRUD.

### Pages

| Method+Path | Описание |
|---|---|
| GET `/p/{slug}/kanban` | Список (все, включая `active=0`). |
| POST `/p/{slug}/kanban/add` form fields | Добавить topic. |
| POST `/p/{slug}/kanban/{id}/delete` | Удалить. |

Form fields: `title*, module, target_agents (CSV), question, why_important`.

`db.list_custom_topics_for_agent(project_id, agent_name)` ([`db.py:535`](../../dreaming/services/db.py)) делает LIKE-match чтобы найти topics, у которых `target_agents` содержит данное имя.

## Notes browser

**Source**: [`dreaming/services/notes.py`](../../dreaming/services/notes.py), [`project_notes.py`](../../dreaming/routes/project_notes.py).

**Setting**: `learning_notes_dir`. Default: `{working_dir}/.claude/agents/learning-notes`.

`list_notes(notes_dir, max_items=200)` — recursive `*.md`, sort by mtime DESC, top 200.

`read_note(notes_dir, relative_path)` — **path-traversal-safe**:

```python
base = Path(notes_dir).resolve()
target = (base / relative_path).resolve()
if not str(target).startswith(str(base)):
    return None
```

Это блокирует `../../etc/passwd` и т.п.

### Pages

| Method+Path | Описание |
|---|---|
| GET `/p/{slug}/notes` | Список заметок. |
| GET `/p/{slug}/notes/raw?path=...` | Raw text (PlainTextResponse). 404 на path-traversal или not-found. |

## Cross-references

- Settings keys (paths): [`configuration.md`](../configuration.md#group-paths-obsidian--artifacts).
- Schema custom_topics: [`schema.md`](../schema.md#custom_topics).
- Service структура: [`services.md`](../services.md#pipeline-parsers).
