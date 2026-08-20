---
description: Write one approved article from the AI Dreaming Center's proposal, then report the draft and its verification.
---

# Write article

Usage: `/write-article <proposal-id>`

## 1. Read the brief

```bash
curl -s "$DREAMING_API_URL/api/articles/<proposal-id>"
```

You get `title`, `angle`, `slug_hint`, `funnel_level`, `locales`, `tags_json`,
`evidence`, `related_product`. The evidence is the fact the piece must be true
to — do not write around it.

For which languages to write, prefer `$DC_ARTICLE_LOCALES` when it is
non-empty; fall back to the payload's own `locales` only if that env var is
empty. The project setting wins because it is the operator's explicit
decision for this project; the payload's `locales` is only the scan's guess
at the time it proposed the topic.

## 2. Know which repository is which

Your working directory for this session is the **venue** — the repository
whose site will publish the piece. Its existing posts are the format to
copy, its build is what step 4 verifies, and its own repository is what
eventually receives the commit, once a human approves publishing.

`$DC_ARTICLE_SUBJECT_DIR` (slug `$DC_ARTICLE_SUBJECT_SLUG`) is the
repository the article is **about** — read it for the material: commits,
code, specs, changelogs, closed work. It is read-only. Never write there
and never commit there, no matter how convenient it looks to edit a file
next to the facts it describes.

When venue and subject are the same directory — still the common case —
none of this changes anything.

The format always comes from the venue, never from the subject. A subject
whose own docs are plain markdown does not make the venue's JSON-data blog
accept a markdown file; the venue's neighbouring posts, read in step 3
below, are the only pattern to copy.

## 3. Find out who writes

`$DC_ARTICLE_WRITER` names the agent the center resolved. If it is a real agent
name, delegate the writing to that subagent and let it own the format. The
delegate cannot see `$DC_ARTICLE_SUBJECT_DIR` or the brief for itself, so hand
both along in the delegating prompt: the subject repository's absolute path
and what it is (the project the article is about, read-only), plus the
brief's own title, angle, and evidence. Delegating without the subject path is
how a cross-project piece ends up inventing its facts. If it is `self`, write
the piece yourself.

Either way, **the venue owns the article's shape**. Before writing anything,
read two or three existing articles in `$DC_ARTICLE_BLOG_DIR` and copy their
structure exactly: file layout, frontmatter fields, language set, heading style,
where the CTA goes. If the venue keeps prose as data (a JSON entry rather
than a markdown file), add a data entry — do not invent a markdown file beside
it. If adding an article requires registering it somewhere (a build entry, an
index, a route), do that too; a piece that does not build is not written.

Match the existing typography per language. In this house style Polish quotes
are `„…”`, Russian are `«…»`, English are `"…"`, dashes are `—`, and ellipses
are `…`. Straight quotes in Polish or Russian text are a defect.

No invented numbers, clients, or benchmarks. If a claim is unverified, ask
rather than guess — see below for how.

## Ask when you can't verify something

Use this when the piece needs a fact that neither `$DC_ARTICLE_SUBJECT_DIR`
nor the venue can establish — a number, a client name, a claim about
behaviour. `blog-writer.md`'s own rule already forbids inventing these; this
channel is how you obey it instead of quietly working around it.

Post the question against the **subject**'s slug — `$DREAMING_PROJECT_SLUG` —
even though your cwd is the venue's article root. That project's page is
what the user is actually looking at. Also pass `run_id` set to this run's
`<proposal-id>`: the center's articles page shows the "writer is waiting"
line on a proposal's own card by matching a pending question's `run_id`
against that proposal's id, and a project can have more than one proposal
`writing` at once (or an unrelated self-study/rotation question pending on
the same project) — an id-less question would either light up no card at
all or, if the page fell back to a project-wide check, light up every
`writing` card including ones that never asked anything.

```bash
curl -s -X POST "$DREAMING_API_URL/api/questions/create" \
  -H "Content-Type: application/json" \
  -d '{
    "project_slug": "'"$DREAMING_PROJECT_SLUG"'",
    "run_id": "<proposal-id>",
    "tool_use_id": "write-article-<proposal-id>-<run-tag>-q1",
    "question": "Do we have a real number for this, or should the claim be cut?",
    "options": []
  }'
```

**JSON escaping (critical):** the body is single-quoted for the shell — the
same rule `/article-ideas-scan`'s ingest call carries. A literal apostrophe
inside `question` ends the quoted string early and breaks the command;
rewrite the value to avoid it, or close and re-open the quote around it
(`'It'\''s broken'`). `$DREAMING_PROJECT_SLUG` is spliced in with its own
`'"..."'` segment exactly as shown above — pasting the variable straight
inside the single-quoted JSON will not expand it; it will POST the literal
text `$DREAMING_PROJECT_SLUG`.

