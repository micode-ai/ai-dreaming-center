# Article Pipeline Wave B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An article about one project can be published on another project's site, the user can state a topic and intro prompt themselves, and the writer can ask a question and wait for the answer.

**Architecture:** A proposal's `project_id` becomes its *subject*; a new nullable `target_project_id` plus a per-project `article_venue_project` setting name its *venue*. Approve and publish read every article setting from the venue and run in the venue's article root, while the card, the queue row and the questions stay with the subject. Two new UI actions (add-article, set-venue) and one new instruction block in `write-article.md` (ask via the existing questions API) complete it.

**Tech Stack:** FastAPI + Jinja2 + aiosqlite, `ProcessManager.start_command`, the existing `orchestrator_questions` API.

**Spec:** `docs/superpowers/specs/2026-08-20-article-cross-project-design.md`
**Extends:** `docs/superpowers/specs/2026-08-20-article-pipeline-design.md` (wave A, merged as `7abb776`)
**Issue:** https://github.com/micode-ai/ai-dreaming-center/issues/35

## Global Constraints

- `scripts/smoke_articles.py` is the only test vehicle (no pytest in this repo) and must exit 0. Verify with `python scripts/smoke_articles.py; echo "EXIT=$?"` — never pipe into `tail` or `head`, or you read that command's exit code instead of python's.
- Keep printed smoke output inside the cp1250 console codepage: no arrows (`→`), check marks or box drawing in `print()`. Write `->`. Em dashes and Cyrillic are fine.
- `python scripts/check_i18n.py` must print `OK: locales have identical key sets`; `python scripts/check_css_tokens.py` must print `ALL OK`; `python -c "import dreaming.main"` must exit 0.
- User-facing strings go through `{{ "key" | t(locale=locale) }}`; every RU key needs its EN mirror. RU is the default locale.
- Cyrillic content must be written with your file-editing tools as UTF-8 — never PowerShell `Set-Content`, which defaults to UTF-16 LE and corrupts the i18n parser.
- Modern Starlette signature: `templates.TemplateResponse(request, "name.html", {ctx_without_request})`. Routes read `request.state.project`.
- **`target_project_id` NULL must behave exactly as wave A did.** Every task's smoke work includes not breaking that.
- **Do not mutate `data/dreaming.db`.** It is the user's live database and holds real article proposals. Build state in a temp database, or create `smoke-` prefixed rows and clean them up.
- Do not weaken `article_publish.py`'s path validator, its `--literal-pathspecs` flags, the no-`-f` decision, or the pathspec-scoped commit. Do not change the publish gate's three cases.
- Do not run the slash-commands (they spawn paid Claude sessions) and never run the publish path against a real repository.
- **Never `git commit --amend`, never `git reset` or rebase.** Add new commits.

---

### Task 1: `target_project_id`, the venue setting, and venue resolution

**Files:**
- Modify: `dreaming/services/db.py` (the `article_proposals` table in the SCHEMA string; `add_article_proposal`; a new setter)
- Modify: `dreaming/services/articles.py` (new `resolve_venue_id`)
- Modify: `dreaming/config.py` (`article_venue_project` field + the `("Articles", [...])` group)
- Modify: `scripts/smoke_articles.py`

**Interfaces:**
- Consumes: `SqliteDB`, `ProjectsService.list_all(only_enabled=True)`
- Produces:
  - column `article_proposals.target_project_id INTEGER` (nullable)
  - `db.add_article_proposal(..., target_project_id: int | None = None)` — the existing signature gains one keyword-only parameter at the end
  - `db.set_article_proposal_venue(proposal_id: int, target_project_id: int | None) -> bool` — only while the row is `proposed`
  - `articles.resolve_venue_id(subject_id: int, override_id: int | None, configured_slug: str, enabled: list) -> int` — pure, no I/O; `enabled` is a list of objects with `.id` and `.slug`
  - setting `article_venue_project: str = ""`

- [ ] **Step 1: Write the failing smoke checks**

Append inside `main()` in `scripts/smoke_articles.py`, before `print("PASS")`:

