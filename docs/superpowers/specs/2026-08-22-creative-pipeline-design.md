# Creative Pipeline: promotional content the way articles work

**Date:** 2026-08-22
**Status:** Approved (design)
**Author:** brainstorming session
**Sibling of:** [`2026-08-20-article-pipeline-design.md`](2026-08-20-article-pipeline-design.md), [`2026-08-20-article-cross-project-design.md`](2026-08-20-article-cross-project-design.md), [`2026-08-21-article-committed-build-output-design.md`](2026-08-21-article-committed-build-output-design.md)

## Problem

The article pipeline now works end to end: the center proposes, a human
approves, the project's own agent writes, a human reads the draft, sends it
back with notes if it is thin, and publishes when it is not. Promotional
content has none of that, and three projects already produce it by hand:

| Project | `docs/marketing/creatives/` holds | Copy lives in |
|---|---|---|
| `accounting-ai-agent` | 77 files: one HTML template per format per locale (`<slug>-post-4x5-pl.html`, `-story-pl`, `-reel-4x5-pl`, `-reel-pl`), `assets/`, `build.mjs`, `build-reel.mjs`, `renders/pl/` | `creatives/captions/<slug>-pl.md`, indexed by `captions/README.md` |
| `ai-budget-assistant` | 249 files: source screenshots (`photo_N_*.jpg`) per campaign, then `renders/` | `docs/marketing/copy/*.md` |
| `mi-code-ai` (landing) | 310 files: `<slug>/src/` and `<slug>/renders/` | `docs/marketing/copy/` |

Same three concepts under three different layouts — rendered media, post
copy, and a plan (`campaign-backlog.md`, `campaigns/`, `content-plan.md`).
This is the same lesson the article waves taught: **the venue owns the shape**,
and the center must not learn any of it.

`accounting-ai-agent`'s `captions/README.md` documents the target formats
precisely, and they are the de-facto house standard:

| File | Size | Ratio | Where |
|---|---|---|---|
| `*-post-4x5-<lang>.png` | 1080×1350 | 4:5 | feed (IG / FB / LinkedIn) |
| `*-story-<lang>.png` | 1080×1920 | 9:16 | story |
| `*-reel-4x5-<lang>.mp4` / `.gif` | 1080×1350 | 4:5 | video in feed |
| `*-reel-<lang>.mp4` / `.gif` | 1080×1920 | 9:16 | reels / stories / TikTok |

## Decisions taken before design

Three, settled with the operator:

1. **Publish means commit**, exactly as for articles — the renders, the copy
   and the attached sources land in the project's repository, and a human
   posts them to the networks. Posting through platform APIs is out of scope:
   it needs per-network credentials, a publish queue, and it is the one action
   in this whole pipeline that cannot be undone.
2. **Video is in from the first wave.** Reels are how this content is
   consumed; a static-only pipeline would be a demo, not a tool.
3. **A human attaches source material after the idea step.** That is already
   how `ai-budget-assistant` works — screen captures go into the campaign
   directory and the build turns them into formats. Without an upload step the
   pipeline could only ever produce what an agent can draw by itself.

## Architecture

### Why a separate table, not a `kind` column on `article_proposals`

A creative carries dimensions an article does not: a set of **formats**, a set
of **attachments**, and outputs that are binaries rather than text. Overloading
the article table would put four nullable columns on every article row and make
every article query explain itself. What is shared is not the schema but the
*discipline*, and that is reused deliberately:

- the evidence rule enforced at ingest, in the DB method and not only at the
  HTTP boundary — a queue of unfalsifiable suggestions is worse than an empty
  one;
- subject vs venue (`target_project_id`), so a creative about one product can
  be produced in another project's repository;
- publishing through a path-scoped `git add` that never passes `-f`, with
  rollback on failure;
- `revision_notes` set only on a drafted row and cleared by the write-back;
- one dispatch path shared by the first make and every revision, so a revision
  can never resolve the venue, the agent, the cwd or the limits differently.

### Status flow

