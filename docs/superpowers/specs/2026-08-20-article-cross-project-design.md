# Article Pipeline, Wave B: subject and venue, manual topics, a question channel

**Date:** 2026-08-20
**Status:** Approved (design)
**Author:** brainstorming session
**Extends:** [`2026-08-20-article-pipeline-design.md`](2026-08-20-article-pipeline-design.md)

## Problem

Wave A shipped a pipeline where a proposal belongs to one project, is written in that
project, and is published into that project's repository. Three facts make that model
the exception rather than the rule.

**Seven of the eleven managed projects have no blog at all.** Verified by scanning
each working directory for a directory of posts: only `mi-code-ai`
(`micode-landing-page/blog`, 18 posts, in a nested repository),
`accounting-ai-agent` (`packages/web/content/blog`, 12 Russian posts plus `en` and
`pl`) and `ai-budget-assistant` (`docs/marketing/seo/site/blog`, 10 posts with
per-language subdirectories) have one. `legalka-kb` has `content/normative`, which is
a knowledge base, not a blog. The remaining seven have nothing to point
`article_blog_dir` at, so under Wave A's model their articles cannot be written at
all.

**The company site already publishes articles about the other products.** The
landing page's existing posts include `accounting-ai-agent-architecture`,
`ai-budget-assistant-ai-architecture` and `ai-budget-assistant-receipt-ocr-gpt4`.
The venue is one repository; the subjects are many. Wave A conflated the two, and the
evidence was sitting in the blog directory the whole time.

**Two capabilities are missing outright.** The user cannot state a topic themselves —
`source="manual"` exists in the model with no way to produce one — and the writer has
no channel to ask a question, even though the agent instruction it works from
(`blog-writer.md`) explicitly tells it to ask when a factual claim is unverified.

## Decisions

1. **Venue resolution: per-project setting plus a per-proposal override.** Each
   project names its default venue; a proposal may override it before approval. The
   seven blogless projects point at `mi-code-ai`; the two with their own blogs point
   at themselves.
2. **A question waits as long as the session lives.** The writer blocks on the
   answer rather than guessing, up to the session's own ceiling. An unanswered
   question ends as a `failed` row with the reason stated, and retry is available.
   The alternative — write the piece without the unverified claim — was rejected: an
   article that goes out without the fact the writer asked about is the quiet
   fabrication this pipeline exists to prevent.
3. **No "add project by path" form.** It was proposed while `micode-landing-page`
   looked unreachable. Wave A's article-root derivation already resolves the `test`
   project into that nested repository, so the landing page is usable as a venue
   today and the form buys nothing.

## Architecture

### Subject and venue

A proposal's `project_id` is its **subject** — whose repository supplies the facts,
whose page shows the card, and where its questions land. The **venue** is the project
whose repository receives the article: its writer agent, its format, its verify
command, its publish mode, its git repository.

- New column `article_proposals.target_project_id INTEGER NULL`. `NULL` means "same
  as the subject", which is exactly Wave A's behaviour.
- New per-project setting `article_venue_project` (a project slug; empty means
  self).
- Resolution at approve and at publish, in order: the proposal's
  `target_project_id`, then the subject's `article_venue_project`, then the subject
  itself. A slug that names no enabled project falls back to the subject rather than
  failing, and the page says which venue it resolved to.

Everything Wave A read from `project` now splits along that line:

| Read | From |
|---|---|
| `article_blog_dir`, `article_verify_cmd`, `article_publish_mode`, `article_writer_agent` | venue |
| article root (the git repository containing the blog directory) | venue |
| session working directory | venue's article root |
| `article_max_turns`, `article_timeout_minutes`, `claude_path`, `model` | venue |
| facts, commits, code the article is about | subject |
| the card, the queue row, the questions | subject |

The approve route's existing refusal — 400 when `article_blog_dir` is unset — now
checks the **venue's** setting, because that is where the article has to land.

### What the session receives