```python
        # ── venue resolution (pure) ────────────────────────────────
        class _P:
            def __init__(self, pid, slug): self.id, self.slug = pid, slug
        enabled = [_P(1, "subject"), _P(2, "venue"), _P(3, "other")]
        cases = [
            # (override, configured slug, expected)
            (2,    "other",   2),  # override wins over the setting
            (None, "venue",   2),  # setting used when no override
            (None, "",        1),  # neither -> the subject itself
            (None, "missing", 1),  # unknown slug -> subject, not an error
            (99,   "venue",   2),  # override naming no enabled project -> setting
            (99,   "",        1),  # ... and then the subject
        ]
        for override, configured, want in cases:
            got = articles.resolve_venue_id(1, override, configured, enabled)
            if got != want:
                fail(f"resolve_venue_id(1, {override}, {configured!r}) = {got}, want {want}")
                return 1
        print("ok: resolve_venue_id -- override > setting > subject, unknown falls back")

        # ── target_project_id round-trip ───────────────────────────
        vid = await db.add_article_proposal(
            pid, source="manual", source_ref="",
            evidence="controller smoke: venue column round-trip",
            title="Venue column", angle="", slug_hint="smoke-venue-column",
            target_project_id=pid,
        )
        row = await db.get_article_proposal(vid)
        if row["target_project_id"] != pid:
            fail(f"target_project_id not persisted: {row['target_project_id']}")
            return 1
        plain = await db.add_article_proposal(
            pid, source="manual", source_ref="",
            evidence="controller smoke: default venue is NULL",
            title="No venue", angle="", slug_hint="smoke-venue-null",
        )
        row = await db.get_article_proposal(plain)
        if row["target_project_id"] is not None:
            fail(f"default target_project_id = {row['target_project_id']!r}, want None")
            return 1
        if not await db.set_article_proposal_venue(plain, pid):
            fail("set_article_proposal_venue returned False on a proposed row")
            return 1
        if (await db.get_article_proposal(plain))["target_project_id"] != pid:
            fail("set_article_proposal_venue did not persist")
            return 1
        await db.set_article_proposal_status(plain, "published")
        if await db.set_article_proposal_venue(plain, None):
            fail("set_article_proposal_venue must refuse a non-proposed row")
            return 1
        print("ok: target_project_id defaults to NULL, round-trips, and is "
              "settable only while proposed")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/smoke_articles.py; echo "EXIT=$?"`
Expected: `AttributeError: module 'dreaming.services.articles' has no attribute 'resolve_venue_id'`

- [ ] **Step 3: Add the column**

In `dreaming/services/db.py`, add to the `article_proposals` CREATE TABLE, after `project_id`:

```sql
    target_project_id INTEGER,
```

Then add a migration line next to the other schema statements, because the table already exists in the user's database and `CREATE TABLE IF NOT EXISTS` will not alter it. Look for how this repo handles added columns — search for `ALTER TABLE` in `db.py`. If there is an established pattern, follow it exactly. If there is none, add the column with a guarded `ALTER TABLE` executed after the schema script, in a small helper that catches the "duplicate column name" error and moves on, with a comment saying why the guard is there.

**This step is load-bearing: without it every article page 500s against the existing database.** Verify by running the smoke script and by `python -c "import asyncio; from dreaming.services.db import SqliteDB; asyncio.run(SqliteDB('data/dreaming.db').connect())"` — read-only, that is a connect, not a write.

- [ ] **Step 4: Extend the writers**

`add_article_proposal` gains a keyword-only `target_project_id: int | None = None` and inserts it. The new setter, next to the other article methods:

```python
    async def set_article_proposal_venue(
        self, proposal_id: int, target_project_id: int | None,
    ) -> bool:
        """Point a proposal at a venue. Only while it is still `proposed`:
        once a writer has been dispatched the venue decided where it ran and
        what format it learned, so moving it afterwards would describe a
        different article than the one on disk."""
        async with self._conn.execute(
            "UPDATE article_proposals SET target_project_id=? "
            "WHERE id=? AND status='proposed'",
            (target_project_id, proposal_id),
        ) as cur:
            n = cur.rowcount
        await self._conn.commit()
        return n > 0
```

