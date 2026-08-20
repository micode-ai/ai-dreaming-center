---
description: Propose 3-7 article topics for this project and post them to the AI Dreaming Center.
---

# Article ideas scan

Propose article topics for **this repository's** external blog. You are not
writing the articles — only proposing what is worth writing, with evidence.
Propose 3–7 topics per run.

## What you have

- `cwd` is the project repository root.
- Env vars: `DREAMING_API_URL`, `DREAMING_PROJECT_SLUG` — already set in this
  session's environment; there is nothing to construct.

## The rule that makes this useful

Every proposal MUST carry `evidence`: one sentence naming a fact anyone can
check — a commit, a shipped feature, a closed wave, a dated release, a measured
gap. The center rejects a proposal with blank evidence (HTTP 400), and that is
deliberate: a queue of unfalsifiable suggestions is worse than an empty queue.

Never propose from a feeling ("developers care about X"). Propose from a fact
("commit 4a1f530 removed three unused classes; the migration is now finishable
in one pass").

## Where to look, in order

1. `git log --since="60 days ago" --oneline` — what actually shipped.
2. Closed wave plans and specs under `docs/superpowers/` — finished work with a
   written rationale is the best article material this repo has.
3. Product pages / README features that no article covers yet.
4. If `docs/seo/ai-visibility/REPORT.md` exists, read it. Its `page-not-cited`
   and `dead-language` lines are already evidence-backed content gaps — turn
   each into a proposal and quote the report line as the evidence.

## Skip what is already proposed

```bash
curl -s "$DREAMING_API_URL/api/p/$DREAMING_PROJECT_SLUG/articles/list"
```

Do not propose a `slug_hint` that appears in that list.

## Post each proposal

```bash
curl -s -X POST "$DREAMING_API_URL/api/p/$DREAMING_PROJECT_SLUG/articles/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "How we cut the report from eight hours to twenty minutes",
    "slug_hint": "report-time-eight-hours-to-twenty-minutes",
    "angle": "Walk through the query plan change, with the numbers",
    "evidence": "commit 1a2a965, 2026-08-18: replaced the per-row lookup with one join",
    "source": "project_scan",
    "source_ref": "1a2a965",
    "funnel_level": "product",
    "locales": "pl,en,ru",
    "tags": ["performance", "SQL"]
  }'
```

**JSON escaping (critical):** the `-d '{...}'` argument above is single-quoted
for the shell, so a literal apostrophe in `title` or `angle` — e.g. "It's
finally documented" — ends the quoted string early and breaks the command.
Rewrite the value to avoid the apostrophe, or close and re-open the quote
around it: `'It'\''s finally documented'`.

`funnel_level` is `top` for search-driven pieces that answer a question a
stranger types, and `product` for "our product as proof" write-ups.

Reuse the tag vocabulary already present in the project's existing posts.
`GET /articles/list` does not return tags, so look on disk instead — the
project's blog or content directory (wherever this repo keeps its published
posts) is the source of truth for tags in active use. If you cannot find any
existing posts to read tags from, omit `tags` rather than inventing a
vocabulary.

## Report

Print one line per proposal: slug, whether the API returned 201 or reported a
duplicate, and the evidence you attached. Report the count. Do not claim a
proposal landed without showing the response.

## Rules

- Propose only. Never write, edit, or commit an article, and never push —
  this command's whole output is the proposals it posts to the ingest
  endpoint.
- Never invoke a writer agent (blog-writer or otherwise) or any other agent —
  writing an approved article is a separate command's job, not this one's.
- Never touch project files. This command is read-only on disk.
- Never claim a proposal landed without showing the API's response.
