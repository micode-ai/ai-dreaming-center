## What this section is for

Articles is the pipeline from a topic to a published text. An agent proposes
topics, you approve, another agent writes, you read the draft and publish it as
a commit.

Inside a project this is `/p/<project>/articles` — the full queue with every
action. The global Articles page is a cross-project queue of everything not yet
approved.

## Where proposals come from

Four sources, one queue:

- **"Propose topics"** on this page — runs `/article-ideas-scan`. The session
  only reads: git history, closed specs, the AI-visibility report — and
  proposes three to seven topics.
- **An AI Radar card** — a topic straight from a publication it found, with no
  session run.
- **An idea card** — a product idea turned into an article topic.
- **The "Add an article" form** — a topic and prompt you write yourself.

Every proposal must rest on a fact — its evidence. Without one, no topic is
created. For the manual form the app supplies it: "requested by hand on
<date>".

## The lifecycle

| Status | What it means | Buttons |
|---|---|---|
| **Proposed** | Awaiting your decision. | Approve and write, Reject, venue select |
| **Writing** | Being written right now. | Cancel |
| **Drafted** | The draft is ready. | Preview, Publish, Retry |
| **Published** | Published. A terminal status. | — |
| **Rejected** | Turned down. | Back to queue |
| **Failed** | The session crashed or was cancelled. | Retry, Session log |

**Cancel** moves the card to Failed but does not kill the session: if the
process is alive it will finish — the card simply stops waiting for it.

## Venue

By default an article is published into the repository of the same project it
is about. You can choose another — writing about one project and publishing on
the company site, for instance.

The venue can be changed while the article is Proposed or Failed. Once the
writer starts it is fixed, and Retry will not change it.

## Preview and revision

**Preview** shows what the writer actually put on disk — the working tree, not
a commit. Multilingual articles are split into tabs. A file that cannot be read
lands in a "problems" list rather than taking the page down.

The preview page has **Send back for revision**: a list of automatic findings
with checkboxes plus a free-text field for your own. The button restarts the
same writer to improve what exists rather than start over. An empty request is
rejected — a revision has to say something.

## Publishing

**Publish** is available only when the article is Drafted, the venue's publish
mode is not off, and — if a verify command is configured — it succeeded.

With no verify command configured you can still publish, but the card and the
commit message both say "unverified" plainly.

Exactly what the writer named is committed, plus any extra paths configured.
Never `git add -A`, never `git stash`: if the venue's working tree holds
someone else's uncommitted changes on those paths, publishing refuses rather
than sweeping them into its commit.

## When the writer is waiting

The writer may fail to find a fact it is asked to confirm. Rather than invent
one, it asks. A card in Writing then shows a link to the Questions section.
Answer and it continues; dismiss the question and it reports failure honestly
instead of asserting something unverified.

## Related sections

- **Questions** — where you answer the writer.
- **Ideas** and **AI Radar** — two of the four topic sources.
- **Creatives** — built the same way, for promotional material.

## If something looks wrong

- **A yellow banner about the directory** — the venue has no
  `article_blog_dir` configured.
- **A banner about a drifted command** — the installed copy of
  `article-ideas-scan.md` or `write-article.md` differs from the reference. The
  button updates the starter kit; if the command lives in a nested repository
  there is no button and you must update it by hand.
- **A button errors about a missing command** — the starter kit is not
  installed; install it from the Rotation page.
- **An article stuck in Writing** — open the Session log and check Questions:
  the writer is most likely waiting for an answer.
