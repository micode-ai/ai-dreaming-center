# Read-only pipelines

A handful of read-only project pages that display the state of markdown / JSON artifacts on disk. All follow the same pattern: `resolver.get(setting_key) → list_X(dir) → render`.

## Contents

- [Tech-Debt](#tech-debt)
- [Product Ideas → Jira](#product-ideas--jira)
- [Contracts](#contracts)
- [Sidecar findings](#sidecar-findings)
- [Wiki](#wiki)
- [Topics (weekly checklist)](#topics-weekly-checklist)
- [Kanban (custom topics)](#kanban-custom-topics)
- [Notes browser](#notes-browser)

## Tech-Debt

**Source**: [`dreaming/services/tech_debt.py`](../../../dreaming/services/tech_debt.py), [`project_findings.py`](../../../dreaming/routes/project_findings.py), [`project_tech_debt.py`](../../../dreaming/routes/project_tech_debt.py).

**Setting**: `tech_debt_dir` (per-project, see [`configuration.md`](../configuration.md#group-paths-obsidian--artifacts)).

**Layout**: `{tech_debt_dir}/items/TD-*.md` (ALC-style) or `{tech_debt_dir}/TD-*.md` (flat micode-style). The parser auto-falls-back ([`tech_debt.py:73`](../../../dreaming/services/tech_debt.py)).

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

| Method+Path | Description |
|---|---|
| GET `/p/{slug}/findings` | List of TD items. |
| GET `/p/{slug}/findings/{id}` | Detail with body markdown. |
| POST `/p/{slug}/findings/{id}/close` | `close_tech_debt_item` — rewrites `^status:.*$` to `status: closed`. |
| POST `/p/{slug}/findings/{id}/delete` | `delete_tech_debt_item` — `path.unlink()`. |
| GET `/p/{slug}/tech-debt` | Aggregate: by_status, top-10 by_module. |

### close behaviour

[`close_tech_debt_item`](../../../dreaming/services/tech_debt.py:191):
1. Find the file (`{td_dir}/{id}.md`, or via `read_tech_debt_item`).
2. `re.subn(r"(?m)^status:\s*.*$", "status: closed", text, count=1)`.
3. If no match — append into the frontmatter (or create a frontmatter if absent).
4. Rewrite the file UTF-8.

This is **destructive** — the file is changed. Backup lives in git, not in DC.

## Product Ideas → Jira

**Source**: [`dreaming/services/product_ideas.py`](../../../dreaming/services/product_ideas.py), [`project_ideas.py`](../../../dreaming/routes/project_ideas.py).

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

| Method+Path | Description |
|---|---|
| GET `/p/{slug}/ideas?status=` | Board, filter by status. |
| POST `/p/{slug}/ideas/{id}/jira` | Create a Jira Task via `jira.create_task` + persist `jira_ticket: <key>` into the frontmatter. |

### Jira flow

`POST /ideas/{item_id}/jira` ([`project_ideas.py:54`](../../../dreaming/routes/project_ideas.py)):

1. Find the idea by id (or slug).
2. `jira_pk_override = await resolver.get(project, "jira_project_key", None)` — per-project override.
3. `jira.create_task(settings, summary=f"[{slug}] {title}", item_id, item_url, description, project_key_override, kind="идея")`.
4. Persist the key back into the .md frontmatter:

```python
new_text, n = re.subn(r"(?m)^jira_ticket:\s*.*$", f"jira_ticket: {key}", text, count=1)
if n == 0 and text.startswith("---\n"):
    end = text.find("\n---", 4)
    if end > 0:
        new_text = text[:end] + f"\njira_ticket: {key}" + text[end:]
```

If Jira isn't configured or returned an error — `JiraError` → 400.

## Contracts

**Source**: [`dreaming/services/contracts.py`](../../../dreaming/services/contracts.py), [`project_contracts.py`](../../../dreaming/routes/project_contracts.py).

**Setting**: `contracts_dir`. Default fallback: `{obsidian_vault}/03-Team/specs/contracts`.

**Frontmatter**:

```yaml
---
kind: module                # module | page | unknown
module: auth
page: ""                     # for kind=page
status: active               # draft | active | deprecated
last_review_at: 2026-04-01
---
```

### Pages

| Method+Path | Description |
|---|---|
| GET `/p/{slug}/contracts` | List of contracts. |

The parser ([`contracts.list_contracts`](../../../dreaming/services/contracts.py:43)) scans `*.md` recursively via `rglob`, skips `_*.md` and `.*.md`.

## Sidecar findings

**Source**: [`dreaming/services/sidecar_findings.py`](../../../dreaming/services/sidecar_findings.py), [`project_sidecar_findings.py`](../../../dreaming/routes/project_sidecar_findings.py).

**Setting**: `sidecar_findings_dir`. Default: `{obsidian_vault}/03-Team/sidecar-findings`.

Sidecar reviewers (vera, svetlana, silent-failure-hunter, etc.) write JSON:

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

The format `{"findings": [...]}` or `{"items": [...]}` is also supported ([`sidecar_findings.py:45`](../../../dreaming/services/sidecar_findings.py)).

`reviewer` is `parent_dir.name` or `file_stem` (sidecar_findings.py:43).

### Pages

| Method+Path | Description |
|---|---|
| GET `/p/{slug}/sidecar-findings?severity=` | List with severity filter. |

## Wiki

**Source**: [`dreaming/services/wiki_data.py`](../../../dreaming/services/wiki_data.py), [`project_wiki.py`](../../../dreaming/routes/project_wiki.py).

**Setting**: `wiki_dir`.

`get_wiki_status(wiki_dir)` returns [`WikiStatus`](../../../dreaming/services/wiki_data.py:11):
- `wiki_dir`, `exists`, `domains_count`, `domains` (first 20 names).

Layout: `{wiki_dir}/domains/*.md` or `{wiki_dir}/*.md` (fallback).

### Pages

| Method+Path | Description |
|---|---|
| GET `/p/{slug}/wiki` | Status: existence, domains_count, first 20 domains. |
| POST `/p/{slug}/wiki/bootstrap` | Runs the slash command `/wiki-bootstrap` via `pm.start_command`. |

### Wiki bootstrap

[`wiki_bootstrap_run`](../../../dreaming/routes/project_wiki.py:33) — POST handler:

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

Composite key in `pm.running`: `cmd:{slug}:wiki-bootstrap`.

After a successful start — 303 to `/p/{slug}/live` to watch the live logs. On RuntimeError — 409.

## Topics (weekly checklist)

**Source**: [`dreaming/services/checklist.py`](../../../dreaming/services/checklist.py), [`project_topics.py`](../../../dreaming/routes/project_topics.py).

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
- general task             <- skipped

## alisa-frontend
- React 19 hooks
- Tests with MSW

## vera-reviewer
- OWASP rules
```

Skip sections: "Приоритет недели" (Week priority), "Общие (любой агент)" (General (any agent)) — they and their subsections.

`parse_weekly_checklist(text)` returns `list[ChecklistTopic]` with `number=1, 2, 3, ...` and `target_agents=[<agent_name>]`.

### Pages

| Method+Path | Description |
|---|---|
| GET `/p/{slug}/topics` | Read-only weekly checklist. |

Read-only: to edit, go to Obsidian / git.

## Kanban (custom topics)

**Source**: [`schema.md`](../schema.md#custom_topics), [`project_kanban.py`](../../../dreaming/routes/project_kanban.py).

DB table `custom_topics`. Per-project CRUD.

### Pages

| Method+Path | Description |
|---|---|
| GET `/p/{slug}/kanban` | List (all, including `active=0`). |
| POST `/p/{slug}/kanban/add` form fields | Add a topic. |
| POST `/p/{slug}/kanban/{id}/delete` | Delete. |

Form fields: `title*, module, target_agents (CSV), question, why_important`.

`db.list_custom_topics_for_agent(project_id, agent_name)` ([`db.py:535`](../../../dreaming/services/db.py)) does a LIKE match to find topics whose `target_agents` contains the given name.

## Notes browser

**Source**: [`dreaming/services/notes.py`](../../../dreaming/services/notes.py), [`project_notes.py`](../../../dreaming/routes/project_notes.py).

**Setting**: `learning_notes_dir`. Default: `{working_dir}/.claude/agents/learning-notes`.

`list_notes(notes_dir, max_items=200)` — recursive `*.md`, sorted by mtime DESC, top 200.

`read_note(notes_dir, relative_path)` — **path-traversal-safe**:

```python
base = Path(notes_dir).resolve()
target = (base / relative_path).resolve()
if not str(target).startswith(str(base)):
    return None
```

Blocks `../../etc/passwd` and friends.

### Pages

| Method+Path | Description |
|---|---|
| GET `/p/{slug}/notes` | List of notes. |
| GET `/p/{slug}/notes/raw?path=...` | Raw text (PlainTextResponse). 404 on path-traversal or not-found. |

## Cross-references

- Settings keys (paths): [`configuration.md`](../configuration.md#group-paths-obsidian--artifacts).
- Schema custom_topics: [`schema.md`](../schema.md#custom_topics).
- Service structure: [`services.md`](../services.md#pipeline-parsers).