- [ ] **Step 5: Add the resolver**

In `dreaming/services/articles.py`:

```python
def resolve_venue_id(
    subject_id: int, override_id: int | None, configured_slug: str, enabled: list,
) -> int:
    """Which project's repository receives this article.

    Order: the proposal's own override, then the subject's
    `article_venue_project` setting, then the subject itself. A value naming
    no enabled project falls back rather than failing — a disabled venue
    should not make a proposal unapprovable, and the page displays whatever
    this returns so the fallback is visible instead of silent.
    """
    by_id = {p.id: p for p in enabled}
    by_slug = {p.slug: p for p in enabled}
    if override_id is not None and override_id in by_id:
        return override_id
    slug = (configured_slug or "").strip()
    if slug and slug in by_slug:
        return by_slug[slug].id
    return subject_id
```

- [ ] **Step 6: Add the setting**

In `dreaming/config.py`, next to the other article keys:

```python
    article_venue_project: str = ""
```

and add `"article_venue_project"` to the `("Articles", [...])` group so it surfaces per-project.

- [ ] **Step 7: Run the checks**

Run: `python scripts/smoke_articles.py; echo "EXIT=$?"` → EXIT=0 with the two new `ok:` lines
Run: `python -c "from dreaming.config import AppSettings; print(repr(AppSettings().article_venue_project))"` → `''`
Run: `python -c "import dreaming.main"` → exit 0

- [ ] **Step 8: Commit**

```bash
git add dreaming/services/db.py dreaming/services/articles.py dreaming/config.py scripts/smoke_articles.py
git commit -m "feat(articles): target_project_id, the venue setting, and venue resolution

Refs #35"
```

---

### Task 2: Approve and publish read the venue

**Files:**
- Modify: `dreaming/routes/project_articles.py` (`articles_page`, `articles_approve`, `articles_publish`)
- Modify: `scripts/smoke_articles.py`

**Interfaces:**
- Consumes: `articles.resolve_venue_id`, `articles.resolve_article_root`, `articles.session_blog_dir`, `articles.resolve_writer`, `db.get_article_proposal`
- Produces: a single helper in `project_articles.py` used by all three routes —
  `async def _venue_for(request, project, row) -> tuple[object, str]` returning the venue project object and its `article_blog_dir`. Every article setting after this point is read against the venue.

- [ ] **Step 1: Write the failing smoke check**

The interesting behaviour is which settings get read. Assert it without spawning a session, by driving the resolution the routes use:

```python
        # ── the venue's settings are the ones that count ───────────
        # A subject with no blog dir but a venue that has one must be
        # approvable; the reverse must not be.
        from dreaming.services import articles as _a
        enabled = [_P(pid, "subject"), _P(pid + 1000, "venue")]
        venue_id = _a.resolve_venue_id(pid, pid + 1000, "", enabled)
        if venue_id != pid + 1000:
            fail(f"venue_id = {venue_id}, want {pid + 1000}")
            return 1
        print("ok: venue id resolves for a subject that is not the venue")
```

Then add a route-level check in the existing `with TestClient(app) as client:` block:

```python
            # A proposal whose venue has no article_blog_dir must be refused
            # with 400 naming the venue, not silently dispatched.
            r = client.post(f"/p/ai-dreaming-center/articles/{api_id}/approve",
                            follow_redirects=False)
            if r.status_code not in (400, 409):
                fail(f"approve without a venue blog dir: {r.status_code}, want 400/409")
                return 1
        print("ok: approve refuses before dispatch when the venue has no blog dir")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/smoke_articles.py; echo "EXIT=$?"`
Expected: the first new check fails with `AttributeError` if Task 1 is not in, otherwise the route check fails because `api_id` is `drafted` rather than dispatchable — read the failure, and if it is the status guard rather than the venue, adjust the fixture to a `proposed` row you created and clean up.

- [ ] **Step 3: Add the venue helper**

In `dreaming/routes/project_articles.py`:

