# Creative pipeline

The same loop as articles — propose, approve, build by the venue's own agent,
review, revise on notes, publish — but for promotional creatives: renders
(image/video) across several formats and locales, plus post copy. Wave E
(after three article waves) deliberately **reuses the discipline, not the
schema**: its own `creative_proposals` table, but the git-publish module, the
venue resolution, and the publish-mode normalisation are all imported from
[`articles`](../../../dreaming/services/articles.py), not copied. This
document covers only how creatives differ; the shared machinery lives in
[`features/articles.md`](articles.md).

Publishing is a commit, not posting through a social API — a decision made
before design: the only irreversible action in the pipeline should not depend
on every platform's own tokens. Video ships in the first wave, not as a later
add-on: reels are how content actually gets consumed now.

## Contents

- [How creatives differ from articles](#how-creatives-differ-from-articles)
- [Campaign lifecycle](#campaign-lifecycle)
- [The `creative_proposals` table](#the-creative_proposals-table)
- [Campaign slug and attachments](#campaign-slug-and-attachments)
- [Who submits proposals](#who-submits-proposals-1)
- [Approve: dispatching the maker](#approve-dispatching-the-maker)
- [Write-back API](#write-back-api)
- [Preview and the media route](#preview-and-the-media-route)
- [Revise — sending a campaign back](#revise--sending-a-campaign-back)
- [Publish: the commit](#publish-the-commit-1)
- [Known gap: reconcile is not wired up](#known-gap-reconcile-is-not-wired-up)
- [What Wave E deferred](#what-wave-e-deferred)
- [Settings](#settings-1)
- [The two skills](#the-two-skills)
- [Cross-references](#cross-references-1)

## How creatives differ from articles

Three projects were already doing promotion by hand, with the center taking no
part: `accounting-ai-agent` (77 files — an HTML template per format/locale,
`assets/`, `build.mjs`, `build-reel.mjs`, `renders/pl/`, copy in
`creatives/captions/`), `ai-budget-assistant` (249 files — source screenshots,
`renders/`, copy in `docs/marketing/copy/`), the landing page (310 files —
`<slug>/src/`, `<slug>/renders/`). Same lesson as the article waves: **the
venue owns the shape**, and the center must not know any of them.

Its own table rather than a `kind` flag on articles: a creative has formats,
attachments, and binary outputs an article does not, and four nullable columns
on every article row would make every article query explain itself.

Where the two genuinely differ:

- **Attachments.** A human attaches source material (screenshots, screen
  recordings) **before** the maker ever runs — articles have nothing like
  this.
- **The slug is fixed when the proposal is created**, not chosen by the maker
  (the opposite of articles, where `slug_hint` is only a seed and the writer
  picks the final slug).
- **A media-serving route** — an ad cannot be approved unseen; articles have
  no such route, their preview is text.
- The build status is called `making`, not `writing`; the button reads
  "Make", not "Approve and write".

## Campaign lifecycle

```
proposed --(approve)--> making --(made, verify_ok or not)--> drafted --(publish)--> published
   |                        ^                                     |
   |                        |_______________(revise / retry)______|
   |
   +--(reject)--> rejected --(restore)--> proposed
   +--(done)----> done -----(restore)--> proposed

making --(made, error_message)--> failed --(approve/retry)--> making
making --(cancel, manual)--------> failed
failed  --(done)----------------> done
```

The same graph as articles, with `writing` renamed to `making`, plus a
terminal `done` ("already made") that articles do not have. It is kept apart
from `rejected` deliberately: a rejection says the idea was wrong, `done` says
it was right and the work was already produced by hand. Dedup is unaffected —
the unique `(project_id, slug_hint)` index stops a scan re-proposing the slug
under either outcome — but the queue reads more honestly a month later.
Reachable from `proposed` and `failed`, reversed by the same `restore` that
rejected campaigns use, and refused from `making` (`409`), where a session is
still working.
`approved` is formally dispatchable here too (`_CREATIVE_DISPATCHABLE`) and
just as unreachable in practice: approve moves `proposed` straight to
`making`.

## The `creative_proposals` table

Also undocumented in [`schema.md`](../schema.md). Columns `article_proposals`
does not have:

| Column | Meaning |
|---|---|
| `formats` | the campaign's formats (overrides the venue's `creative_formats`) |
| `maker_agent` | the `writer_agent` equivalent |
| `made_at` | the `written_at` equivalent |

Everything else — `project_id`, `target_project_id`, `source`, `source_ref`,
`evidence`, `title`, `angle`, `slug_hint`, `locales`, `tags_json`,
`related_product`, `status`, `draft_ref`, `verify_output`, `verify_ok`,
`verify_label`, `commit_ref`, `session_id`, `error_message`,
`revision_notes` — matches articles one for one, including
`UNIQUE(project_id, slug_hint)`.

`draft_ref` here holds **both renders and post copy, mixed together**: the
preview tells them apart by extension (`creatives.media_type` /
`creatives.is_copy`), rather than a second column that could disagree with
this one.

## Campaign slug and attachments

`creatives.campaign_slug(title)` is **not** `articles.slugify`. That one drops
Cyrillic on purpose (an article's `slug_hint` is only a seed for the writer); a
campaign slug is the directory name attachments land in **before** the maker
ever runs, and it never changes. So Cyrillic is transliterated
(`Дашборды и отчёты` → `dashbordy-i-otchety`) rather than dropped: an empty
slug would collapse different campaigns into one directory under the unique
index — silently, as a "duplicate" it never was.

Attachments are written to `<creative_dir>/<slug>/src/`
(`_store_attachments` in [`project_creatives.py:107`](../../../dreaming/routes/project_creatives.py),
shared by the add form and the standalone attach route). It assumes the caller
is careless, and refuses either way:

- Only the basename survives (`creatives.safe_upload_name`) — the path is
  **shortened**, not rejected, since a browser's `<input type=file>` honestly
  sends a full path.
- The name is normalised to `[a-z0-9._-]`, the extension is allow-listed
  (`UPLOAD_EXTS`: png/jpg/jpeg/gif/webp/mp4/mov/webm — **no svg**: an SVG would
  execute as a script when served by the media route from the center's own
  origin with the operator's cookies attached).
- The size is capped **while streaming** (64 MB), not afterwards — a file that
  exceeds it is deleted immediately.
- The path is then checked by the same validator publish uses
  (`article_publish._validate_paths`) — the route cannot write anywhere
  publishing could not commit from.

Attaching is allowed while a campaign is `proposed` / `approved` / `failed` /
`drafted` (`_CREATIVE_ATTACHABLE`) — not during `making`: the maker has already
listed the directory, and a file arriving underneath it is a race with no
upside.

## Who submits proposals

Two sources instead of articles' four — `_ARTICLE_SOURCES` (the shared
allow-list in [`api.py`](../../../dreaming/routes/api.py)) accepts all four
values (`project_scan`, `radar`, `center`, `manual`) for creatives too, but
**no route today produces `radar` or `center`** — neither AI Radar nor Product
Ideas has a "Propose a campaign" button the way they do for articles. What
actually works:

| Source | `source` | How |
|---|---|---|
| `/creative-ideas-scan` slash command | `project_scan` | `POST /api/p/{slug}/creatives/ingest`, deduped via `GET .../creatives/list` |
| A human | `manual` | `POST /p/{slug}/creatives/add` — topic, opening prompt, venue **and attachments in one step** |

The manual creatives form, unlike the article one, accepts files right there
(`enctype="multipart/form-data"`, the form in
[`project_creatives.py:304`](../../../dreaming/routes/project_creatives.py)):
a campaign an operator proposes usually exists *because* they already have
footage, and making them hunt down the card afterwards to hand it over is a
step that only ever gets skipped.

## Approve: dispatching the maker

`POST /p/{slug}/creatives/{id}/approve`
([`project_creatives.py:450`](../../../dreaming/routes/project_creatives.py)):
nearly word-for-word `articles_approve`, with the same reason for
`bypassPermissions`. What differs:

- It resolves not just the venue but the **repository root plus the campaign
  directory** (`_campaign`) — `<creative_dir>/<slug>` against the same
  `resolve_repo_root` (`articles.resolve_article_root` under another name),
  which handles nested repositories (e.g. the landing page) the same way.
- The env carries `DC_CREATIVE_AGENT` (the `DC_ARTICLE_WRITER` equivalent,
  resolved by `creatives.resolve_agent` — its own hint list: `creative`,
  `designer`, `design`, `marketing`, `copywriter`, `social`, `brand`,
  **deliberately without a bare `"writer"`**: the autodetect once picked
  `blog-writer` for the landing page, handing reel production to a prose
  agent), `DC_CREATIVE_DIR` (the campaign directory), `DC_CREATIVE_SLUG`
  (fixed), `DC_CREATIVE_FORMATS`, `DC_CREATIVE_LOCALES`,
  `DC_CREATIVE_VERIFY_CMD`, `DC_CREATIVE_SUBJECT_DIR`,
  `DC_CREATIVE_SUBJECT_SLUG`, `DC_CREATIVE_REVISION_NOTES`,
  `DC_CREATIVE_DRAFT_REF`, `DC_CREATIVE_BRIEF` (the operator's direction,
  typed at dispatch time; stored on the proposal and outliving every
  attempt, unlike the revision notes).
- There is no separate `article_blog_dir`-style 400 at the start: a missing
  `creative_dir` is caught earlier, by `_require_dir` — the same check that
  also blocks attaching without a directory.

## Write-back API

`GET /api/creatives/{id}` (the brief) and `POST /api/creatives/{id}/made`
([`api.py:565`](../../../dreaming/routes/api.py),
[`api.py:574`](../../../dreaming/routes/api.py)) mirror
`GET .../articles/{id}` / `POST .../articles/{id}/written`: 409 if the row is
no longer `making`, `{error_message}` → `failed`, success
`{draft_ref, verify_output, maker_agent, verify_ok}` → `mark_creative_made`
moves it to `drafted`, `verify_label` computed against the venue (not the
subject — the same "read from the pinned target" trick articles use).

The maker has a question channel, added because it previously did not.
`make-creative.md` forbids inventing an unverifiable fact ("Never invent a
number, a customer, a testimonial...") and, until step 4a existed, offered no
alternative beyond an honest failure report — a campaign could die over one
figure a human would have supplied in seconds.

Step 4a mirrors `write-article.md`'s: `POST /api/questions/create` against the
**subject**'s slug with `run_id` set to the proposal id, then a poll loop kept
inside a single Bash call so the wait costs one turn rather than one per
`curl`. The `run_id` is what lets the campaign's own card show the waiting
line — `project_creatives.py` matches a pending question's `run_id` against
the row id, so a question from another campaign, or one with no `run_id`,
lights up nothing. On `dismissed` or no answer, the rule is unchanged: fail
and name the question, never ship around it.

## Preview and the media route

`GET /p/{slug}/creatives/{id}/preview?fmt=&loc=`
([`project_creatives.py:587`](../../../dreaming/routes/project_creatives.py))
groups `draft_ref` paths by `(format, locale)` (`creatives.classify_render`
reads the suffix of the filename — `<something>-<format>-<locale>.<ext>`,
longest format first so `reel-4x5` is not read as `reel` with locale `4x5`).
Renders show as tabs, post copy renders as markdown right underneath, and
anything matching no format lands in a separate "outside the formats" list.

Renders are never inlined into the HTML — each is served by its own request to
`GET /p/{slug}/creatives/{id}/media?path=`
([`project_creatives.py:668`](../../../dreaming/routes/project_creatives.py)),
which articles have no equivalent of (text can go straight into the page, an
image or video cannot). Three independent checks:

1. The path must be one **this exact row reported** in its own `draft_ref`, or
   one of its own attachments (`creatives.list_attachments`) — the parameter
   selects from a ready-made list, it never opens anything arbitrary.
2. It passes `article_publish._validate_paths` against the campaign's root.
3. Its extension is in `creatives.MEDIA_TYPES` — **no `.svg`**, for the same
   reason the attachment list excludes it: an SVG is a script container served
   from the center's own origin with the operator's cookies attached.

## Revise — sending a campaign back

`creatives.draft_findings` — its own set of checks, unrelated to
`articles.draft_findings` because the domain is different:

- `format_missing` — a format from the venue's `creative_formats` with no
  render at all.
- `locale_missing` — a locale with nothing rendered.
- `wrong_size` — a render whose pixels (read from the PNG/JPEG/GIF header,
  `creatives.image_size`, no image libraries) do not match its format's
  declared size (`FORMAT_SIZES`: `post-4x5`/`reel-4x5` are 1080×1350,
  `story`/`reel` are 1080×1920). Video is never measured — only its presence
  or absence is reported, never a guessed size.
- `copy_missing` — renders exist, post copy does not.

`POST /p/{slug}/creatives/{id}/revise` follows the same pattern as articles:
findings plus free text into `revision_notes`, refuses an empty request, calls
`creatives_approve` with the same code path as the first build.

## Publish: the commit

`POST /p/{slug}/creatives/{id}/publish`
([`project_creatives.py:742`](../../../dreaming/routes/project_creatives.py))
uses the **same** [`article_publish.publish`](../../../dreaming/services/article_publish.py)
as articles — not a separate copy. The gate, `creatives.can_publish`, is an
unmodified import of `articles.can_publish`. `creative_publish_extra_paths` is
the same idea as articles' `article_publish_extra_paths` (may name
directories, for a built output). Refuses with 409 if `draft_ref` is empty
("the campaign reported no files") — articles have the same check implicitly
(an empty `draft_ref` never passes `_validate_paths`), creatives make it an
explicit 409 before calling publish.

## Known gap: reconcile is not wired up

`db.reconcile_stranded_creative_proposals` exists at
[`db.py:2000`](../../../dreaming/services/db.py) and mirrors
`reconcile_stranded_article_proposals`'s contract word for word (the same
liveness signal — the live `cmd:*` session set in `ProcessManager`, never the
`agent_learning_sessions.status` column) — but it is **never called**:
`scheduler._reconcile_job` only invokes the article version. A campaign
stranded in `making` after the maker's session dies (a watchdog kill, a host
crash) does not recover on its own — only the manual "Cancel" button moves it
on. `waves.md` never mentions this gap; it surfaced while reading the code for
this document and is not documented anywhere else.

## What Wave E deferred

Stated plainly in [`waves.md`](../waves.md#wave-e--creative-pipeline):

- Posting to social platforms via API — an operator's choice, not a gap.
- A cross-project queue at `/creatives` (the `/articles` equivalent) and a
  scheduled `weekly_creative_ideas_scan` — neither exists; that is also why
  there is no matching cron entry in `_PER_PROJECT_JOBS` (articles have
  `weekly_article_ideas_scan`, creatives have nothing).
- A live build run never happened: the pipeline is built and smoke-tested, but
  no campaign had gone through it by the time the wave shipped.

## Settings

The "Creatives" group (parallel to "Articles" but shorter — no
`_min_chars` / `_required_markers`; format/locale/size checks play that role
for creatives instead):

| Key | Meaning |
|---|---|
| `creative_dir` | blank by default = the feature is off; every route refuses naming this key |
| `creative_agent` | override for the autodetect |
| `creative_formats` | defaults to `post-4x5,story,reel-4x5,reel` |
| `creative_locales` | falls back to `row.locales` if blank |
| `creative_verify_cmd` | the build (reels take minutes; that's why it runs in the session, never a web request) |
| `creative_publish_mode` | `off` \| `commit` \| `commit+push` |
| `creative_publish_extra_paths` | same idea as articles |
| `creative_venue_project` | the default venue |
| `creative_max_turns`, `creative_timeout_minutes` | separate limits, defaulting to the same 300/120 as articles |

## The two skills

- **`creative-ideas-scan`** — read-only, three to seven proposals per run, each
  with `evidence`. Never creates files, directories, or branches; never runs
  the maker.
- **`make-creative`** — `/make-creative <id>`. Looks at `$DC_CREATIVE_DIR/src/`
  for what a human attached **before anything else**; copies the shape of
  neighbouring campaigns (where templates live, where renders go, how a
  filename encodes format and locale); writes the post copy — "renders without
  copy are half a campaign"; for a registry it uses the same trick as
  articles — never read a large file whole, mutate it with a script. Never
  commits or pushes, never renames or moves the campaign directory
  (attachments already live there), never deletes a human's attachment.

Verbatim source:
[`templates/starter-kit/commands/creative-ideas-scan.md`](../../../templates/starter-kit/commands/creative-ideas-scan.md),
[`templates/starter-kit/commands/make-creative.md`](../../../templates/starter-kit/commands/make-creative.md).

## Cross-references

- Shared machinery (venue resolution, git publish, the status machine) —
  [`features/articles.md`](articles.md).
- User guide — [`user/features/creatives.md`](../user/features/creatives.md).
- Route inventory — [`routes.md`](../routes.md).
- Wave E history — [`waves.md`](../waves.md#wave-e--creative-pipeline).
