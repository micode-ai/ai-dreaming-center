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

## 1a. If this is a revision, it is not a new article

When `$DC_ARTICLE_REVISION_NOTES` is non-empty, a human read your draft and
sent it back. `$DC_ARTICLE_DRAFT_REF` lists the files you produced last time.

- **Improve those files in place.** Same slug, same entry, same paths. Writing
  a second article on the same subject leaves the venue with two, and the one
  the reader finds is whichever the index sorts first.
- **Address every note.** They are specific on purpose. "Too short" means add
  the mechanics, numbers and worked examples the piece gestures at and never
  shows — not more adjectives around the same claims, and not a summary
  section repeating what the reader just read.
- If a note asks for something the venue supports but you have not used
  (a diagram, a table, an image), find how the neighbouring articles do it
  before inventing your own way. Look at what they reference and add yours the
  same way.
- If a note is wrong or impossible, say so in your report rather than
  half-doing it — and if it needs a fact you cannot verify, ask (see below).

Then verify and report exactly as a first write does; the center moves the row
back to `drafted` on your report either way.

## 1b. The operator's own direction, if there is one

`$DC_ARTICLE_BRIEF` is non-empty when the operator typed direction next to the
button that dispatched you: what to lead on, what to avoid, which tone.

- It **outranks the payload's `angle`.** The angle is what the scan guessed
  when it proposed the topic; this is what the human who pressed the button
  actually wants. Where they disagree, follow this and say so in your report.
- It does **not** loosen the evidence rule. Direction chooses among true
  things to say; it cannot make an unestablished fact sayable. If it asks for
  a claim neither repository establishes, ask for that fact (step 4a) rather
  than writing it.
- It is **not** a revision. It is set on a first run too, and it stays set
  across retries — seeing it does not mean files already exist. Only
  `$DC_ARTICLE_REVISION_NOTES` means that.

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

**Sample one entry, never read a large data file whole.** When the venue keeps
prose as data, "read two or three existing articles" means two or three
*entries*, not the file they live in. `micode-landing-page` keeps 17 articles
with three full language bodies each in one 778 KB `src/data/blog-posts.json`;
a session that read it whole four times died of `error_during_execution` after
11 minutes and $1.66 with nothing written. So: check the size first (`wc -c`).
Over roughly 100 KB, print only what you need — the key names and one short
field of one entry — and mutate the file with a script that reads, appends and
writes in a single pass **without printing its contents back**. Pulling a large
file into your own context to edit it is how a writing session runs out of room
before it writes anything.

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

The response is `{"id": "...", "status": "pending"}`. Poll it from a
**single** Bash call that loops internally — each `curl` you run is its own
Bash tool call and its own turn, and this session shares one turn budget
(`article_max_turns`) across reading the repo, writing the piece, verifying
it, and this wait. A one-`curl`-per-turn poll loop can burn most of that
budget on waiting alone and die of `error_max_turns` before it ever gets to
write anything — the fix is one Bash call that sleeps and re-polls inside
itself, so the whole wait costs a single turn no matter how long it runs:

```bash
for i in $(seq 90); do
  resp=$(curl -s "$DREAMING_API_URL/api/questions/<id>/poll")
  case "$resp" in
    *'"status":"pending"'*) sleep 20 ;;
    *) echo "$resp"; break ;;
  esac
done
```

That loop is bounded (90 tries × 20s ≈ 30 minutes) — adjust the count if you
need to wait longer, but it must stay inside this one call, never split
back into one `curl` per turn. While a question is pending, the center's
watchdog does not count this session's silence against it, but that only
stops the *watchdog* from killing the session — it does not extend
`article_max_turns` or the session's own timeout ceiling. **Waiting is not
unconditionally safe**: if the loop above ends and `status` is still
`"pending"`, or the session is approaching its own turn/time ceiling either
way, do not keep waiting indefinitely and do not proceed as if answered —
report through `error_message` at step 5, naming the question that went
unanswered, same as the `"dismissed"` case below.

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