**`tool_use_id` must be unique per *asking*, not per proposal — a
proposal-scoped id breaks on retry.** `db.create_question` treats a
repeated `tool_use_id` as the same question: it returns the row that
already exists — with whatever `answer_text` (or lack of one) that row
already has — instead of creating a new one. That is deliberate, so a
session resumed mid-question does not duplicate its own ask. But retrying a
`failed` proposal re-dispatches `/write-article <proposal-id>` with the
*same* proposal id, so an id built only from the proposal id (e.g.
`write-article-<proposal-id>-q1`) computes to exactly the same key the
first attempt used. The retry's very first `create` call then silently
returns that old row: if it was answered, the retry proceeds on the
*previous* attempt's answer to whatever the previous attempt asked, not a
fresh answer to what the retry actually needs; if it was dismissed, the
retry is denied any chance to ask at all. Either way the writer would ship
a fact the user never confirmed for that question.

Add a run-scoped tag to the id to prevent this. Generate it once, the first
time you need to ask in this run — a timestamp works:

```bash
date +%s
```

— and reuse the number it prints for every question you ask in *this* run
(`-q1`, `-q2`, ...): `write-article-<proposal-id>-<that number>-q1`. Each
`curl` you run is a separate Bash tool call, and shell variables do not
survive between them, so don't rely on a shell variable still being set —
just remember the literal number you saw and paste it into every
`tool_use_id` you build afterwards. A fresh attempt and its retry land on
different tags (different times), so they never collide; two questions
inside the same run still get distinct ids via the `-q1`/`-q2` suffix.
Do not simplify this back down to a proposal-scoped id — that is exactly
the collision this paragraph exists to prevent.

The response is `{"id": "...", "status": "pending"}`. Poll it, sleeping
between attempts:

```bash
curl -s "$DREAMING_API_URL/api/questions/<id>/poll"
```

Keep polling every 20–30 seconds (`sleep 20` between calls) until `status`
is no longer `"pending"`. While a question is pending, the center's watchdog
does not count this session's silence against it, so waiting for an answer
is safe — it will not get the session killed.

- On `"answered"`, use `answer_text` as the fact and keep writing.
- On `"dismissed"`, or if the session ends before an answer ever arrives,
  **do not invent the fact and do not ship the piece without it.** Report
  the failure at step 5 through `error_message`, naming the question that
  went unanswered (e.g. `"unanswered question: do we have a real number for
  the latency improvement?"`). An article that ships around the fact it
  asked about is exactly the fabrication this pipeline exists to prevent.

Ask sparingly — two or three questions in one run, not an interrogation.

## 4. Verify

If `$DC_ARTICLE_VERIFY_CMD` is set, run it and capture the output verbatim. A
failure is a result to report, not something to hide or work around.

## 5. Report back

On success:

```bash
curl -s -X POST "$DREAMING_API_URL/api/articles/<proposal-id>/written" \
  -H "Content-Type: application/json" \
  -d '{"draft_ref": "<paths you created or edited>",
       "verify_output": "<verbatim output, or: no verify command configured>",
       "writer_agent": "<agent name or self>",
       "verify_ok": true}'
```

`draft_ref` contract (the center validates this before it will ever commit
anything, and there is no UI to fix a bad value afterwards — a rejected
`draft_ref` means another paid session to correct it):

- Every path is **relative to your cwd** — the root of the repository this
  session is running in, which is always the repository that contains
  `$DC_ARTICLE_BLOG_DIR` (for most projects that is the project root itself).
  Not relative to `$DC_ARTICLE_BLOG_DIR` — if the blog directory is itself a
  subdirectory (e.g. `src/data/`), still report the full path from your cwd
  (e.g. `src/data/blog-posts.json`), never just the filename or a path
  relative to that subdirectory.
- **Comma-separated** for more than one file — `"a.md, b.ts"` — never a JSON
  array; the API accepts a string and a JSON array is rejected outright.
- Each entry must be an **existing regular file**, not a directory and not a
  glob (`*`, `?`, `[...]` are all refused).
- No `..` segments and no absolute paths.

On failure, POST the same endpoint with `{"error_message": "<what failed>"}`.

Set `verify_ok` to `true` only if you ran the command and it exited zero. If
there was no command to run, send `false` with `verify_output` saying so — the
center labels that publish "unverified", which is honest; a `true` you did not
observe is not.

Never commit and never push. Publishing is a separate, human-approved step in
the center.