```python
async def _venue_for(request, project, row) -> tuple[object, str]:
    """Resolve a proposal's venue project and that venue's blog dir.

    The subject owns the card, the queue row and the questions; the venue owns
    the repository the article lands in, so every article setting from here on
    is read against the venue. With no override and no `article_venue_project`
    this returns the subject itself, which is exactly wave A's behaviour.
    """
    resolver = request.app.state.resolver_factory(request)
    enabled = await request.app.state.projects.list_all(only_enabled=True)
    configured = await resolver.get(project, "article_venue_project", "")
    venue_id = articles.resolve_venue_id(
        project.id, row.get("target_project_id") if row else None,
        configured, enabled,
    )
    venue = next((p for p in enabled if p.id == venue_id), project)
    blog_dir = await resolver.get(venue, "article_blog_dir", "")
    return venue, blog_dir
```

- [ ] **Step 4: Rewire the three routes**

In `articles_approve`: call `_venue_for` after the status and starter-kit guards, and replace every subsequent `project`-scoped read with the venue —
`article_writer_agent`, `article_verify_cmd`, `article_locales`, `article_max_turns`,
`article_timeout_minutes`, `claude_path`, `model`, and `resolve_article_root(venue.working_dir, blog_dir)`.
Pass `working_dir=root` as now. The 400 for a missing blog dir must name the venue:
`f"article_blog_dir is not set for venue '{venue.slug}' — nowhere to put the article"`.
Add to `env_overrides`:

```python
                "DC_ARTICLE_SUBJECT_DIR": project.working_dir,
                "DC_ARTICLE_SUBJECT_SLUG": project.slug,
```

Leave `DREAMING_PROJECT_SLUG` as `project.slug` — the subject — and add a comment saying why: the write-back and any question must reach the proposal's own project, not the venue's.

The starter-kit check moves to the **venue**: the `write-article` command has to exist where the session will run. Keep the existing message but name the venue.

In `articles_publish`: resolve the venue the same way and read `article_verify_cmd`, `article_publish_mode` and the article root from it.

In `articles_page`: resolve the venue per row for the writer label and the gate, and pass `venue_slug` per row so the card can show it. The page-level `writer` value should use the page's default venue (no override), so a project with no proposals still shows something truthful.

- [ ] **Step 5: Show the venue on the card**

In `dreaming/templates/_article_card.html`, in the header row after the status badge:

```html
    {% if a.venue_slug and a.venue_slug != project.slug %}
      <span class="badge badge-brand" title="{{ 'article.venue.hint' | t(locale=locale) }}">
        {{ "article.venue" | t(locale=locale) }}: {{ a.venue_slug }}
      </span>
    {% endif %}
```

i18n, both files:

RU: `"article.venue": "площадка"`, `"article.venue.hint": "Репозиторий, в который попадёт статья"`
EN: `"article.venue": "venue"`, `"article.venue.hint": "The repository the article lands in"`

- [ ] **Step 6: Run the checks**

`python scripts/smoke_articles.py; echo "EXIT=$?"` → EXIT=0
`python scripts/check_i18n.py` → OK
`python scripts/check_css_tokens.py` → ALL OK
Render `/p/ai-dreaming-center/articles` and `/p/test/articles` via TestClient → both 200

- [ ] **Step 7: Commit**

```bash
git add dreaming/routes/project_articles.py dreaming/templates/_article_card.html \
        dreaming/i18n/messages_ru.json dreaming/i18n/messages_en.json scripts/smoke_articles.py
git commit -m "feat(articles): approve and publish read the venue's settings

Refs #35"
```

---

### Task 3: `write-article.md` learns subject and venue

**Files:**
- Modify: `templates/starter-kit/commands/write-article.md`
- Modify: `scripts/smoke_articles.py`

- [ ] **Step 1: Write the failing check**

```python
        kit = ROOT / "templates" / "starter-kit" / "commands" / "write-article.md"
        body = kit.read_text(encoding="utf-8")
        for needle in ("DC_ARTICLE_SUBJECT_DIR", "DC_ARTICLE_SUBJECT_SLUG"):
            if needle not in body:
                fail(f"write-article.md does not mention {needle}")
                return 1
        print("ok: write-article.md documents the subject directory")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/smoke_articles.py; echo "EXIT=$?"` → fails on the first needle.

