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

## 2. Find out who writes

`$DC_ARTICLE_WRITER` names the agent the center resolved. If it is a real agent
name, delegate the writing to that subagent and let it own the format. If it is
`self`, write the piece yourself.

Either way, **the project owns the article's shape**. Before writing anything,
read two or three existing articles in `$DC_ARTICLE_BLOG_DIR` and copy their
structure exactly: file layout, frontmatter fields, language set, heading style,
where the CTA goes. If this project keeps prose as data (a JSON entry rather
than a markdown file), add a data entry — do not invent a markdown file beside
it. If adding an article requires registering it somewhere (a build entry, an
index, a route), do that too; a piece that does not build is not written.

Match the existing typography per language. In this house style Polish quotes
are `„…”`, Russian are `«…»`, English are `"…"`, dashes are `—`, and ellipses
are `…`. Straight quotes in Polish or Russian text are a defect.

No invented numbers, clients, or benchmarks. If a claim is unverified, ask
rather than guess.

## 3. Verify

If `$DC_ARTICLE_VERIFY_CMD` is set, run it and capture the output verbatim. A
failure is a result to report, not something to hide or work around.

## 4. Report back

On success:

```bash
curl -s -X POST "$DREAMING_API_URL/api/articles/<proposal-id>/written" \
  -H "Content-Type: application/json" \
  -d '{"draft_ref": "<paths you created or edited>",
       "verify_output": "<verbatim output, or: no verify command configured>",
       "writer_agent": "<agent name or self>",
       "verify_ok": true}'
```

On failure, POST the same endpoint with `{"error_message": "<what failed>"}`.

Set `verify_ok` to `true` only if you ran the command and it exited zero. If
there was no command to run, send `false` with `verify_output` saying so — the
center labels that publish "unverified", which is honest; a `true` you did not
observe is not.

Never commit and never push. Publishing is a separate, human-approved step in
the center.
