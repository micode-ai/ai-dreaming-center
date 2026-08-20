# Article Pipeline: the center proposes articles, you approve, the project's writer writes

**Date:** 2026-08-20
**Status:** Approved (design)
**Author:** brainstorming session

## Problem

The user asked for a center that *proposes* writing articles and, once approved,
*writes* them — using the article-writer agents that live in the projects.

Two corrections to the premise, both verified, both shaping the design.

**Writer agents are rarer than assumed.** Across the 11 enabled projects, only
three carry anything that writes prose:

| Project | Writing agent | Neighbours |
|---|---|---|
| `mi-code-ai` (`micode-landing-page/`) | `blog-writer` | `seo-optimizer` |
| `ai-budget-assistant` | `blog-writer` | `seo-specialist` |
| `legalka-kb` | `kb-page-author` | `kb-reviewer`, `fact-extractor`, `seo-specialist` |

The other eight (`accounting-ai-agent`, `budlog`, `marketing-ai-assistant`,
`testing-ai-assistant`, `openwebui-ts-embedded-sdk`, `dn-parser`, `wishlist`,
`ai-dreaming-center`) have engineering agents only. The pipeline must therefore
work with no writer present, without pretending it has one.

**The publishing format is per-project, and unifying it is not on the table.**

- `mi-code-ai`: `micode-landing-page/blog/<slug>/index.html` + `main.ts`, with the
  actual prose living as data in `src/data/blog-posts.json`.
- `accounting-ai-agent`: `packages/web/content/blog/{ru,en,pl}/*.md` with a strict
  frontmatter contract (`slug, locale, translationKey, title, description,
  category, tags[], publishedAt, updatedAt, author, status`).
- `legalka-kb`: `content/normative`, its own structure again.

So the center cannot own the article's shape. It owns the *proposal*; the project
owns the *text*.

## The algorithm we are copying (verified 2026-08-20)

The user pointed at `D:\Work\micode\mi-code-ai\micode-landing-page` as the model.
Three properties transfer; they are the backbone of this spec.

**1. Content is data, not markup.** `blog-posts.json` is the single source of
truth, and `scripts/prerender.mjs` plus the sitemap generator read it directly —
the agent is explicitly forbidden from hand-editing `public/sitemap.xml`. The
lesson: whoever owns the format owns the whole write, and the center should not
reach into it.

**2. The writer agent *is* the algorithm.** `.claude/agents/blog-writer.md` is 192
lines of exactly the knowledge the center must not duplicate: house style
(first-person plural, case-study grounding, no invented metrics), per-language
typography (`„…”` for Polish, `«…»` for Russian, zero straight quotes in either),
a four-step publishing workflow (JSON entry → `index.html` → `main.ts` →
`vite.config.ts` entry), and a verification gate — `npx svelte-check`,
`npm run build`, and the standing order to "never claim success you haven't
observed." The center dispatches this agent and records what it reported.

**3. A proposal must be checkable.** `scripts/ai-visibility/advice.mjs` opens with
the rule this pipeline adopts wholesale: *"a suggestion nobody can check is worse
than no suggestion"* — every advice line traces back to a number in the measured
run. Its rules (`brand-canary`, `brand-mentioned-not-cited`, `page-not-cited`,
`portfolio-skew`, `dead-language`) are evidence-derived, and `MIN_SKEW_SAMPLE = 3`
exists because a single citation was once reported as a portfolio problem.

Alongside it, `docs/marketing/content-plan.md` is a queue in markdown: date,
campaign, funnel level, channel, language, creative, copy — plus
`tests/test_content_plan.py`, which parses the table and fails when a date drifts
away from its funnel level. Our proposal table is the machine-readable form of
that file.

## Decisions (from brainstorming)

1. **Audience: external content** — blog-class material written for readers
   outside the company. A review step and SEO concerns are in scope; internal
   docs and knowledge-base pages are not.
2. **Three idea sources**: a scan of the project itself, AI Radar findings, and
   artefacts already in the center (product ideas).
3. **Executor: setting plus autodetect** — `article_writer_agent` per project;
   empty means the command looks for a writing agent in `.claude/agents/`, and
   writes the piece itself if there is none.
4. **The center publishes**, and publishing means **git**: the article file is
   committed and pushed in the project repo, and the site's own deploy picks it
   up. No platform APIs, no tokens, no Habr — there is no documented public
   write API for Habr, and unofficial routes are out of scope.
5. **Two human gates**: approve-to-write, and approve-to-publish.

## Architecture

### Ownership boundary

Proposals and their statuses live in the center's SQLite database. Article text
lives only in the project repository, in that project's own format. The center
stores a reference and the verification output; it never writes or edits the
content itself.

### Data model

