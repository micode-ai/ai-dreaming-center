# Wiki

`/p/{slug}/wiki` — project wiki status and the `Run /wiki-bootstrap` button for first-time generation.

## Contents

- [What wiki means in DC](#what-wiki-means-in-dc)
- [What the page shows](#what-the-page-shows)
- [Run /wiki-bootstrap](#run-wiki-bootstrap)
- [After the bootstrap](#after-the-bootstrap)
- [If a wiki already exists](#if-a-wiki-already-exists)
- [If wiki_dir is not configured](#if-wiki_dir-is-not-configured)

## What wiki means in DC

A wiki is a set of markdown files in `wiki_dir` (`{working_dir}/wiki/` by default), describing the project's domain structure. One file per domain (auth, billing, ui-shell, etc.). Used by agents in orchestration: when decomposing a goal Roman reads the domain files to figure out which part of the codebase the goal touches.

The exact wiki format depends on the starter kit / project conventions. DC just shows the number of domain files and their names — it doesn't parse or edit content.

## What the page shows

Open `/p/{slug}/wiki`. Logic:

**Case 1: `wiki_dir` is not configured.**
- Amber banner "Каталог wiki не настроен." (Wiki directory is not configured.)
- Settings link: "Пропиши `wiki_dir` в Settings или через CLI: `set_setting('wiki_dir', '...')`." (Set `wiki_dir` in Settings or via CLI: `set_setting('wiki_dir', '...')`.)

**Case 2: configured but does not exist.**
- Grey text: "Wiki не найдена. Каталог `{wiki_dir}` не существует." (Wiki not found. Directory `{wiki_dir}` does not exist.)
- Hint: "Можно запустить bootstrap прямо из UI — Claude CLI выполнит `/wiki-bootstrap` в рабочем каталоге проекта." (You can run bootstrap right from the UI — Claude CLI will execute `/wiki-bootstrap` in the project's working directory.)
- A blue button `Run /wiki-bootstrap (запустит claude)` (Run /wiki-bootstrap (will start claude)) (POST form).

**Case 3: exists and non-empty.**
- A white card with the status:
  - "Источник: `{wiki_dir}`" (Source: `{wiki_dir}`).
  - In big font: "N domains".
  - If wiki_dir has md files — a `<details>` block "show first N" with a monospace list of file names.

Names are shown without extension and path — only the short domain name.

## Run /wiki-bootstrap

The `Run /wiki-bootstrap` button only appears in case 2 (configured but does not exist).

What happens on click:
1. POST to `/p/{slug}/wiki/bootstrap`.
2. DC resolves claude_path and spawns `claude /wiki-bootstrap` with `cwd={working_dir}`.
3. Creates a row in `agent_learning_sessions` (with agent-name `_wiki-bootstrap` or similar).
4. Subscribes the live-log streamer.
5. Redirects the browser to `/p/{slug}/live`.

From there — in the live log you watch Claude:
1. Read `.claude/agents/` to understand the agent team.
2. Scan the codebase.
3. Determine domains (by directory structure / module boundaries).
4. Create `wiki_dir` if missing.
5. Write one md file per domain.

That usually takes 10–20 minutes. At the end you can refresh `/wiki` — you'll see case 3 with domain-count > 0.

## After the bootstrap

After a successful bootstrap:
- `wiki_dir` has md files for each domain.
- Roman, in orchestration runs, can read them (if so configured by his instructions).
- `/p/{slug}/wiki` shows count and list.

The domain wiki is not edited via UI. To add/change a domain:
- Open the md file by hand (Obsidian, VS Code, any editor).
- Or run an `/wiki-update` agent (if your starter kit has such a command).

## If a wiki already exists

If `wiki_dir` exists and has md files — the `Run /wiki-bootstrap` button is **not shown**. Intentional: bootstrap could overwrite existing files.

To re-bootstrap:
1. Delete `wiki_dir` by hand (or rename it `wiki.bak`).
2. Open `/wiki` — now case 2.
3. Click the button.

## If wiki_dir is not configured

By default `wiki_dir` is empty. To set it:
1. `/p/{slug}/settings` → find the `wiki_dir` key (usually in the Paths group).
2. Override → type, e.g. `D:\Work\micode\my-app\wiki\` (with or without trailing slash).
3. Save.
4. Go back to `/wiki` — the case will change.

If you want the wiki stored not in the project but in an Obsidian vault — type the vault path into `wiki_dir`. That works: DC just reads md files from the directory, it doesn't inherit from the project structure.

---

See also:
- [`orchestration.md`](orchestration.md) — Roman may use the wiki for decomposition.
- [`settings.md`](settings.md) — where `wiki_dir` lives.
- [`live-log.md`](live-log.md) — watching the bootstrap session.
- Technical: [`../../features/pipelines.md`](../../features/pipelines.md).
