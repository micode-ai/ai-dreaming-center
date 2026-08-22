---
description: Build one approved promotional campaign, then report its files and verification
---

# Make creative

Build the campaign the AI Dreaming Center approved, in this venue's own shape,
then report exactly what you produced.

## 1. Read the brief

```bash
curl -s "$DREAMING_API_URL/api/creatives/<proposal-id>"
```

You get `title`, `angle`, `slug_hint`, `evidence`, `formats`, `locales`,
`tags_json`, `revision_notes`, `draft_ref`. The evidence is the fact the
campaign must be true to — a creative that overstates it is worse than none,
because it is a claim about the product with the product's name on it.

Environment, all set by the center:

| Variable | What it is |
|---|---|
| `$DC_CREATIVE_DIR` | the campaign's directory, relative to your cwd |
| `$DC_CREATIVE_SLUG` | the campaign slug — **fixed**, never rename it |
| `$DC_CREATIVE_FORMATS` | the formats this venue produces |
| `$DC_CREATIVE_LOCALES` | the locales to produce |
| `$DC_CREATIVE_VERIFY_CMD` | the build/verify command, if the venue has one |
| `$DC_CREATIVE_AGENT` | the agent the center resolved for this work |
| `$DC_CREATIVE_SUBJECT_DIR` | the repository the campaign is *about* |
| `$DC_CREATIVE_REVISION_NOTES` | non-empty only when a human sent this back |
| `$DC_CREATIVE_DRAFT_REF` | what you produced last time, if this is a revision |

Prefer `$DC_CREATIVE_FORMATS` and `$DC_CREATIVE_LOCALES` over the payload's own
fields: those are the operator's decision for this venue, the payload's are the
scan's guess when it proposed.

## 1a. If this is a revision, it is not a new campaign

When `$DC_CREATIVE_REVISION_NOTES` is non-empty, a human looked at your renders
and sent them back. `$DC_CREATIVE_DRAFT_REF` lists what you produced.

- **Improve those files in place.** Same slug, same directory, same filenames
  where the format is unchanged. A second campaign on the same subject leaves
  the venue with two, and whichever the index sorts first is the one that ships.
- **Address every note.** "The opening frame is weak" means re-cut the opening,
  not re-export the same frames at a different bitrate.
- If a note asks for a format you have not built, find how the neighbouring
  campaigns build theirs before inventing your own way.
- If a note is wrong or impossible, say so in your report rather than
  half-doing it.

Then verify and report exactly as a first build does.

## 2. Know which repository is which

Your cwd is the **venue** — the repository the campaign is produced in. The
campaign may be *about* a different project, at `$DC_CREATIVE_SUBJECT_DIR`.
Facts come from the subject; conventions come from the venue. Never guess a
fact about the subject from the venue's own docs.

## 3. Use what the human attached, and copy the venue's shape

Look in `$DC_CREATIVE_DIR/src/` first. Screen captures and clips a human put
there are the raw material for this campaign, and they are why the campaign
was approved rather than left as an idea. If `src/` is empty and the venue's
templates need footage, say so in your report rather than producing an empty
frame.

**The venue owns the shape.** Before building anything, read two or three
existing campaigns in the creatives directory and copy their layout exactly:
where templates live, where renders go, how filenames encode format and locale,
which build script produces what. Do not invent a second convention beside the
one already there.

Filenames matter to the center: it reads the format and the locale off the end
of a render's name — `<something>-<format>-<locale>.<ext>`, e.g.
`voice-entry-post-4x5-pl.png`. A render the center cannot classify still shows
in the preview, but under "outside the formats" rather than on its tab.

Declared sizes: `post-4x5` and `reel-4x5` are 1080×1350, `story` and `reel` are
1080×1920. A render at the wrong size comes straight back as a revision.

**Do not read a large data file whole.** If the venue keeps a registry, sample
one entry and mutate the file with a script that does not print its contents.
Reading a 780 KB file to append to it is how a session runs out of room before
it produces anything.

## 4. Write the post copy

Renders without copy are half a campaign. Write the text that ships with them,
in every locale, where the venue keeps its copy — the neighbouring campaigns
show you where. Same rule as the visuals: no claim the evidence does not carry.

## 5. Verify

If `$DC_CREATIVE_VERIFY_CMD` is set, run it and capture the output verbatim.
Reels take minutes; that is expected, and it is why this runs here rather than
in the center's web request. A red build is a red build — report it as such
rather than reporting success and letting the publish gate discover it.

## 6. Report back

```bash
curl -s -X POST "$DREAMING_API_URL/api/creatives/<proposal-id>/made" \
  -H "Content-Type: application/json" \
  -d '{"draft_ref": "<comma-separated paths>",
       "verify_output": "<verbatim, trimmed>",
       "maker_agent": "<agent name or self>",
       "verify_ok": true}'
```

`draft_ref` contract — the center validates this before it will commit
anything, and there is no UI to fix a bad value afterwards:

- **Every path is relative to your cwd**, the repository root you are standing
  in. Not relative to `$DC_CREATIVE_DIR`.
- **Comma-separated**, never a JSON array.
- **List every file the campaign needs**: each render, the post copy, and any
  template, build script or registry entry you added or changed. A file you
  leave out is a file publishing will not commit, and the campaign will ship
  incomplete.
- Each entry must be an existing regular file — no directories, no globs, no
  `..`, no absolute paths.

On failure, report honestly and nothing else:

```bash
curl -s -X POST "$DREAMING_API_URL/api/creatives/<proposal-id>/made" \
  -H "Content-Type: application/json" \
  -d '{"error_message": "<what failed, in one or two sentences>"}'
```

## Rules

- Never rename or move the campaign directory. Attachments arrived there.
- Never delete a human's attachment, even after using it.
- Never invent a number, a customer, a testimonial or a screenshot of something
  that does not exist. A fabricated ad is the worst thing this pipeline could
  produce.
- Do not commit or push. Publishing is a human's button.
- Do not amend or rewrite existing commits.
