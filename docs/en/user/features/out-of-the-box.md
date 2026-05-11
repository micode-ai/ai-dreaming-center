# Out-of-the-box setup

When you first open a new project in DC, you no longer have to manually copy
slash commands and write directory paths into `config.yaml`. Wherever the UI
used to say "not configured / does not exist", there is now an inline button
that creates the missing piece in a single click.

This page covers four mechanisms:

- [Bootstrap everything](#bootstrap-everything) — master button on the
  dashboard: runs starter-kit + autoconfig in one click.
- [Starter-kit](#starter-kit) — install slash commands (`/self-study`, weekly
  checklist, ...) from templates baked into the DC repo.
- [Directory autoconfig](#directory-autoconfig) — one-click creation of
  `docs/tech-debt/`, `docs/wiki/`, etc., with the corresponding `*_dir`
  setting saved automatically.
- [Session controls](#session-controls) — Stop / Delete / Force-close for
  stuck or stale rows.

## Contents

- [Bootstrap everything](#bootstrap-everything)
- [Starter-kit](#starter-kit)
  - [What lives in the template](#what-lives-in-the-template)
  - [Install via UI](#install-via-ui)
  - [Install via CLI](#install-via-cli)
  - [Extending the starter-kit](#extending-the-starter-kit)
- [Directory autoconfig](#directory-autoconfig)
  - [Which directories are covered](#which-directories-are-covered)
  - [Click flow](#click-flow)
  - [If you want a different path](#if-you-want-a-different-path)
- [Session controls](#session-controls)
  - [Stop / Force-close](#stop--force-close)
  - [Delete](#delete)
  - [Force-close all stale](#force-close-all-stale)

## Bootstrap everything

The master button lives on the **project dashboard** (`/p/{slug}/`) — the
first page you land on after clicking a project. When anything is still
unconfigured, a yellow banner appears at the top:

```
┌─ Проект ещё не настроен «из коробки» ─────────────────────────────────┐
│ Одна кнопка ниже сделает всё разом:                                    │
│  • скопирует 2 файла starter-kit (commands/self-study.md,              │
│    agents/lessons/_weekly-learning-checklist.md) в .claude/            │
│  • создаст 8 каталогов и пропишет в Settings:                          │
│    tech_debt_dir, product_ideas_dir, wiki_dir, evolutions_dir,         │
│    loops_dir, plans_dir, contracts_dir, sidecar_findings_dir           │
│                                                                         │
│ Existing files and existing overrides are left untouched.              │
│ Change the paths later in Settings if you don't like the defaults.     │
│                                                                         │
│ [ Bootstrap everything ]                                                │
└─────────────────────────────────────────────────────────────────────────┘
```

(The banner copy is in Russian by default — the localised UI follows your
`dc_locale` cookie.)

The button hits `POST /p/{slug}/bootstrap-all` and in one pass:

1. Runs `starter_kit.install(working_dir, force=False)` — copies every
   missing file from `templates/starter-kit/` into
   `{working_dir}/.claude/`. Existing files are not overwritten.
2. Runs `autoconfig.apply_all_defaults(skip_existing=True)` — for every key
   in `autoconfig.DEFAULTS` it creates the directory and saves the setting,
   **only if no override is set for that key**. If you've already typed your
   own `tech_debt_dir = ...` it will not be touched.

After clicking, the page re-renders: the yellow banner disappears (everything
is configured) and you see the regular dashboard with metrics and recent
sessions.

This master button does not replace the per-page buttons — those remain for
"I want to configure only this one feature" and "I deleted the directory and
want to re-create it" use cases.

## Starter-kit

Without a `/self-study` slash command, the claude CLI doesn't know what
`/self-study aba-architect` means, and it exits within 7 ms with status
`success` and zero cost. Symptom: `/p/{slug}/live` ends immediately, the
dashboard accumulates `success` sessions with no `note_path`.

### What lives in the template

`templates/starter-kit/` inside the DC repo is the source of truth for a set
of files that gets mirrored into `{project.working_dir}/.claude/`. The
template structure **mirrors** the `.claude/` layout one-to-one:

```
templates/starter-kit/
├── commands/
│   └── self-study.md                          → .claude/commands/self-study.md
└── agents/
    └── lessons/
        └── _weekly-learning-checklist.md       → .claude/agents/lessons/_weekly-learning-checklist.md
```

What's inside:

- **`commands/self-study.md`** — the slash command DC asks the claude CLI to
  run for every self-study spawn. It reads `.claude/agents/{name}.md`, samples
  the repo, writes a note to `.claude/agents/learning-notes/`, and POSTs to
  `/api/session/finish`. See [`self-study.md`](self-study.md).
- **`agents/lessons/_weekly-learning-checklist.md`** — a skeleton for the
  weekly learning checklist parsed by the Topics page. See
  [`topics-kanban.md`](topics-kanban.md).

Over time you can drop `/wiki-bootstrap.md`, `/tech-debt-scan.md` and any
other slash commands into this directory — the UI will start suggesting them
across all projects automatically.

### Install via UI

**The Rotation page** (`/p/{slug}/rotation`) is the main indicator. Right
under the "N agents in DB; M on disk" line you get one of two banners:

- **Yellow "Starter-kit slash-commands are missing"** — lists the missing
  files and offers the **Install starter kit** button.
- **Collapsed green "✓ starter kit installed (N files)"** — expand it to see
  what's installed plus a **Reinstall (overwrite)** button for pulling the
  latest version of the template over your existing files.

**The Topics page** (`/p/{slug}/topics`) — if the weekly checklist is the
specific file missing, this page shows its own yellow banner with a
**Создать заготовку checklist** button. Installing returns you to the Topics
page (not Rotation) so you can verify the result on the spot.

Any other page can grow the same kind of banner in the future — the
mechanism is shared (see [Extending the starter-kit](#extending-the-starter-kit)).

### Install via CLI

A CLI alternative — `scripts/install_starter_kit.py`. Useful when you don't
have UI access (re-bootstrapping an instance) or want to roll out to all
projects at once:

```bash
# one project by slug (reads working_dir from DB)
python scripts/install_starter_kit.py --slug ai-budget-assistant

# arbitrary path (skips DB lookup)
python scripts/install_starter_kit.py --working-dir "D:/Work/micode/foo"

# every enabled project
python scripts/install_starter_kit.py --all

# modifiers
--dry-run     # print what would be copied, write nothing
--force       # overwrite existing files
--db-path     # explicit path to data/dreaming.db
```

Default behaviour is **skip existing files**. If you tweaked `self-study.md`
to your taste, a repeat install leaves it alone unless you pass `--force`.

### Extending the starter-kit

To add a new slash command (e.g. `/wiki-bootstrap`, `/tech-debt-scan`):

1. Drop the file at `templates/starter-kit/commands/wiki-bootstrap.md` in the
   DC repo.
2. On the next visit to Rotation (or whichever page needs it), the banner
   automatically reports it as missing. Click → file is copied into the
   project.

No code, no endpoints, no service changes. `starter_kit.py` walks
`templates/starter-kit/**` recursively and diffs against
`{working_dir}/.claude/`.

## Directory autoconfig

Eight project pages depend on per-project settings like `tech_debt_dir`,
`wiki_dir`, `loops_dir`, etc. Previously, when these were unset, the page
said "not configured, go to Settings". Now you see a yellow banner with the
proposed path and a **Create directory and save setting** button.

### Which directories are covered

| Page | Setting key | Default path (relative to `working_dir`) |
|---|---|---|
| `/p/{slug}/tech-debt` | `tech_debt_dir` | `docs/tech-debt` |
| `/p/{slug}/ideas` | `product_ideas_dir` | `docs/product-ideas` |
| `/p/{slug}/wiki` | `wiki_dir` | `docs/wiki` |
| `/p/{slug}/evolutions` | `evolutions_dir` | `.claude/agents/_context` |
| `/p/{slug}/loops` | `loops_dir` | `docs/loops` |
| `/p/{slug}/plans` | `plans_dir` | `docs/plans` |
| `/p/{slug}/contracts` | `contracts_dir` | `docs/contracts` |
| `/p/{slug}/sidecar-findings` | `sidecar_findings_dir` | `.claude/agents/sidecar-findings` |

Defaults live in `dreaming/services/autoconfig.py:DEFAULTS`. Convention:
"human" artifacts go under `docs/<feature>/`, agent output (self-study notes,
sidecar reports) — under `.claude/agents/<feature>/`.

### Click flow

1. On a page like `/p/{slug}/tech-debt`, you see the yellow banner: "Tech-debt
   not configured yet. I'll create the directory: `D:\Work\micode\foo\docs\tech-debt`".
2. Click **Create directory and save setting**.
3. The POST hits `/p/{slug}/settings/autoconfig`. The server:
   - runs `mkdir -p` on the full path;
   - saves `tech_debt_dir = ...` into the `project_settings` table;
   - redirects back to the page via Referer header (same-origin check:
     redirect only if the path starts with `/p/{slug}`).
4. The page re-renders — now either showing an empty list ("no files yet") or
   real content if the directory already had stuff in it (someone may have
   committed files there).

The same banner reappears when the setting is set but the directory doesn't
exist (e.g. you changed the path manually). The button is the same — re-running
`mkdir -p` is idempotent.

### If you want a different path

Open `/p/{slug}/settings`, find the key (`tech_debt_dir` etc.), click
**override**, type your own path. If the directory doesn't yet exist — create
it through your file manager / `mkdir`.

Autoconfig is for fast bootstrap; the final configuration still lives in
Settings and is edited there.

### Wiki — special case

After autoconfig, the Wiki page sits in "directory exists, no domains" state.
`/p/{slug}/wiki` then shows a blue banner **"Wiki is still empty"** plus a
**Run /wiki-bootstrap** button. That button spawns claude CLI with the prompt
`/wiki-bootstrap`. When it finishes — refresh the page, see N domains. See
[`wiki.md`](wiki.md).

## Session controls

On the project dashboard (`/p/{slug}/`), the **Recent sessions** table now
has an Actions column, and a banner appears at the top whenever there are
stuck `running` rows.

### Stop / Force-close

For each row in `running` status:

- If the process is **alive** (present in `pm.list_running()`) — **Stop**
  button. Sends SIGTERM to the child claude process. After exit, `_cleanup`
  tries to update the DB row (see
  [troubleshooting.md](../../troubleshooting.md#reconcile-warning)).
- If the process **died** but the row is still `running` (an orphan — the
  status badge reads "orphan" in the table) — **Force-close** button. Calls
  `db.cancel_session(id)`, which sets `status='cancelled'`, `finished_at=now`.

Each action asks for confirmation through `confirm()`.

### Delete

Available for **any** status. Removes the row from `agent_learning_sessions`
entirely. If the process is still alive, it's killed first and the row is
deleted afterwards. Useful for clearing out garbage `failed` sessions from
the dashboard.

### Force-close all stale

If you have many orphans at once (accumulated from a server crash or the
Wave-0 reconcile bug) — a banner appears above the table:

```
N stuck running rows (process gone, DB never closed).   [ Force-close all stale ]
```

One click marks every running row for this project as `cancelled`. **It does
not kill live processes** — those are in `pm.running` and are excluded.

## See also

- [`self-study.md`](self-study.md) — what the `/self-study` slash command
  actually does.
- [`topics-kanban.md`](topics-kanban.md) — the format of
  `_weekly-learning-checklist.md`.
- [`settings.md`](settings.md) — Settings UI, override mechanics.
- Technical: [`../../services.md#starter-kit`](../../services.md#starter-kit),
  [`../../services.md#autoconfig`](../../services.md#autoconfig),
  [`../../routes.md#starter-kit`](../../routes.md#starter-kit).