- [ ] **Step 3: Write the instruction**

Add a section near the top of the command, after the brief is read. Keep the file's register. It must say, in your own words:

- The session's own working directory is the **venue** — the repository whose site publishes the piece. Its posts, its format, its build, its git repository.
- `$DC_ARTICLE_SUBJECT_DIR` is the repository the article is **about**. Read it for the material: commits, code, specs, closed work. Read-only — never write there, never commit there.
- When the two are the same directory (the common case) nothing changes.
- The format always comes from the venue, never from the subject. A subject with markdown docs does not make the venue's JSON-data blog accept a markdown file.

Do not change the `draft_ref` contract, the typography rules, the verification honesty rule, or the "never commit and never push" rule.

- [ ] **Step 4: Run the check** → EXIT=0

- [ ] **Step 5: Commit**

```bash
git add templates/starter-kit/commands/write-article.md scripts/smoke_articles.py
git commit -m "docs(articles): tell the writer to read the subject and write in the venue's format

Refs #35"
```

---

### Task 4: The manual add-article form

**Files:**
- Modify: `dreaming/routes/project_articles.py` (new route)
- Modify: `dreaming/templates/project_articles.html` (the form)
- Modify: both i18n files
- Modify: `scripts/smoke_articles.py`

**Interfaces:**
- Produces: `POST /p/{slug}/articles/add` — form fields `title`, `angle`, `venue` (a slug, optional)

- [ ] **Step 1: Write the failing check**

In the `TestClient` block:

```python
            blank = client.post("/p/ai-dreaming-center/articles/add",
                                data={"title": "   ", "angle": "x"},
                                follow_redirects=False)
            if blank.status_code != 400:
                fail(f"manual add with a blank topic: {blank.status_code}, want 400")
                return 1
            made = client.post("/p/ai-dreaming-center/articles/add",
                               data={"title": "Smoke manual topic",
                                     "angle": "an intro prompt from the operator",
                                     "venue": ""},
                               follow_redirects=False)
            if made.status_code != 303:
                fail(f"manual add: {made.status_code}, want 303")
                return 1
        # the row must carry honest, non-blank evidence naming the request
        made_row = None
        for r in await real_db.list_article_proposals(status="proposed"):
            if r["slug_hint"].startswith("smoke-manual") or r["title"] == "Smoke manual topic":
                made_row = r
                break
        if made_row is None:
            fail("manual proposal was not created")
            return 1
        if made_row["source"] != "manual" or not made_row["evidence"].strip():
            fail(f"manual row: source={made_row['source']}, evidence={made_row['evidence']!r}")
            return 1
        if "an intro prompt from the operator" not in made_row["angle"]:
            fail("the intro prompt did not reach the angle")
            return 1
        await real_db.execute("DELETE FROM article_proposals WHERE id=?", (made_row["id"],))
        print("ok: manual add -- blank topic refused, row carries honest evidence")
```

Reuse whatever the existing block already calls the direct DB handle; if it is not named `real_db`, match the existing name.

- [ ] **Step 2: Run it to verify it fails** → 404 (route missing)

- [ ] **Step 3: Implement the route**

```python
@router.post("/p/{slug}/articles/add")
async def articles_add(
    request: Request, slug: str,
    title: str = Form(...), angle: str = Form(""), venue: str = Form(""),
):
    """A human states the topic. `source='manual'`, and the evidence says so.

    The API's blank-evidence 400 exists because a queue of unfalsifiable
    suggestions is worse than an empty one. A person asking for an article is
    a checkable fact about why the proposal exists, so we record exactly that
    and never dress it up as a commit or a measurement.
    """
    project = request.state.project
    db = request.app.state.db
    topic = title.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic required")
    prompt = angle.strip()
    enabled = await request.app.state.projects.list_all(only_enabled=True)
    venue_id = None
    if venue.strip():
        match = next((p for p in enabled if p.slug == venue.strip()), None)
        if match is None:
            raise HTTPException(status_code=404, detail=f"project {venue} not found")
        venue_id = match.id
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    evidence = f"requested by hand on {stamp}"
    if prompt:
        evidence += f": {prompt[:300]}"
    slug_hint = articles.slugify(topic) or f"manual-{int(datetime.now(timezone.utc).timestamp())}"
    new_id = await db.add_article_proposal(
        project.id, source="manual", source_ref="", evidence=evidence,
        title=topic[:300], angle=prompt, slug_hint=slug_hint,
        target_project_id=venue_id,
    )
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    resp = RedirectResponse(f"/p/{project.slug}/articles", status_code=303)
    key = "article.flash.duplicate" if new_id is None else "article.flash.proposed"
    set_flash(resp, request.app.state.i18n.t(key, locale=locale),
              level="info" if new_id is None else "success")
    return resp
```