New table `article_proposals`:

| Column | Purpose |
|---|---|
| `id`, `project_id` | identity; global table is project-scoped unlike `ai_radar_findings` |
| `source` | `project_scan` \| `radar` \| `center` \| `manual` |
| `source_ref` | radar finding id, ai-visibility prompt id, commit range, idea slug |
| `evidence` | the traceable "why now". **NOT NULL, rejected when blank** |
| `title`, `angle` | headline and thesis handed to the writer |
| `slug_hint` | short hyphenated English keyword slug |
| `funnel_level` | `top` \| `product`, mirroring `content-plan.md` |
| `locales` | CSV, e.g. `pl,en,ru` |
| `tags_json`, `related_product` | tag vocabulary reuse; product card linkage |
| `status` | `proposed` \| `approved` \| `writing` \| `drafted` \| `published` \| `rejected` \| `failed` |
| `writer_agent` | who actually wrote it (resolved at dispatch, recorded after) |
| `draft_ref` | path(s) the writer reported creating |
| `verify_output` | what `article_verify_cmd` printed, verbatim |
| `session_id` | the center session that ran the write |
| `created_at`, `decided_at`, `written_at`, `published_at`, `error_message` | timeline + failure text |

`UNIQUE(project_id, slug_hint)` — three feeders converging on one subject produce
one row, not three. Indexes on `(project_id, status)` and `(status, created_at)`
for the per-project list and the cross-project queue.

### Status machine

```
proposed ──approve──> approved ──dispatch──> writing ──ok──> drafted ──publish──> published
   │                                            │
   └──reject──> rejected                        └──fail──> failed ──retry──> writing
```

Two transitions belong to the user (`approve`, `publish`); the rest are moved by
sessions and the API. Nothing auto-advances past `drafted`. A `drafted` proposal
may be re-dispatched — that returns it to `writing` and the writer overwrites its
own draft; a `published` one is terminal, since re-editing published pieces is
out of scope (below).

### Per-project settings (ConfigResolver)

| Key | Default | Meaning |
|---|---|---|
| `article_writer_agent` | `""` | empty → autodetect in `.claude/agents/`, then self-write |
| `article_blog_dir` | `""` | where articles live, relative to the project's working directory; also determines the article root (below) |
| `article_locales` | `""` | e.g. `pl,en,ru`; empty → whatever the existing posts use |
| `article_verify_cmd` | `""` | e.g. `npm run build`; empty → publish is allowed but labelled unverified |
| `article_publish_mode` | `off` | `off` \| `commit` \| `commit+push` |
| `article_max_turns` | `300` | see below |
| `article_timeout_minutes` | `120` | see below |

The limits need their own pair. The global defaults are `max_turns: 50` and
`timeout_minutes: 20`; the landing's search-driven pieces run 8–12 `##` sections
at 15–20k characters *per language*, times three languages, plus a build. That
exhausts 50 turns during the first language. Orchestration already set the
precedent with `orchestration_max_turns: 500` / `orchestration_timeout_minutes:
240`. Note the watchdog measures *silence*, not lifetime, with a hard ceiling of
`max(timeout × 6, 1 h)` — so the timeout value is about how long the session may
go quiet, not how long the article may take.

### The article root

Article work happens in **the git repository that contains the blog directory**, not
necessarily the project's own repository. That root — derived from the project's
working directory plus `article_blog_dir` — is what the writer autodetect searches,
what the article session runs in, and what the publish commits into.

For most projects the two are the same and nothing changes. They differ where a
project's site lives in a nested repository: `mi-code-ai`'s blog is
`micode-landing-page/blog`, and `micode-landing-page` is its own repository with its
own remote and its own `blog-writer` agent. Without this rule the pipeline would look
for a writer in the wrong `.claude/agents`, run the session where `package.json` is
not, and commit one repository's paths from another.

The derivation refuses to leave the project: an absolute `article_blog_dir`, one
containing `..`, a missing directory, or a directory that is not in a git repository
all fall back to the project's working directory. The blog directory handed to the
session is expressed relative to the derived root.

## Feeders

**`/article-ideas-scan`** — a new starter-kit command
(`templates/starter-kit/commands/article-ideas-scan.md`), dispatched into the
project like `product-idea-scan`. It reads the git log since the last proposal,
closed waves and plans, and product pages; where a project has an ai-visibility
report (`docs/seo/ai-visibility/REPORT.md` in the landing) it reads that too,
since `page-not-cited` and `dead-language` already name content gaps in
evidence-backed form. It POSTs proposals to the center API with
`DREAMING_PROJECT_SLUG` / `DREAMING_API_URL`, as `topics-scan` does.