```
proposed ──(attach files)──> approved ──> making ──> drafted ──> published
   │                                         │          │
   └──> rejected                             └─> failed <┘ (revise)
```

`attach` is allowed on `proposed`, `approved`, `failed` and `drafted` — the
last so material can be sent along with revision notes. It is refused while
`making`: the session has already listed the directory, so a file arriving
underneath it is a race with no upside.

### Per-venue settings

All optional; empty means the feature is off for that venue, so nothing
changes for a project that never opts in.

| Key | Meaning |
|---|---|
| `creative_dir` | Where campaigns live, relative to the venue's working dir (`docs/marketing/creatives`) |
| `creative_agent` | The agent that makes them; autodetected when blank, like `article_writer_agent` |
| `creative_formats` | Comma-separated format ids the venue produces (`post-4x5,story,reel-4x5,reel`) |
| `creative_locales` | Comma-separated locales |
| `creative_verify_cmd` | Run by the session in the campaign's own directory; the build lives here, never in the publish request |
| `creative_publish_mode` | `off` / `commit` / `commit+push` |
| `creative_publish_extra_paths` | Extra trees to commit — a venue that keeps a captions index or a shared assets dir names it here |

### Preview: the part that differs most from articles

An advertisement cannot be approved unless it is seen, so the center needs to
serve media out of a project repository: a route that validates the path with
the publish validator, refuses anything outside the campaign directory, allows
only the media types the pipeline produces, and streams the bytes with a
correct `Content-Type`. The preview groups renders by **format × locale**,
shows images inline and video in a `<video>` element, and puts the post copy
beside them. Without this, "Publish" would be a signature under something
invisible.

### Revision checks

The same shape as `draft_findings` for articles, with checks that are
meaningful here and computable without knowing the venue's toolchain:

- a format in `creative_formats` that produced no render at all;
- a render whose pixel dimensions do not match its format's declared size
  (1080×1350 for 4:5, 1080×1920 for 9:16) — read from the PNG/JPEG header, no
  image library needed;
- a locale in `creative_locales` with no renders;
- no post copy found for the campaign.

Each finding carries the English sentence sent to the maker and the fields a
template needs to render it localised, exactly as the article findings do.

## Error handling and risk

| Risk | Handling |
|---|---|
| An upload escapes the campaign directory | Filename normalised to `[a-z0-9._-]`, extension allow-listed, path checked by the publish validator, destination fixed at `<creative_dir>/<slug>/src/` |
| A huge upload | Size cap, refused before anything is written |
| Video build takes minutes | It runs in the session's verify step, never in a web request — the same rule wave C settled for articles |
| A venue with no `creative_dir` | Every route refuses with a message naming the setting, before dispatching a paid session |
| Renders are binaries in git | That is what these repositories already do; publishing commits only the paths reported plus the operator's configured extras |
| A format id the venue does not actually build | The finding says the format produced nothing; it cannot tell "not built" from "not buildable", and says so rather than guessing |

## Testing

`scripts/smoke_creatives.py`, against temp DBs and throwaway repositories:

- ingest refuses blank evidence at the DB method, not just over HTTP;
- dedup on `(project_id, slug_hint)`;
- every status precondition: attach refused while making, revision notes only
  while drafted and cleared by the write-back, publish only from drafted;
- upload: a traversal attempt, a disallowed extension, an oversized file and a
  name needing normalisation — each refused or normalised with nothing written
  outside the campaign's `src/`;
- the media route: serves a render, refuses a path outside the campaign dir,
  refuses a non-media type;
- dimension findings computed from real PNG headers, including a correct file
  producing no finding;
- preview groups by format × locale for a fixture campaign.

## Out of scope

- Posting to social networks (see Decisions).
- A cross-project `/creatives` queue and scheduled scans — both follow once
  the loop is proven, the same order the article waves took.
- Generating imagery from nothing: the pipeline composes the venue's templates
  and the operator's attachments. An agent inventing brand visuals unattended
  is a different decision than this one.
