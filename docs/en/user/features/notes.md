# Notes

`/p/{slug}/notes` — a browser over the notes that agents write after self-study sessions. A simple read-only page: list of files + raw-content viewer.

## Contents

- [What the page shows](#what-the-page-shows)
- [Where the files come from](#where-the-files-come-from)
- [Raw-content viewer](#raw-content-viewer)
- [Path-traversal protection](#path-traversal-protection)
- [If there are no notes](#if-there-are-no-notes)

## What the page shows

Open `/p/{slug}/notes`. At the top — a line like: "Источник: `{learning_notes_dir}`" (Source: `{learning_notes_dir}`). If the directory does not exist — next to it, in red: "(каталог не существует)" ((directory does not exist)).

If there are files — a two-column table:
- **path** — path relative to `learning_notes_dir`. Clickable link (blue, monospace).
- **size** — bytes (right-aligned).

Example:
```
2026-05-09-vera.md           4231
2026-05-08-svetlana.md       3892
old/2026-04-15-team-lead.md  5021
```

If there are subdirectories inside `learning_notes_dir` — DC walks recursively. Files are filtered by `.md` extension (markdown only).

## Where the files come from

A note is a markdown file the agent writes at the end of a self-study session. By default `learning_notes_dir` = `{working_dir}/.claude/agents/learning-notes/`. Can be overridden in settings (`learning_notes_dir`).

The file name is up to the agent (whatever is written in the starter-kit's `/self-study` slash command). Usually `{date}-{agent}.md` or `{date}/{agent}.md`.

When the session finishes:
1. Claude writes the file (via its Write tool).
2. Optionally via the callback `POST /api/session/finish` returns the path to DC — DC stores it in `agent_learning_sessions.note_path`.
3. On `/p/{slug}/dashboard` recent sessions you see the agent name and (if note_path is set) — it as a clickable link.

In the `/notes` table you see **every** md file in the directory, not just the newest. Convenient: you can come back to an old note if you need to remember something.

## Raw-content viewer

Clicking the link in the `path` column goes to `/p/{slug}/notes/raw?path=...`. DC returns plain text (not rendered as HTML, no markdown parsing). The browser shows the contents in standard monospace.

This is intentional: notes often contain code blocks, mermaid diagrams, frontmatter — the raw text is easier to copy into another tool (Obsidian, VS Code).

If you want pretty markdown rendering — open the file in Obsidian (if your project folder is an Obsidian vault) or in VS Code with markdown preview.

## Path-traversal protection

DC checks that the requested `path` does not escape `learning_notes_dir`. An attempt at `path=../../etc/passwd` or `path=../../config.yaml` returns 400.

Implementation: the path is resolved to absolute and checked to start with `learning_notes_dir`. Therefore the URL always carries a path **relative** to notes_dir.

## If there are no notes

If the directory is empty — you'll see the text "Конспектов нет. Они появляются после успешных self-study сессий (записываются в этот каталог)." (No notes. They appear after successful self-study sessions (written to this directory).)

When to expect the first note:
- Start any agent via `Start session` (see [`rotation.md`](rotation.md)).
- Wait for the session to finish (status `success`).
- Refresh `/notes` — you'll see it.

If the session finished `success` but there's no note — the `/self-study` slash command didn't write the file. Check its implementation in `~/.claude/commands/self-study.md`.

If the `learning_notes_dir` directory does not exist at all — DC will not create it automatically. Create it manually: `mkdir D:\Work\micode\my-app\.claude\agents\learning-notes`.

---

See also:
- [`self-study.md`](self-study.md) — what a session is and what it writes.
- [`rotation.md`](rotation.md) — starting an agent.
- [`settings.md`](settings.md) — where to change `learning_notes_dir`.
- Technical: [`../../routes.md#notes`](../../routes.md), [`../../features/pipelines.md`](../../features/pipelines.md).
