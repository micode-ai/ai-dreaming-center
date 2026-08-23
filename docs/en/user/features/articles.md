# Articles

`/p/{slug}/articles` — the queue of article proposals for the project's
external blog, with approval, dispatching the writer, and publishing by
commit. Plus `/articles` — a cross-project queue of everything not yet
decided, across every project at once.

## Contents

- [Where proposals come from](#where-proposals-come-from)
- [What the page shows](#what-the-page-shows)
- [The proposal card](#the-proposal-card)
- [Buttons by status](#buttons-by-status)
- [The venue](#the-venue)
- [Preview](#preview)
- [Revision (Send back for revision)](#revision-send-back-for-revision)
- [Publishing](#publishing)
- [When the writer is waiting for an answer](#when-the-writer-is-waiting-for-an-answer)
- [The cross-project queue at `/articles`](#the-cross-project-queue-at-articles)
- [If something is not installed](#if-something-is-not-installed)
- [A typical working session](#a-typical-working-session)

## Where proposals come from

Four sources, all landing in the same queue:

1. **The "Propose topics" button** on the `/articles` page itself — runs
   `/article-ideas-scan`. The session is read-only: it looks at `git log`,
   closed specs, the AI-visibility report if one exists, and posts 3–7 topics
   each naming the fact it rests on ("evidence").
2. **The button on an AI Radar card** ("Propose an article") — the topic comes
   straight from the discovered publication (title, source, date), no session
   runs.
3. **The "Propose an article" button on an idea's card** (`/p/{slug}/ideas`) —
   turns a product idea into an article topic, evidence is the path to the
   idea's own md file. The button never disables or hides itself once the idea
   is already proposed — clicking it again just returns "already proposed",
   with no second row created.
4. **The "Add an article" form** on the `/articles` page itself — a topic and
   an opening prompt you type yourself. A collapsible block right under the
   page header.

No topic is created without a fact it rests on ("evidence") — true for the
slash command and the manual form alike (for the manual form, the center
composes the evidence itself: "requested by hand on `<date>`").

## What the page shows

Cards are grouped by status, each group with its own count:

| Status | Meaning |
|---|---|
| Proposed | proposed, awaiting a decision |
| Writing | being written right now |
| Drafted | a draft exists, awaiting review/publish |
| Published | published (terminal) |
| Rejected | rejected |
| Failed | the session failed or was cancelled |

At the top: the total proposal count (`N proposals`), who is currently writing
for this project (`writer: self` or an agent's name), and the "Propose topics"
button (greyed out while a scan is already running).

If `article_blog_dir` is not set for the venue — a yellow banner at the top.

If the installed copy of `.claude/commands/article-ideas-scan.md` or
`write-article.md` has **drifted** from the reference template (not the same
as being missing) — a separate banner with a diff and an "Update starter kit"
button. If the command lives in a different (nested) repository, there is no
button — it must be updated by hand, and the banner says so plainly.

## The proposal card

- Topic title, status badge, monospace `slug_hint`.
- A venue badge (`venue: <slug>`), only when it differs from the current
  project.
- A "Why now" line — the fact the proposal rests on.
- Tags, if any.
- For a drafted/published row — a build-result badge: "build passed" /
  "unverified" / "build failed".
- **Preview** and **Session log** buttons, when there's something to show (the
  log is available even for a failed attempt — that's where the explanation
  lives).
- The error (if any) and the verify command's output, as a text block.

## Buttons by status

| Status | Buttons |
|---|---|
| Proposed | **Approve and write** (dispatches the writer), **Reject**, a venue select + **Set venue** |
| Failed | **Retry** (re-dispatches the writer on the same topic), a venue select |
| Writing | **Cancel** (moves it to Failed; does not kill the underlying session — if the process is still alive it keeps going, the card just stops waiting on it) |
| Drafted | **Publish** (if the gate allows it) or the refusal reason as text, plus **Retry** |
| Rejected | **Back to queue** (returns it to Proposed) |
| Published | nothing — terminal |

## The venue

By default an article publishes into the repository of the **same** project
it's about. But you can pick a different venue — e.g. publish an article about
`accounting-ai-agent` on the company's landing page. The venue select is
visible while the article is Proposed or Failed; once the writer is
dispatched, the venue is pinned and cannot be changed for that attempt
(not even on Retry — it's already locked in).

If a project has `article_venue_project` configured in settings, that's what a
new proposal takes by default, with no manual pick needed.

## Preview

The **Preview** button opens what the writer actually put on disk — the
working tree, not the commit. If the article has several languages, tabs
appear at the top. For venues whose blog is one big JSON entry rather than a
set of files, preview still finds the right entry and shows it per language.

A file that could not be read, or that fails the publish check, lands in a
"problems" list instead of breaking the whole page.

## Revision (Send back for revision)

On the draft's preview page — a "Send back for revision" block:

- A list of automatic findings with checkboxes (when the venue has
  `article_min_chars` / `article_required_markers` configured) — e.g. "the
  English text is shorter than 3000 characters" or "no `[[diagram:` marker in
  any language". Checked by default.
- A free-text box — for anything no automatic check can see.

The **Send back for revision** button re-dispatches the writer with the same
`draft_ref` and the instructions — the same writer improves the files it
already produced rather than starting a new article. An empty request (no
checkbox, no text) is refused — a revision has to say something.

## Publishing

The **Publish** button is available only when:

- the article is Drafted;
- the venue's `article_publish_mode` is not `off`;
- if `article_verify_cmd` is set, it ran successfully (`verify_ok`).

If `article_verify_cmd` is not configured at all, publishing is still allowed,
but both the card and the commit message honestly say "unverified" — for
venues with no build step (a plain markdown blog, say) this is the only
sensible mode.

Publishing commits exactly what the writer named in `draft_ref` (plus, if
configured, a built site's directory — `article_publish_extra_paths`). Never
`git add -A`, never `git stash` — if someone else's uncommitted edits sit on
those same paths in the venue's working tree, publishing honestly refuses
rather than sweeping them into its own commit.

## When the writer is waiting for an answer

While writing, the writer may not be able to find, in the venue's or the
subject's code, a fact it's asked to confirm — rather than invent it, it asks
a question. A "The writer is waiting for your answer" link appears on the card
while it's Writing, pointing to `/p/{slug}/questions`. Answer it and the
session continues; dismiss the question and the writer honestly reports a
failure instead of shipping an unverified fact.

## The cross-project queue at `/articles`

A separate page (a menu item in the header, visible globally rather than
inside one project) — every proposal in the Proposed status across every
enabled project at once, with a project badge on each card. It also has a form
to kick off a scan for a chosen project without navigating into that project's
own `/articles` page. Only one button lives here — **Reject**; approving an
article means going to that project's own page (the card's title links there).

## If something is not installed

If `article-ideas-scan` or `write-article` is not installed in
`.claude/commands/` for the project (or the venue), the matching button
returns a clear error instead of hanging silently. To install: go to
`/p/{slug}/rotation` or `/p/{slug}/topics` → the starter-kit install button
(see [`out-of-the-box.md#starter-kit`](out-of-the-box.md#starter-kit)).

## A typical working session

1. In the morning you check `/articles` (the cross-project queue) or go into a
   specific project — new Proposed rows from the overnight scan are waiting.
2. Read the topic and its evidence. Off-target — **Reject**. Worth writing —
   **Approve and write** (changing the venue first if needed).
3. While it's Writing you can walk away and come back; if it hangs a while
   with no answer, open the Session log to see what's happening.
4. Draft ready (`Drafted`) — click **Preview**, read it. Not satisfied — tick
   findings and/or write your own notes, **Send back for revision**. Happy
   with it — **Publish**.
5. After publishing, the article sits at Published with a link to the commit;
   there's nothing more to do with it.

---

See also:
- [`../../features/articles.md`](../../features/articles.md) — the technical
  internals: lifecycle, venue resolution, publishing by commit.
- [`creatives.md`](creatives.md) — the parallel page for promotional
  creatives.
- [`ideas.md`](ideas.md) — the idea card the "Propose an article" button lives
  on.
- [`../../routes.md`](../../routes.md) — the full route list.
- [`../../configuration.md`](../../configuration.md) — every `article_*` key.