Add `from datetime import datetime, timezone` and `Form` / `set_flash` imports if the file does not already have them — check first.

- [ ] **Step 4: Add the form**

In `dreaming/templates/project_articles.html`, after the header and before the groups:

```html
<details class="card mb-4">
  <summary class="text-sm cursor-pointer strong">{{ "article.add.title" | t(locale=locale) }}</summary>
  <form method="post" action="/p/{{ project.slug }}/articles/add" class="mt-3 flex flex-col gap-2">
    <input type="text" name="title" required
           placeholder="{{ 'article.add.topic' | t(locale=locale) }}"
           class="rounded px-2 py-1 bg-elevated text-sm">
    <textarea name="angle" rows="3"
              placeholder="{{ 'article.add.prompt' | t(locale=locale) }}"
              class="rounded px-2 py-1 bg-elevated text-sm"></textarea>
    <div class="flex items-center gap-2 text-xs">
      <label>{{ "article.venue" | t(locale=locale) }}</label>
      <select name="venue" class="rounded px-2 py-1 bg-elevated">
        <option value="">{{ "article.venue.default" | t(locale=locale) }}</option>
        {% for p in projects %}<option value="{{ p.slug }}">{{ p.label }}</option>{% endfor %}
      </select>
      <button class="btn btn-sm btn-primary">{{ "article.add.submit" | t(locale=locale) }}</button>
    </div>
  </form>
</details>
```

Before writing, run `grep -n "details\|summary" dreaming/static/components.css dreaming/templates/*.html | head` to see whether `<details>` is used elsewhere and styled; if it is not, use a plain `div` with the form always visible rather than introducing an unstyled disclosure widget.

i18n, both files:

RU: `"article.add.title": "Добавить статью"`, `"article.add.topic": "Тема"`, `"article.add.prompt": "Вводный промпт — что важно сказать, на что опереться"`, `"article.add.submit": "Предложить"`, `"article.venue.default": "по умолчанию для проекта"`
EN: `"article.add.title": "Add an article"`, `"article.add.topic": "Topic"`, `"article.add.prompt": "Intro prompt — what matters, what to build on"`, `"article.add.submit": "Propose"`, `"article.venue.default": "the project's default"`

- [ ] **Step 5: Run all three checks** → smoke EXIT=0, i18n OK, css ALL OK

- [ ] **Step 6: Commit**

```bash
git add dreaming/routes/project_articles.py dreaming/templates/project_articles.html \
        dreaming/i18n/messages_ru.json dreaming/i18n/messages_en.json scripts/smoke_articles.py
git commit -m "feat(articles): add an article by hand, with honest manual evidence

Refs #35"
```

---

### Task 5: Set a proposal's venue from the card

**Files:**
- Modify: `dreaming/routes/project_articles.py` (new route)
- Modify: `dreaming/templates/_article_card.html`
- Modify: both i18n files
- Modify: `scripts/smoke_articles.py`

**Interfaces:**
- Produces: `POST /p/{slug}/articles/{proposal_id}/venue` — form field `venue` (slug; empty clears the override)

- [ ] **Step 1: Write the failing check**

