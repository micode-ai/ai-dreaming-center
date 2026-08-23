## What this section is for

Wiki is the project's knowledge base: the domain and module descriptions that
agents write and maintain. Unlike self-study notes — which are personal
write-ups from a single session — the wiki is the shared, structured picture of
the project.

This screen is not an editor. It shows whether a wiki exists and what is in it,
and gives you two buttons that set agents to work on it.

## What is on screen

The path to the wiki directory (`wiki_dir` in project settings) and whether it
exists.

If it does: how many domains it holds and the first twenty names. Domains are
found by convention, in two possible layouts:

1. `<wiki_dir>/domains/*.md` — used if that folder exists;
2. otherwise `*.md` at the root of the wiki directory.

So with a flat layout, every markdown file at the root counts as a domain.

## What you can do

- **Bootstrap** — runs `/wiki-bootstrap`: an agent walks the project and
  creates the initial wiki structure. Needed once, on an empty project.
- **Lint** — runs `/wiki-lint`: an agent looks for stale pages and broken
  references.
- **Open a page** — read the contents of a single wiki file.

Both buttons start a full Claude session. While one is running the button
shows that, so you cannot start a second of the same kind. Follow its progress
in the Live log.

## Related sections

- **Wiki health** — coverage metrics and trends over the same wiki.
- **Notes** — the agents' personal write-ups, separate from the wiki.
- **Live log** — where a running bootstrap or lint is visible.

## If something looks wrong

- **The directory is not set** — set `wiki_dir` in project settings, or use
  the one-button setup on the dashboard.
- **The directory is set but does not exist** — either the path is wrong or
  the wiki has never been created: run Bootstrap.
- **Zero domains although files exist** — the files are not where the app
  looks. Check this: if a `domains/` folder is present, only files inside it
  are counted and files at the root are ignored.
- **A button does nothing** — a run of that kind is already in progress.