Added to the existing `DC_ARTICLE_*` environment: `DC_ARTICLE_SUBJECT_DIR` (the
subject project's working directory) and `DC_ARTICLE_SUBJECT_SLUG`. The session's own
working directory is the venue's article root, so `DREAMING_PROJECT_SLUG` stays the
subject's slug — questions and the write-back must reach the proposal's own project,
not the venue's.

`write-article.md` gains one instruction: read the subject directory for material,
write in the venue's format. It already learns the format from neighbouring posts;
that part does not change.

### The manual feeder

A form on `/p/{slug}/articles`: a topic, an intro prompt, and a venue selector.
`POST /p/{slug}/articles/add` creates a proposal with `source="manual"`, the topic as
`title`, the intro prompt as `angle`, and the venue as `target_project_id`.

Its `evidence` states the truth: that a person asked for this article, when, and what
they said. It does not name a commit or a measurement, because there is none. The
API's blank-evidence 400 stays exactly as it is — the route composes real evidence
rather than bypassing the rule. A human's request is a checkable fact about why the
proposal exists; a fabricated commit reference would not be.

`slug_hint` comes from `slugify(topic)`, with the `manual-{timestamp}` fallback for a
topic that yields an empty slug, and the existing `UNIQUE(project_id, slug_hint)`
still means a second identical topic is reported as already proposed.

### The question channel

The infrastructure exists and is unchanged: `POST /api/questions/create` stores a
pending row and the process watchdog stops counting silence against the session while
one is pending; the user answers at `/p/{slug}/questions`; `GET
/api/questions/{id}/poll` returns the status and the answer text.

`write-article.md` gains a section telling the session to use it when a claim it
needs cannot be verified from either repository: post the question with the subject's
slug, poll until the status leaves `pending`, and use the answer. On `dismissed`, or
if the session is killed while waiting, it must not invent the claim — it reports
`error_message` and the row becomes `failed`, which the card already renders.

The articles page gains one line: when a proposal is `writing` and its subject
project has a pending question, the card says so and links to the questions page.
Without that, a session blocked on an answer looks identical to a session that is
working.

## Error handling and risk

| Risk | Handling |
|---|---|
| Venue slug names a disabled or deleted project | Falls back to the subject; the page shows the resolved venue, so the fallback is visible rather than silent |
| Venue has no `article_blog_dir` | Approve refuses with 400 before any session starts, naming the venue |
| Subject directory missing on disk | The session is told the path; a missing subject is a fact it must report, not work around |
| A question is never answered | The session dies at its ceiling; the row becomes `failed` with the reason; retry re-asks |
| Manual proposal duplicates an existing topic | `UNIQUE(project_id, slug_hint)` reports it as already proposed |
| Cross-project confusion in the write-back | `POST /api/articles/{id}/written` is keyed by proposal id and still requires `writing`; the venue never appears in it |
| Publishing into the wrong repository | The publish root is the venue's article root, derived by Wave A's rule and containment-checked |

## Testing

Per repo convention, `scripts/smoke_articles.py` grows; there is no pytest here.

- Venue resolution: override beats setting beats self; an unknown or disabled slug
  falls back to the subject; the resolved venue is what the page displays.
- The venue's settings are the ones read: a subject with no `article_blog_dir` but a
  venue that has one must be approvable, and the reverse must refuse.
- The manual route: a proposal is created with `source="manual"`, non-blank evidence
  naming the request, and the venue applied; a blank topic is refused.
- Questions: a created question is pending, an answer flips it and the poll returns
  the text, and the card reports a pending question for a `writing` row.
- The regression that matters: a proposal with `target_project_id` NULL behaves
  exactly as it did in Wave A, including which directory the session would run in.

## Out of scope

- An "add project by path" form (see Decisions).
- Editing or translating already-published articles.
- Publishing to dev.to, Telegram or Habr; git remains the publisher.
- Any change to the path validator, the pathspec-scoped commit, or the publish gate's
  three cases.