```python
        # setting a venue is allowed while proposed, refused afterwards
        vrow = await db.add_article_proposal(
            pid, source="manual", source_ref="",
            evidence="controller smoke: venue route", title="Venue route",
            angle="", slug_hint="smoke-venue-route",
        )
        if not await db.set_article_proposal_venue(vrow, pid):
            fail("venue setter refused a proposed row")
            return 1
        await db.set_article_proposal_status(vrow, "writing")
        if await db.set_article_proposal_venue(vrow, None):
            fail("venue setter must refuse a writing row")
            return 1
        print("ok: venue is settable only before the writer is dispatched")
```

- [ ] **Step 2: Run it** → passes only once Task 1's setter exists; if it already passes, note that and move to the route check, adding a `TestClient` POST asserting 303 on a `proposed` row and 409 on a `writing` one.

- [ ] **Step 3: Implement the route**

Mirror `articles_reject`'s shape: 404 when the row is missing or belongs to another project, then call the setter, then 409 if it returns `False` (meaning the row was not `proposed`), then redirect to the articles page. An empty `venue` clears the override — that is not an error.

- [ ] **Step 4: Add the selector to the card**

Only for a `proposed` row, in the footer next to the approve/reject buttons:

```html
      <form method="post" action="/p/{{ project.slug }}/articles/{{ a.id }}/venue"
            class="inline flex items-center gap-1">
        <select name="venue" class="text-xs rounded px-1 py-1 bg-elevated">
          <option value="">{{ "article.venue.default" | t(locale=locale) }}</option>
          {% for p in projects %}<option value="{{ p.slug }}"
            {% if a.venue_slug == p.slug %}selected{% endif %}>{{ p.label }}</option>{% endfor %}
        </select>
        <button class="btn btn-sm">{{ "article.venue.set" | t(locale=locale) }}</button>
      </form>
```

i18n: RU `"article.venue.set": "Площадка"`, EN `"article.venue.set": "Set venue"`.

- [ ] **Step 5: Run all three checks** → green

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(articles): choose a proposal's venue before approving it

Refs #35"
```

---

### Task 6: The question channel

**Files:**
- Modify: `templates/starter-kit/commands/write-article.md`
- Modify: `dreaming/routes/project_articles.py` (`articles_page` — pending-question flag)
- Modify: `dreaming/templates/_article_card.html`
- Modify: both i18n files
- Modify: `scripts/smoke_articles.py`

**Interfaces:**
- Consumes: the existing `POST /api/questions/create` (`project_slug`, `tool_use_id`, `question`, `options`) and `GET /api/questions/{id}/poll` (`status`, `answer_text`); `db.list_pending_questions` if it exists — check `dreaming/services/db.py` for the accessor `project_questions.py` uses, and reuse it rather than writing a second query.

- [ ] **Step 1: Write the failing checks**

```python
        body = (ROOT / "templates" / "starter-kit" / "commands" / "write-article.md").read_text(encoding="utf-8")
        for needle in ("/api/questions/create", "poll", "tool_use_id"):
            if needle not in body:
                fail(f"write-article.md does not document {needle}")
                return 1
        print("ok: write-article.md documents the question channel")
```

Plus a page-level check: create a pending question for the project, render `/p/{slug}/articles` with a `writing` row, and assert the page mentions the waiting state. Clean up both rows afterwards.

- [ ] **Step 2: Run it to verify it fails**

- [ ] **Step 3: Write the instruction**

A section in `write-article.md`. It must say:

- Use it when a fact the piece needs cannot be established from the venue or the subject — a number, a client name, a claim about behaviour. `blog-writer.md`'s own rule already forbids inventing these; this is the channel for obeying it.
- `POST $DREAMING_API_URL/api/questions/create` with `project_slug` set to `$DREAMING_PROJECT_SLUG` (the subject — that is the page the user is looking at), a `tool_use_id` unique to this question, the question text, and optional `options`.
- Poll `GET $DREAMING_API_URL/api/questions/{id}/poll` until `status` is no longer `pending`, with a sleep between polls. While a question is pending the session will not be killed for silence, so waiting is safe.
- On `answered`, use `answer_text`. On `dismissed`, or if the answer never comes, **do not invent the fact** — report failure through the write-back's `error_message`, naming the question that went unanswered. An article that ships around the fact it asked about is the fabrication this pipeline exists to prevent.
- Ask sparingly: two or three questions in one run, not a interrogation.

Include a concrete `curl` for both calls, with the JSON-escaping caveat the sibling commands carry.

- [ ] **Step 4: Surface the wait on the page**

In `articles_page`, fetch the subject project's pending questions once and pass a boolean; in the card, for a `writing` row, show a line with a link to `/p/{{ project.slug }}/questions`.

i18n: RU `"article.waiting_answer": "Писатель ждёт вашего ответа"`, EN `"article.waiting_answer": "The writer is waiting for your answer"`.

- [ ] **Step 5: Run all three checks** → green

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(articles): let the writer ask, and show when it is waiting

Refs #35"
```

