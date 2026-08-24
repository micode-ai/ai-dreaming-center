## What this section is for

Creatives is the pipeline for promotional campaigns: a topic, approval,
assembly by an agent (images, video, post copy), review, then revision or
publication as a commit.

The same cycle as articles, but with attachments, formats and locales, and with
a preview of renders instead of text. There is no cross-project queue here as
there is for articles — only the page inside a project.

## Where campaigns come from

Two sources rather than the four articles has: AI Radar and idea cards have no
"propose a campaign" button.

- **"Propose campaigns"** — runs `/creative-ideas-scan`: the session only reads
  recent commits, product documentation and neighbouring campaigns, then
  proposes three to seven ideas, each resting on a fact.
- **The "Add your own campaign" form** — topic, prompt, venue, formats and
  locales (leave them empty to take the venue's settings), and files straight
  away if you already have the material.

The form takes several files at once: png, jpg, gif, webp, mp4, mov, webm. If a
campaign with that slug already exists the files attach to it rather than
being silently lost — provided it is not mid-assembly.

## The lifecycle

| Status | What it means | Buttons |
|---|---|---|
| **Proposed** | Awaiting a decision. | Make, Reject, Already made, venue select |
| **Making** | Being assembled. | Cancel |
| **Drafted** | Ready for review. | Preview, Publish |
| **Published** | Published, with the commit. | — |
| **Already made** | Closed without assembling: the work exists. | Back to the queue |
| **Rejected** | Turned down. | Back to the queue |
| **Failed** | Assembly crashed or was cancelled. | Retry, Already made, Session log |

**"Already made" is not a rejection.** Rejected says the idea was wrong;
already made says it was right and the work exists. Coming back to the queue a
month later you read those two differently, and a scan will not re-propose the
slug in either case. The decision reverses with the same button rejected
campaigns use.

**Cancel** moves it to Failed but does not kill the session: a live process
finishes anyway, the card just stops waiting.

## Attaching material

While a campaign is Proposed, Failed or Drafted, an attach block opens under
the card.

During assembly attaching is closed. The reason is simple: the maker has
already read the directory listing, and a file slipped under its hand gains
nothing while creating a race.

An attached file cannot be removed from the interface — only on disk or
through git.

## Preview

**Preview** lays the renders out in tabs of the form "format · locale", such as
`post-4x5 · pl` and `story · en`. Inside are the renders themselves (an image,
or a video with a player) and the post copy that goes with them.

A render that could not be matched to any format by its filename goes into a
separate list rather than disappearing.

The material you attached is shown on the same page: judging an advert makes
sense alongside what it was made from.

## Revision

The preview page has "Send back for revision" with automatic findings, when the
venue has formats and locales configured:

- no render at all for a declared format;
- nothing produced for one of the locales;
- a render that is not the size the format declares — `story` should be
  1080×1920, and if it is not, the platform crops it its own way rather than
  yours;
- no post copy at all.

Plus a free-text field. The button sends the maker back with the same slug and
directory — a revision of the campaign, not a new one from scratch.

## Publishing

**Publish** is available only when the campaign is Drafted, publishing is not
switched off in the venue's settings, and — if a build command is configured —
it succeeded.

Everything the maker named is committed, renders and copy together, plus any
extra paths configured. The app asks for confirmation before committing.

## When the maker asks

The maker is forbidden from inventing a number, a customer or a testimonial. If
the copy needs one and it cannot be established, the maker asks and waits — a
campaign card in Making shows a link to the Questions section. Answer and it
carries on; dismiss the question, or never answer, and it fails the campaign
honestly, naming the question, rather than shipping an advert built on an
invented fact.

The wait is not open-ended: the watchdog will not kill the session for silence
while a question is pending, but the session's own turn and time ceilings still
apply.

## Related sections

- **Articles** — the same pipeline for text, with four topic sources and a
  cross-project queue.
- **Questions** — where to answer if the maker asked something.
- **Live log** — the progress of an assembly in flight.

## If something looks wrong

- **A yellow banner instead of the list** — the venue has no `creative_dir`
  configured and the pipeline has nowhere to put a campaign. Fix that first.
- **A campaign stuck in Making** — check the Session log. The scheduler moves
  campaigns whose process is already dead to Failed by itself, but you need not
  wait for it: Cancel does the same at once.
- **The tabs are empty although renders exist** — the filenames do not match
  the declared formats; look in the "outside the formats" list.
