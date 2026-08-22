---
description: Propose promotional campaigns for this project to the AI Dreaming Center
---

# Creative ideas scan

Find things worth advertising about this project, and post each one as a
campaign proposal. You are not making anything here — the maker runs later,
after a human approves and attaches material.

## What you have

- `$DREAMING_API_URL` — the center's API
- `$DREAMING_PROJECT_SLUG` — this project's slug
- the repository you are standing in

## The rule that makes this useful

**Every proposal states a checkable fact it rests on.** A campaign nobody can
verify is worse than no campaign: it wastes a paid session, and worse, it ships
a claim about the product that nobody checked. `evidence` names the commit, the
file, the release note or the number the campaign is about. "Users would love
this" is not evidence. "Voice entry shipped in `a1b2c3d`, 2026-08-14, and the
release note says three seconds per expense" is.

The API refuses a blank `evidence` outright, so this is not advice.

## Where to look, in order

1. **What shipped recently that a user can see.** `git log` for the last few
   weeks, filtered to user-facing changes. A refactor is not a campaign; a
   feature is.
2. **What the product's own docs boast about** and no campaign has covered —
   compare the marketing directory's existing campaigns against the feature
   list.
3. **What the neighbouring campaigns already say**, so a new one adds instead
   of repeating. Read two or three of the existing ones.
4. **Numbers the repository can prove**: benchmark output, a migration's
   before/after, a limit the code enforces. A number a campaign can show is
   worth more than three adjectives.

Three to seven proposals. Fewer is fine if the project genuinely has nothing to
show right now — say so in the report rather than padding. More than seven and
nobody reads the queue.

## Skip what is already proposed

```bash
curl -s "$DREAMING_API_URL/api/p/$DREAMING_PROJECT_SLUG/creatives/list"
```

Returns `[{id, slug_hint, title, status}]`. Skip a subject that is already
there in any status — including `rejected`, which is a human saying no.

## Post each proposal

```bash
curl -s -X POST "$DREAMING_API_URL/api/p/$DREAMING_PROJECT_SLUG/creatives/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Voice entry: an expense in three seconds",
    "slug_hint": "voice-entry-three-seconds",
    "angle": "Show the whole gesture in one take: press, speak, done. No narration.",
    "evidence": "voice entry shipped in a1b2c3d, 2026-08-14; release note states three seconds per expense",
    "source": "project_scan",
    "source_ref": "a1b2c3d",
    "formats": "post-4x5,story,reel",
    "locales": "pl,en",
    "tags": ["voice", "onboarding"]
  }'
```

`slug_hint` becomes the campaign's directory name and never changes
afterwards — attachments land in it before the maker runs. Keep it kebab-case,
short, and about the subject rather than the format.

`formats` and `locales` may be left empty; the venue's own settings decide.
Fill them only when this particular campaign genuinely needs something
different from the venue's default.

**JSON escaping (critical):** the `-d '{...}'` argument is single-quoted for
the shell, so a literal apostrophe inside it ends the quoting. Write the JSON
to a file and use `-d @file.json` whenever the text has apostrophes, or avoid
them.

201 means a new proposal, 200 with `"duplicate": true` means one already
existed — that is not an error, and not something to retry.

## Report

One line per proposal: the slug and the fact it rests on. Then the count posted
and the count skipped as duplicates. If you found nothing worth proposing, say
what you looked at and why none of it qualified.

## Rules

- Never invent a number, a customer or a benchmark. If the repository does not
  prove it, it is not evidence.
- Never propose a campaign about something unreleased or behind a flag without
  saying so in `angle`.
- Do not create files, directories or branches. This command only reads and
  posts.
- Do not run the maker. A human approves first, and usually attaches footage.