**AI Radar** — a "Propose an article" button on the finding card, next to the
existing "To note". `source=radar`, `source_ref` = finding id, evidence assembled
from the finding's title, source and date.

**Center artefacts** — the same button on the product ideas page.
`source=center`, `source_ref` = idea slug, evidence = the idea itself.

**The evidence rule is enforced at the API, not in the prompt.** A proposal
arriving with an empty `evidence` gets a 400. This is the one place where the
pipeline is deliberately stricter than a human would be, and the reason is
`advice.mjs`: a queue of unfalsifiable suggestions is worse than an empty queue.

**Scheduling.** A weekly `article_ideas_scan` job, `article_ideas_scan_enabled =
False` by default, following `radar_scan_enabled`. The cron may propose. It may
never write and never publish.

## Dispatch and gates

**Approve** starts `pm.start_command(command_name="write-article",
prompt="/write-article <id>")` with `--permission-mode bypassPermissions` —
without it the session cannot write into the repo, which is settled behaviour for
self-study — plus `article_max_turns` / `article_timeout_minutes`. Status →
`writing`.

**`/write-article`** (second new starter-kit command) fetches the proposal from
the API, resolves the writer (setting → autodetect → itself), delegates to the
project's agent, runs `article_verify_cmd`, and POSTs back `draft_ref`,
`verify_output` and the exit code. Status → `drafted`, or `failed` with the build
output shown on the card and a Retry button.

**The publish gate** is the verification, not a checkbox. Three cases, and the
difference between them is what the card is allowed to claim:

- `article_verify_cmd` set and exited zero → Publish enabled, card shows the
  verification as passed.
- `article_verify_cmd` set and failed → Publish disabled with the failure shown.
  A red build never becomes a green publish.
- `article_verify_cmd` empty → Publish enabled, but card and commit message both
  say **unverified**. Blocking this case would make the feature useless in
  `accounting-ai-agent`, whose markdown blog has no build step at all; claiming
  verification that never ran would break the one rule we imported from
  `blog-writer.md`. Saying so plainly is the only honest option.

With `article_publish_mode=off` there is no button at all.

**Publishing** stages only the paths in `draft_ref`, commits, and pushes when
mode is `commit+push`. Never `git add -A`; never `git stash`. This is a hard
constraint learned in this repo: orchestration once swept uncommitted evolutions
with `git stash -u`, and this feature operates on eleven working trees that are
not ours. If the article paths contain unrelated uncommitted edits, the publish
stops with an error rather than trying to resolve it.

## UI

- `/p/{slug}/articles` — proposals grouped by status, in the idiom of the topics
  kanban. Card shows title, angle, evidence with a link back to its source, the
  resolved writer, and the stage buttons.
- `/articles` — cross-project queue of everything in `proposed`, the reason the
  proposals live in the center's database instead of in files.
- A `failed` card shows `verify_output` verbatim. No summarising a build failure.

## Error handling and risk

| Risk | Handling |
|---|---|
| Project has no writer agent | Autodetect misses → the command writes the piece itself; `writer_agent` records `self` so the card is honest about it |
| `article_blog_dir` unset | Approve is refused with a message pointing at settings, before any session starts |
| Article session hits the turn cap mid-language | `failed` + `error_message`; retry is explicit, and partial files stay in the working tree for inspection |
| Verify command missing | Publish stays available but is labelled unverified, in the card and in the commit message — never presented as checked |
| Two feeders propose the same subject | `UNIQUE(project_id, slug_hint)`; the API answers "already proposed" and returns the existing id |
| Dirty working tree at publish time | Stop with an error; no stash, no `-A` |
| Cron writing or publishing unattended | Structurally impossible: the job only creates `proposed` rows |

## Testing

Per repo convention (no test suite; manual smoke scripts):

- `scripts/smoke_articles.py` — proposal insert/dedup on `UNIQUE(project_id,
  slug_hint)`, the evidence-required rejection, every status transition including
  the illegal ones (publish from `proposed` must fail), and the publish gate's
  dependence on `verify_output`.
- `scripts/check_i18n.py` — new `article.*` keys mirrored in RU and EN.
- `scripts/check_css_tokens.py` — new templates carry no colour utilities and no
  static inline styles.
- Manual end-to-end on `mi-code-ai`, because it is the project whose algorithm
  this was modelled on and the only one with a build that verifies the result.

## Out of scope (YAGNI)

- Translating existing articles into new languages, and editing already-published
  pieces. Both are their own pipeline; folding them in now would make the first
  wave sprawl.
- Publishing to dev.to, Telegram, or Habr. Git is the publisher.
- Generating creatives — `docs/marketing/` already renders carousels and reels
  from `campaign.json`, and that factory stays where it is.
- Any center-side editing of article text.
