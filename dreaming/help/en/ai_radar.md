## What this section is for

AI Radar watches the outside world: it collects publications and releases over
RSS and Atom from the sites on a watchlist and puts them in one feed. It is the
only section of the app that looks outward rather than into your projects.

A radar finding is not a task. It is a prompt: to read it, to record it as a
note in a project, or to turn it into an article topic.

## What is on screen

The feed of findings: title, source, date, and a link to the original.

At the top, the watched sources with a per-source count for the last week. The
watchlist itself is a file, and its path is shown on the page.

Filters: by status, by source, by age in days, plus a "show hidden" toggle —
dismissed findings are kept out of the feed by default.

Up to two hundred findings are read from the database; search and sorting work
over those, in the browser.

## What you can do

- **Scan now** — walk the watchlist immediately. The scan is synchronous, so
  the page waits for it; it is bounded in time and in concurrent requests, so
  it will not hang for long.
- **Change the status** — mark a finding as read, dismissed, and so on.
- **Pin to a project** — attach the finding to a particular project so it is
  not lost.
- **Save as a note** — store the finding in a chosen project.
- **Propose an article** — creates an article proposal in the chosen project.
  The evidence is assembled from the finding itself: source, title, date and
  link — a fact by construction rather than a retelling. If that article has
  already been proposed, the app says so and does not add a second row to the
  queue.

The apply button supports only one kind so far: a note. The other kinds are
declared but not implemented, and choosing one returns a clear error rather
than silently doing nothing.

## Related sections

- **Articles** — where a finding goes once you propose an article from it.
- **Notes** — where saved notes end up.

## If something looks wrong

- **The feed is empty** — the scan has never run, or the watchlist is empty.
  The path to the watchlist file is shown on the page.
- **A source is listed but has no findings** — its feed is unreachable or does
  not serve RSS/Atom. Run a scan and see whether its weekly count moves.
- **A finding disappeared from the feed** — it was dismissed. Turn on "show
  hidden".
- **The propose-article button says "already proposed"** — this finding has
  already become a topic; look for it in Articles.