---

### Task 7: Verification pass and the wave record

**Files:**
- Modify: `docs/ru/waves.md`, `docs/en/waves.md`
- Modify: whatever the pass turns up

- [ ] **Step 1: Run everything**

```bash
python scripts/smoke_articles.py; echo "EXIT=$?"
python scripts/smoke_ai_radar.py; echo "EXIT=$?"
python scripts/check_i18n.py
python scripts/check_css_tokens.py
python -c "import dreaming.main"
```

All must be green. `smoke_ai_radar.py` matters because the radar card is shared.

- [ ] **Step 2: Render every touched page**

```bash
python - <<'PY'
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
from starlette.testclient import TestClient
from dreaming.main import app
urls = ['/articles', '/ai-radar', '/p/ai-dreaming-center/articles', '/p/test/articles',
        '/p/accounting-ai-agent/articles', '/p/ai-dreaming-center/questions',
        '/settings', '/p/test/settings']
with TestClient(app) as c:
    bad = [(u, c.get(u).status_code) for u in urls]
    for u, s in bad: print(s, u)
    assert all(s == 200 for _, s in bad), [b for b in bad if b[1] != 200]
print("ALL PAGES 200")
PY
```

- [ ] **Step 3: Confirm the wave A regression**

A proposal with `target_project_id` NULL and no `article_venue_project` must resolve its venue to the subject itself, read the subject's settings, and derive the same article root wave A did. Assert it explicitly against the three configured projects, and record the output.

- [ ] **Step 4: Record the wave**

Add a `## Wave B — Article cross-project` entry to both waves docs, following the shape of the Wave A entry directly above it: branch and range, spec and plan links, the problem in two paragraphs, what shipped, the defects review caught, acceptance, and what stayed deferred. Be honest about the live end-to-end still not having run.

- [ ] **Step 5: Commit**

```bash
git add docs/en/waves.md docs/ru/waves.md
git commit -m "docs(waves): record the article cross-project wave

Closes #35"
```

---

## Self-Review

**Spec coverage.** Subject/venue columns, setting and resolution → Task 1; the routes reading the venue → Task 2; the writer's subject-vs-venue instruction → Task 3; the manual feeder → Task 4; the venue selector → Task 5; the question channel and the waiting indicator → Task 6; testing and the record → Task 7. The spec's out-of-scope list stays out: no add-project-by-path, no editing published pieces, no platform publishing, no changes to the validator or the publish gate.

**Placeholders.** None. Four steps deliberately say "read the existing code first" rather than inventing: the `ALTER TABLE` pattern in Task 1 (the table already exists in the user's database, and guessing the migration idiom would be worse than reading it), the `<details>` styling question in Task 4, the direct-DB handle's name in Task 4's smoke addition, and the pending-questions accessor in Task 6. Each names the exact grep.

**Type consistency.** `resolve_venue_id(subject_id, override_id, configured_slug, enabled) -> int` is called the same way in Task 1's smoke and Task 2's helper. `set_article_proposal_venue(proposal_id, target_project_id) -> bool` returns `False` for a non-`proposed` row in both its definition (Task 1) and its route (Task 5). `_venue_for(request, project, row) -> (venue, blog_dir)` keeps that shape across all three call sites in Task 2. `target_project_id` is `int | None` everywhere, with `None` meaning the subject.

**The regression that matters most.** Every task's checks include the `target_project_id is None` path, because that is wave A's behaviour on the user's live data and a silent change there would be the worst outcome of this wave.
