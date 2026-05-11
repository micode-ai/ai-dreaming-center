---
description: Scan the repository for latent product-idea opportunities and write findings.
---

You are running inside Claude Code, spawned by the AI Dreaming Center
(weekly scanner or on-demand) to surface **product** ideas — features or
quality-of-life improvements that would be valuable for the project's
users.

## What you have

- `cwd` is the project repository root.
- Target directory: `docs/product-ideas/` (already created by DC).
- Env vars: `LEARNING_SESSION_ID`, `DREAMING_API_URL`, `DREAMING_PROJECT_SLUG`.

## What to do

1. **Understand what this product is.** Read:
   - `README.md`, `CLAUDE.md`
   - `package.json` description, `pyproject.toml` description
   - Any `user_docs/` or `docs/user/` folder
   - Recent commits — what's been shipped lately

2. **Find idea sources in the repo:**
   - Comments like `// TODO: would be nice if ...`, `// future: ...`
   - User-facing strings that hint at a missing feature ("coming soon",
     "not yet implemented", "TODO: add X")
   - Inconsistencies in the UX (one page has X, another doesn't)
   - Recently-fixed bug categories that suggest a structural improvement
   - Empty / sparse sections of the product

3. **Pick 3–7 ideas with real user impact.** Each idea must:
   - Solve a concrete user problem (not "refactor X").
   - Be small enough to ship in <2 weeks.
   - Not duplicate something already on the roadmap.

4. **For each idea, write `docs/product-ideas/{slug}.md`:**

   ```markdown
   ---
   id: {slug}
   title: '{one-line title — see YAML escaping note below}'
   status: idea           # idea | exploring | approved | building | shipped | dropped
   priority: P2           # P1 high / P2 normal / P3 nice-to-have
   created_at: {YYYY-MM-DD}
   jira_ticket:           # leave empty — DC will fill via "→ Jira" button
   ---

   # {title}

   ## User story
   As a {user type}, I want {capability}, so that {outcome}.

   ## Value hypothesis
   Why this matters — what does the user feel / save / unlock?

   ## Sketch
   3–5 bullets: what would the feature actually do? Be concrete.

   ## Open questions
   Bullets — what's unclear, what to validate, what could kill this idea.

   ## Cost estimate
   One sentence: rough effort (hours / days / weeks).
   ```

**YAML escaping note (critical — otherwise the DC parser drops the file
silently):**

   - **Always wrap the title in single quotes.** Frontmatter is YAML — a
     bare value can't contain `"`, `:`, `?`, or `—` safely. Single-quote
     the whole title and you're fine: `title: 'Foo "bar" baz'`.
   - If the title itself contains a single quote, double it: `'don''t'`.
   - Don't mix quotes (`title: "foo" — bar` is invalid — anything after
     the closing `"` makes YAML angry).
   - Other fields (`id`, `status`, `priority`, `created_at`) are simple
     alphanumeric or date — no quoting needed.

5. **Don't duplicate** — read existing files in `docs/product-ideas/`
   first; skip ideas already filed.

6. **Report back:**

   ```bash
   curl -s -X POST "$DREAMING_API_URL/api/session/finish" \
     -H "Content-Type: application/json" \
     -d "{\"session_id\":\"$LEARNING_SESSION_ID\",\"status\":\"success\"}"
   ```

## Rules

- Do **not** edit code or other files.
- Focus on **product** ideas (user value), not engineering tasks — those
  belong in `docs/tech-debt/`.
- Skip "implement X library" / "rewrite Y in Rust" — that's not a product
  idea.
