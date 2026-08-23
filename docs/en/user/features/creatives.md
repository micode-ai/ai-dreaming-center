# Creatives

`/p/{slug}/creatives` — the queue of promotional campaigns: topic → approval →
build by the venue's own agent (images, video, post copy) → review → revision
or publish by commit. The same loop as [articles](articles.md), but with
attachments, formats/locales, and a render preview instead of text.

There is no cross-project queue for creatives yet (no `/articles` equivalent)
— only the page inside a specific project.

## Contents

- [Where campaigns come from](#where-campaigns-come-from)
- [What the page shows](#what-the-page-shows)
- [The "Add your own campaign" form](#the-add-your-own-campaign-form)
- [The campaign card](#the-campaign-card)
- [Buttons by status](#buttons-by-status)
- [Attaching material](#attaching-material)
- [Previewing renders](#previewing-renders)
- [Revision](#revision)
- [Publishing](#publishing-1)
- [If something got stuck](#if-something-got-stuck)
- [If the directory is not configured](#if-the-directory-is-not-configured)
- [A typical working session](#a-typical-working-session-1)

## Where campaigns come from

Two sources (articles have four — there's no "Propose a campaign" button on an
AI Radar or an idea card):

1. **The "Propose campaigns" button** on the page itself — runs
   `/creative-ideas-scan`: a read-only session looks at recent commits,
   product docs, neighbouring campaigns, and posts 3–7 ideas each naming the
   fact it rests on.
2. **The "Add your own campaign" form** — a topic, an opening prompt, a venue,
   formats/locales (leave blank to use the venue's own settings), and
   **files right away**, if you already have them at hand.

## What the page shows

At the top: the total campaign count, who is currently building them
(`maker: self` or an agent's name), the venue's campaign directory and its
configured formats/locales, and the "Propose campaigns" button.

If `creative_dir` is not configured for the venue at all — a yellow banner
instead of the list: the pipeline has nowhere to put a campaign, and that's
the first thing to fix in settings.

Cards are grouped by status:

| Status | Meaning |
|---|---|
| Proposed | proposed, awaiting a decision |
| Making | being built right now |
| Drafted | ready to review |
| Published | published |
| Rejected | rejected |
| Failed | the build failed or was cancelled |

## The "Add your own campaign" form

Unlike articles, here you can attach material **in the same step** you propose
a campaign — no need to find the card again afterwards to hand it over. The
file field takes several files at once (png, jpg, gif, webp, mp4, mov, webm).
If a campaign with the same slug already exists, the files still attach to it
(unless it's currently being built) rather than silently vanishing.

## The campaign card

- Title, status badge, monospace slug.
- A venue badge, when it differs from the current project.
- The evidence line, formats/locales, tags.
- What's already attached — thumbnail previews for images, filename badges
  for video (video doesn't play right on the card).
- **Preview** and **Session log** buttons, when there's something to show.
- The error and the build output, when applicable.

## Buttons by status

| Status | Buttons |
|---|---|
| Proposed | **Make** (dispatches the maker), **Reject**, a venue select |
| Failed | **Retry**, a venue select |
| Making | **Cancel** (moves it to Failed; does not kill the session itself) |
| Drafted | **Publish** (if the gate allows it) or the refusal reason as text, plus a "build passed / unverified / build failed" badge |
| Rejected | **Back to the queue** |
| Published | the commit (first 8 chars of the sha) and the build-result badge |

## Attaching material

While a campaign is Proposed / Approved / Failed / Drafted, an "Attach
material" block (or "Attach more" once something is already attached) unfolds
under the card: pick files, click **Attach**. Attaching is closed during
Making — the maker has already listed the directory, and a file slipped
underneath gains nothing but a race.

There's no UI to remove an attachment — only by hand on disk or through git.

## Previewing renders

The **Preview** button opens tabs for each (format, locale) pair — say
"post-4x5 · pl" and "story · en". Inside a tab: the renders themselves (an
image, or a video with a player) and the post copy that goes with them,
rendered as markdown. A render that couldn't be classified from its filename
shows up separately, under "outside the formats".

Whatever a human attached is visible on the same page in a collapsible block —
judging an ad only makes sense next to the material it was built from.

## Revision

The drafted preview page has a "Send back for revision" block with automatic
findings (when the venue has `creative_formats` / `creative_locales`
configured):

- no render at all for a declared format;
- no render for one of the locales;
- a render at the wrong size for its format (e.g. `story` should be
  1080×1920 — a different size means the platform crops it on its own,
  not the way it was meant to look);
- no post copy at all.

Plus a free-text box. The button re-dispatches the maker into the same slug
and directory — a revision of the campaign, not a new one from scratch.

## Publishing

The **Publish** button is available only when the campaign is Drafted,
publishing is not turned off in the venue's settings
(`creative_publish_mode`), and — if a build command is configured — it ran
successfully. Publishing commits everything the maker named (renders and post
copy together), plus, if configured, `creative_publish_extra_paths`.
Publishing asks for confirmation — "Commit the campaign's renders and copy to
the repository?" — before committing anything.

## If something got stuck

If the maker's session dies (a crashed process, a watchdog kill) while
Making, the card does **not** move to Failed on its own as reliably as an
article does — articles have a background check every 5 minutes, creatives
don't have one today. If a card sits in Making unusually long, open **Session
log**, confirm the process is really gone, and click **Cancel** by hand.

## If the directory is not configured

`/p/{slug}/settings` → "Creatives" group → `creative_dir` → Override → the
absolute path where campaigns will live (create it by hand, DC will not create
it). Formats (`creative_formats`) and locales (`creative_locales`) live in the
same group; leave them blank to get the default
`post-4x5,story,reel-4x5,reel` for formats and nothing for locales (the maker
decides on its own).

## A typical working session

1. Someone on the team sends over screenshots and a clip for an upcoming ad —
   you open `/p/{slug}/creatives`, expand "Add your own campaign", write the
   topic and an opening prompt, attach the files, click **Add**.
2. Look at the card in Proposed — if the topic and evidence check out, click
   **Make**.
3. While it builds (`Making`, can take minutes — reels aren't fast) — come
   back later.
4. Ready (`Drafted`) — **Preview**, look through the renders by format and
   locale, read the post copy.
5. Not happy with it — tick findings and/or write your own notes, **Send back
   for revision**. Happy with it — **Publish**, confirm.
6. The campaign is Published — a commit lands in the venue's repository,
   nothing more to do with the card.

---

See also:
- [`../../features/creatives.md`](../../features/creatives.md) — the
  technical internals: how it differs from articles, publishing by commit, the
  known reconcile gap.
- [`articles.md`](articles.md) — the parallel page for articles, where almost
  all of the machinery came from.
- [`../../routes.md`](../../routes.md) — the full route list.
- [`../../configuration.md`](../../configuration.md) — every `creative_*` key.
