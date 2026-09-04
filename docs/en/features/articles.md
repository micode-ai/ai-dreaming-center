# Article pipeline

The article conveyor: the center proposes a topic (on its own or from someone
else's hint), a human approves it, the project's own agent writes a draft, a
human looks it over and either sends it back for revision or publishes it as a
commit into the project's repository. The two human gates — Approve and
Publish — are the only places where anything actually happens without an
explicit click.

The key architectural decision from Wave A, from which almost everything else
follows: **the center does not know the article's format**. The landing page
keeps prose as records in `blog-posts.json`, `accounting-ai-agent` keeps
per-locale markdown with a strict frontmatter, `legalka-kb` has its own
structure. So the center owns only the proposal (topic, evidence, status), and
the venue always decides the article's shape — its existing posts and its
writer agent, if it has one. A writer agent exists in only 3 of 11 connected
projects; for the rest, the `write-article` session itself is the writer
(`writer_agent = 'self'`), and that is a normal outcome, not a degradation.

## Contents

- [Subject and venue](#subject-and-venue)
- [Proposal lifecycle](#proposal-lifecycle)
- [The `article_proposals` table](#the-article_proposals-table)
- [Who submits proposals](#who-submits-proposals)
- [Approve: dispatching the writer](#approve-dispatching-the-writer)
- [Resolving the venue and the article root](#resolving-the-venue-and-the-article-root)
- [Write-back API and the question channel](#write-back-api-and-the-question-channel)
- [Preview](#preview)
- [Revise — sending a draft back](#revise--sending-a-draft-back)
- [Publish: the commit](#publish-the-commit)
- [Reconcile: stranded attempts](#reconcile-stranded-attempts)
- [Settings](#settings)
- [The four skills](#the-four-skills)
- [Cross-references](#cross-references)

## Subject and venue

Every proposal has two projects, which almost always coincide but need not:

- **subject** — the project the article is *about* ("submitted from" —
  `article_proposals.project_id`). Owns the card, the queue row, the writer's
  questions and the session log.
- **venue** — the project whose repository the article lands in. Owns the
  format: `article_blog_dir`, `article_writer_agent`, `article_verify_cmd`,
  `article_publish_mode` and everything else on the settings page is read from
  the venue, never from the subject.

The venue is resolved by a pure function
[`articles.resolve_venue_id`](../../../dreaming/services/articles.py) (Wave B):
the proposal's own override (`target_project_id`) outranks the subject's
`article_venue_project` setting, which outranks the subject itself. A value
naming no enabled project falls back rather than failing. With no override and
no `article_venue_project` setting, venue == subject, which reproduces Wave A's
behaviour byte for byte — every project today except `budlog`, which has
`article_venue_project=test` (the cross-project demo from Wave B).

The venue is **pinned** at the moment of successful dispatch
(`db.pin_article_proposal_venue`, called from `articles_approve` right after
`pm.start_command` but before `start_article_attempt`) — not earlier, not
later. Publish reads the pinned value instead of re-resolving it: otherwise the
row could drift if `article_venue_project` changes between approve and
publish.

## Proposal lifecycle

```
proposed --(approve)--> writing --(written, verify_ok or not)--> drafted --(publish)--> published
   |                        ^                                        |
   |                        |________________(revise / retry)________|
   |
   +--(reject)--> rejected --(restore)--> proposed
   +--(done)----> done -----(restore)--> proposed

writing --(written, error_message)--> failed --(approve/retry)--> writing
writing --(cancel, manual)-----------> failed
writing --(reconcile cron, session dead)--> failed
failed  --(done)---------------------> done
failed  --(draft-ready, manual)------> drafted
```

The two exits from `failed` are not interchangeable. `done` ("already done")
closes the row and commits nothing — the article exists outside this pipeline.
It is deliberately separate from `rejected`: rejected says the topic was
wrong, done says it was right and the work already exists. It costs nothing in
dedup (the unique `(project_id, slug_hint)` index refuses a re-proposal under
either outcome), but a month later the queue reads honestly. Reachable from
`proposed` and `failed`, reversible through the same `restore` rejected rows
use, refused from `writing` with a `409` — a session is still working there.

`draft-ready` is a recovery, not a decision: the draft is on disk but the
report never landed (the session was killed, the host restarted, or reconcile
failed the row from under a working writer — see below). The route puts the
row where `/written` would have put it, so the normal publish gate, and the
commit behind it, become reachable again without paying for another session to
rewrite files that already exist. The paths are validated by the same code
publish uses (`article_publish.validate_draft_paths`) before anything is
stored. The verification label on such a row is `manual`, never `verified`:
the centre did not run the build, a human vouched for it, and the commit
message says which of the two happened. Accepted only from `failed` — a
`writing` row must be cancelled first, so nothing is recorded behind a live
session.

The status is written into the `status` column; there is no CHECK constraint,
only code (`_ORDER` in the template and `_DISPATCHABLE_STATUSES` in the route)
— a row with any other value still renders, in a separate "other" group.

`approved` is formally part of `_DISPATCHABLE_STATUSES` and of the status
order, but it is **unreachable today**: no code path ever sets it —
`articles_approve` dispatches the writer and moves the row straight to
`writing`, skipping an intermediate `approved`. The comment at
[`db.py:1506`](../../../dreaming/services/db.py) says so in plain words: "the
first approve ('proposed', and the unreachable-today 'approved')" — room for a
future two-step approve, not today's behaviour.

`published` is terminal: a repeat approve/retry against an already-published
row is refused with 409 before dispatch even happens (checked in
[`project_articles.py:428`](../../../dreaming/routes/project_articles.py),
before `start_article_attempt`, not only inside it — otherwise an already-spent
CLI session would end up attached to no row at all).

## The `article_proposals` table

Not documented in [`schema.md`](../schema.md) — the table was added after the
16-table count there was written. Key columns:

| Column | Meaning |
|---|---|
| `project_id` | the subject |
| `target_project_id` | venue override / pin (nullable, Wave B) |
| `source` | `project_scan` \| `radar` \| `center` \| `manual` |
| `evidence` | required; non-blank is enforced in `add_article_proposal`, not only at the HTTP boundary |
| `slug_hint` | a seed for the writer; `UNIQUE(project_id, slug_hint)` dedups three feeders proposing the same subject |
| `funnel_level` | `top` \| `product` |
| `locales`, `tags_json`, `related_product` | the brief |
| `status` | see the lifecycle above |
| `writer_agent`, `draft_ref`, `verify_output`, `verify_ok`, `verify_label` | what the write-back reported |
| `commit_ref`, `session_id`, `error_message` | the outcome of dispatch / publish |
| `revision_notes` | non-empty only between a revise and the next write-back |

`verify_label` is what the card and the commit message **are allowed to
claim** (`articles.publish_label`): `"unverified"` when `article_verify_cmd` is
blank, otherwise `"verified"`/`"failed"` from the actual `verify_ok`.
Persisted at write-back time, not recomputed at render or publish — otherwise
changing `article_verify_cmd` later would repaint already-written cards.

## Who submits proposals

Four sources, distinguished only by `source`:

| Source | `source` | How | Where |
|---|---|---|---|
| `/article-ideas-scan` slash command | `project_scan` | The session scans `git log`, closed specs, `docs/seo/ai-visibility/REPORT.md`, and POSTs to `POST /api/p/{slug}/articles/ingest` | manually via the "Propose topics" button, or the weekly `weekly_article_ideas_scan_{slug}` cron (off by default) |
| AI Radar | `radar` | `POST /ai-radar/{finding_id}/propose-article` — evidence is assembled from the finding itself (source, title, date), no LLM session involved | button on a finding's card |
| Product Ideas | `center` | `POST /p/{slug}/ideas/{item_id}/propose-article` — evidence is the path to the idea's own md file | button on an idea's card |
| A human | `manual` | `POST /p/{slug}/articles/add` — evidence honestly says "requested by hand on `<date>`" | the form on the `/articles` page itself |

`_ARTICLE_SOURCES` in [`api.py`](../../../dreaming/routes/api.py) is the shared
allow-list for the ingest HTTP boundary; `add_article_proposal` itself refuses
a blank `evidence` (not only the route), so the rule holds structurally for any
future feeder.

The manual form (`articles_add`) is the one place where the slug is not built
by `articles.slugify` (which drops Cyrillic) but by a hash of the normalised
topic (`"manual-" + sha1(...)[:10]`) when `slugify` returns blank: a Russian
topic is the ordinary case for this form, not an edge case, and a
clock-based fallback would collide two different topics submitted in the same
second while failing to dedup the same topic submitted seconds later.

## Approve: dispatching the writer

`POST /p/{slug}/articles/{id}/approve`
([`project_articles.py:408`](../../../dreaming/routes/project_articles.py)):

1. 404 if the row is missing or belongs to another project.
2. 409 if `status` is not in `_DISPATCHABLE_STATUSES = (proposed, approved, failed, drafted)`.
3. Resolves the venue (`_venue_for`) and `article_blog_dir` — 400 if blank.
4. Resolves the repository that actually owns the blog
   (`articles.resolve_article_root`) — not always `venue.working_dir`: a
   venue like `micode-landing-page` nests its blog in a second repository with
   its own `.git`.
5. Checks that `write-article` is installed **in that root**, not in
   `venue.working_dir` — otherwise the check would pass against the wrong
   `.claude/commands/` while the session actually starts inside the nested
   repository that has none.
6. Resolves the writer (`articles.resolve_writer`) and starts `pm.start_command`
   with `working_dir=root`, the prompt `/write-article {proposal_id}` and env:
   `DREAMING_PROJECT_SLUG` (the subject, not the venue — the write-back and any
   question must reach it), `DREAMING_API_URL`, `DC_ARTICLE_WRITER`,
   `DC_ARTICLE_BLOG_DIR` (re-derived relative to `root`, see
   `session_blog_dir`), `DC_ARTICLE_VERIFY_CMD`, `DC_ARTICLE_LOCALES`,
   `DC_ARTICLE_SUBJECT_DIR`, `DC_ARTICLE_SUBJECT_SLUG`,
   `DC_ARTICLE_REVISION_NOTES`, `DC_ARTICLE_DRAFT_REF` (the last two non-blank
   only on a resend for revision), `DC_ARTICLE_BRIEF` (the operator's
   direction, typed at dispatch time; stored on the proposal and outliving
   every attempt).
7. Pins the venue, then `db.start_article_attempt` — moves the row to
   `writing`, wipes the previous attempt's `draft_ref`/`verify_output`/
   `writer_agent`/`error_message` (otherwise a retry would show a stale "build
   passed" next to a brand-new error).
8. Dismisses any question left pending by a previous attempt
   (`dismiss_article_proposal_questions`) — otherwise a retry would read the
   answer meant for a different, already-dead attempt's question.

`bypassPermissions` is required (same decision as self-study, see
[`self-study.md`](self-study.md)): with `--allowedTools` the session silently
loses the ability to write into the repository.

`articles_revise` (sending a draft back) is **the same code path**: it writes
`revision_notes`, then calls `articles_approve` directly, so the venue, the
writer, the cwd and the limits of a revision can never diverge from what the
first write decided.

## Resolving the venue and the article root

`articles.resolve_article_root(working_dir, blog_dir)` — the git repository
that actually owns the blog, not always `working_dir`. Falls back to
`working_dir` unchanged whenever: `blog_dir` is blank; it would escape
`working_dir` (an absolute path or a `..` segment); the directory does not
exist yet on disk; the directory is not inside a git repository at all; or
`git rev-parse --show-toplevel` for it turns out to be an **ancestor** of
`working_dir` (the project is registered on a subdirectory of a larger
checkout — a real git repository, but not the project's own). Following that
ancestor would commit the publish higher up the tree than the project itself —
so the function guarantees `root` is either `working_dir` or a descendant of
it, never an ancestor or an unrelated tree.

`articles.session_blog_dir(working_dir, blog_dir, root)` re-derives
`DC_ARTICLE_BLOG_DIR` relative to `root`, only when `root` actually differs
from `working_dir` (the nested-repository case).

## Write-back API and the question channel

`/write-article` reads its brief via `GET /api/articles/{id}`
([`api.py:646`](../../../dreaming/routes/api.py)) and reports back via
`POST /api/articles/{id}/written` ([`api.py:655`](../../../dreaming/routes/api.py)):

- 409 if the row is no longer `writing`.
- Success: `{draft_ref, verify_output, writer_agent, verify_ok}` →
  `mark_article_written` moves it to `drafted`, persists `verify_label`
  (computed against the venue, not the subject — the row's
  `target_project_id` already carries the pinned venue), clears
  `revision_notes`.
- Failure: `{error_message}` → `failed`, dismisses any pending question.
- `draft_ref` defaults to `""` — otherwise an honest failure report
  (`{"error_message": "..."}`, no `draft_ref`) would 422 from pydantic before
  the handler even ran.

The question channel (`POST /api/questions/create`,
`GET /api/questions/{id}/poll`, shared infrastructure with self-study, table
`orchestrator_questions`) is used by the writer when a fact can be confirmed
neither in the subject nor the venue. The question is posted with
`run_id = <proposal_id>` **against the subject's slug**, even though the
session's cwd is the venue: the page shows "the writer is waiting for your
answer" on a proposal's card by matching a pending question's `run_id` against
that row's id, the only way to avoid lighting up an unrelated card
(self-study/rotation/another proposal on the same project). While a question
is pending, the `ProcessManager` watchdog does not count the session's silence
against it (`process_manager.py:561`) — but it does not extend
`article_max_turns`.

## Preview

`GET /p/{slug}/articles/{id}/preview?lang=&file=`
([`project_articles.py:660`](../../../dreaming/routes/project_articles.py))
shows the working tree, not the commit: for a published row this is the file
as it stands now, which may have already diverged from what was committed.

Every path from `draft_ref` goes through `article_publish._validate_paths` —
the same validator publish uses, so the preview can never show anything
publish could not have committed. A path that fails validation goes into a
"problems" list instead of aborting the whole page.

A variant's language is read from its frontmatter (`lang:`/`locale:` in the
leading `---` block) or from a path segment matching one of the row's
`locales`. For venues that keep prose as data (`micode-landing-page`: one JSON
array entry with `titlePl`/`bodyPl` fields and so on) —
`articles.data_entry_variants` finds the entry by `slug_hint` or by a segment
of `draft_ref` and reads the languages out of `body<Lang>` fields. The file
itself stays reachable separately ("others") for debugging.

Files longer than 200,000 characters are truncated with a notice (a generated
registry or an editorial plan can be far larger than the article itself).

For `status == 'drafted'`, `draft_findings` (below) are computed to
pre-populate the revision form's checkboxes.

## Revise — sending a draft back

Checks computable without knowing the venue's own tooling
(`articles.draft_findings`), both per-venue and both opt-in because neither has
a defensible default:

- `article_min_chars` — a variant shorter than this many characters is flagged
  `short`.
- `article_required_markers` — a marker (e.g. `[[diagram:`) missing from at
  least one language is flagged `marker`.

With neither setting the revision form is just a free-text box. `POST
/p/{slug}/articles/{id}/revise` combines the ticked findings and the free text
into `revision_notes`, refuses an empty request (400), and calls
`articles_approve` — the same dispatch path as the first write.

## Publish: the commit

`POST /p/{slug}/articles/{id}/publish`
([`project_articles.py:812`](../../../dreaming/routes/project_articles.py)) →
[`article_publish.publish`](../../../dreaming/services/article_publish.py) —
shared with creatives (see [`features/creatives.md`](creatives.md); not
duplicated here).

The gate, `articles.can_publish(row, verify_cmd, publish_mode)`:

- `article_publish_mode == 'off'` → refused (`mode_off`).
- `status != 'drafted'` → refused (`not_drafted`).
- `verify_cmd` set and `verify_ok` false → refused (`verify_failed`).
- Otherwise allowed; if `verify_cmd` is blank, publishing is allowed but both
  the card and the commit message honestly say "unverified". Refusing this
  case would make the feature useless for `accounting-ai-agent`, whose
  markdown blog has no build step at all.

Only the paths from `draft_ref` (self-reported by the writer) are published,
plus, if set, `article_publish_extra_paths` — a comma/newline-separated list
that **may name directories** (unlike `draft_ref`): meant for a committed
build output like `ai-budget-assistant`'s, where `docs/marketing/seo/site/blog`
is generated and committed whole (Wave C). The comment on `article_verify_cmd`
in [`config.py`](../../../dreaming/config.py) records the lesson of the first
live publish: verify must regenerate **everything** the deploy ships, not just
the generator nearest the article — otherwise the gate passes on a half-built
site.

`PushFailed` (the commit landed, `git push` did not) is distinct from
`PublishError`: the row is marked `published` with its `commit_ref`, and
`error_message` says a manual push is needed — otherwise a retry would see
"nothing to publish" forever and the sha would be lost.

## Reconcile: stranded attempts

A global cron every 5 minutes (`scheduler._reconcile_job`) calls
`db.reconcile_stranded_article_proposals(active_session_ids)` — it fails any
row stuck in `writing` whose `session_id` is not among the live `cmd:*`
processes tracked by `ProcessManager`. The only liveness signal is the live
process set, never the `agent_learning_sessions.status` column (which can show
`running` for years after an ungraceful shutdown skipped `_cleanup`). This
closes the case where a watchdog or a dying host process killed the
write-article session and it never called `/written`.

The manual "Cancel" button (`POST /p/{slug}/articles/{id}/cancel`) does the
same thing immediately, on click — moves `writing → failed` without killing
the underlying process (the route's own docstring says so in plain words).

### Other people's sessions: one database file, several servers

Nothing about this app is single-instance: a second `uvicorn` on another port
opens the same `data/dreaming.db` happily and runs the same five-minute cron.
Its live-process set is its own, so without a further check each instance
reads the other's live sessions as dead and fails the work underneath them.
That is not hypothetical — it is how proposal 514 died on 2026-08-25: the
writer worked for 21 minutes, a forgotten server running code from 08-23
failed the row on minute five, and the writer's own `/written` was then
refused as out-of-status.

So every instance registers itself in `app_instances` at startup
(`main.lifespan` → `db.register_instance`) and refreshes `last_seen` once a
minute (`scheduler._heartbeat_job`), while `create_session` stamps the owner
into `agent_learning_sessions.owner_instance`. Before all three sweeps,
`_reconcile_job` adds `db.sessions_owned_by_live_instances()` to the live set
— the unfinished sessions of instances whose heartbeat is younger than
`db.INSTANCE_STALE_AFTER_SEC` (180s, three missed beats). A live foreign
instance's session counts as running because it is running, and the instance
that owns it is the one that will decide when it is not.

The self-healing survives: a hard-killed instance stops beating, and after the
staleness window its rows become sweepable again; a clean shutdown drops the
row immediately via `db.unregister_instance()`. Rows with an empty
`owner_instance` (everything from before the column) behave exactly as they
did. `_heartbeat_job` logs a warning whenever another live instance appears —
a forgotten server is invisible right up until it eats something.

## Settings

The "Articles" group in [`configuration.md`](../configuration.md) /
[`features/settings.md`](settings.md):

| Key | Meaning |
|---|---|
| `article_writer_agent` | override for the autodetect |
| `article_blog_dir` | relative to venue.working_dir |
| `article_locales` | falls back to `row.locales` (the scan's guess) if blank |
| `article_verify_cmd` | build/verify, run by the **session**, never by a web request |
| `article_publish_mode` | `off` \| `commit` \| `commit+push` |
| `article_publish_extra_paths` | Wave C; may name directories |
| `article_min_chars`, `article_required_markers` | optional revision checks |
| `article_max_turns`, `article_timeout_minutes` | separate from self-study's limits — the global 50/20 is exhausted by the first language of a trilingual piece |
| `article_venue_project` | the default venue (Wave B) |

Plus `weekly_article_ideas_scan_cron` / `_enabled` in the "Scheduling — weekly"
group — off by default, the only cron job this pipeline has.

## The four skills

All four live in `templates/starter-kit/commands/*.md` (the source of truth)
and are copied into `{working_dir}/.claude/commands/` by the starter-kit
installer; two belong to articles:

- **`article-ideas-scan`** — read-only. Never writes, commits, or calls the
  writer. Posts through `POST .../articles/ingest`, skipping whatever `GET
  .../articles/list` already lists.
- **`write-article`** — `/write-article <id>`. Reads the brief, tells a first
  write from a revision by `$DC_ARTICLE_REVISION_NOTES`, copies the shape of
  two or three neighbouring posts from the **venue**, not the subject; for a
  venue with one huge JSON registry the file explicitly says not to read it
  whole (a real example inside the document: 778 KB, a session died 11 minutes
  in with nothing written); asks a question through the API instead of
  inventing a fact; never commits or pushes — publishing is a separate,
  human-approved step.

Both commands are commented line by line in the files themselves — see
[`templates/starter-kit/commands/article-ideas-scan.md`](../../../templates/starter-kit/commands/article-ideas-scan.md)
and
[`templates/starter-kit/commands/write-article.md`](../../../templates/starter-kit/commands/write-article.md).

An installed copy can **drift** from the template (not the same as being
missing) — the center detects this (`starter_kit.command_stale`, compared with
line-ending normalisation) and shows a banner on `/articles` with a diff, but
does not block the session: a too-old copy simply follows older instructions
silently.

## Cross-references

- Publishing by commit (shared module with creatives) — [`features/creatives.md`](creatives.md).
- User guide — [`user/features/articles.md`](../user/features/articles.md).
- Route inventory — [`routes.md`](../routes.md).
- Wave A/B/C history — [`waves.md`](../waves.md#wave-a--article-pipeline).
- Self-study and `bypassPermissions` — [`features/self-study.md`](self-study.md).
