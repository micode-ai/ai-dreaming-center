## What this section is for

Wiki health answers whether the wiki is growing or rotting. Two things: a
snapshot of coverage right now, and metrics plotted over time.

## Where the data comes from

By two separate paths, which is worth knowing because they break
independently.

**The coverage snapshot** is computed by the app on the fly from the files in
`wiki_dir`:

- **Covered** — the number of markdown files. If a `domains/` folder exists,
  files inside it are counted; otherwise files at the root, excluding `README`
  and `INDEX`.
- **Learning notes** — files under a `learning/` subfolder, if present.

An honest but blunt heuristic: it counts files, it does not check that
anything meaningful is written in them.

**The trends** are read from a ready-made `wiki-health-trends.md` written by
an agent. The app looks for it in three places, in order:

1. `<wiki_dir>/wiki-health-trends.md`
2. `<wiki_dir>/reports/wiki-health-trends.md`
3. `<wiki_dir>/03-Team/reports/wiki-health-trends.md`

The first one found wins. The file is split into dated sections and metrics
are pulled out of each; sections are then sorted by date. Which metrics those
are is decided by the agent writing the file — the app simply shows what it
finds.

## What is on screen

A bar with the current coverage numbers, the latest metric snapshot from the
trends, and the movement across dates.

If the trends file is missing, the page says so plainly and shows the path to
put it at. The coverage snapshot is still computed — the two parts do not
depend on each other.

## What you can do

- **Generate** — runs `wiki-health-scan`: an agent walks the wiki and updates
  the trends file. While the scan runs, the button shows it.

## Related sections

- **Wiki** — the knowledge base itself, and the bootstrap / lint buttons.
- **Live log** — where a running scan is visible.

## If something looks wrong

- **"Wiki directory not found"** — `wiki_dir` points elsewhere, or the wiki
  has never been created. Start from the Wiki section and its Bootstrap
  button.
- **"Trends file not found"** — health scans have never run, or the agent put
  the file somewhere other than the three expected places. The expected path
  is printed in the message.
- **Coverage looks suspiciously low** — most likely the layout: when a
  `domains/` folder exists, files at the root are not counted at all.
- **A trends parse error** — the file is there but not in the format the
  parser expects. The error text with the file path is shown on the page.
