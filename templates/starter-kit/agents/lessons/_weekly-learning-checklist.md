---
week: W??
---

# Weekly Learning Checklist — W??

This file lists the topics each agent should focus on during this week's
self-study sessions. The Dreaming Center reads it from
`.claude/agents/lessons/_weekly-learning-checklist.md` and injects the
matching topics into the `/self-study` prompt for each agent.

## Format

- Each `## <agent-name>` H2 header starts a bucket for that agent.
- Bullet points (`- ...`) under that header become individual topics.
- Numbering is automatic — don't add numbers yourself.
- `## Приоритет недели` and `## Общие (любой агент)` are reserved section
  names that the parser skips. Use them for human notes that should not
  be routed to any specific agent.

Edit this file weekly. The `week:` field in frontmatter is just a label,
shown on the Топики page.

## Приоритет недели

- (a one-sentence description of this week's overall focus)

## Общие (любой агент)

- (topics every agent should be aware of, e.g. major refactors in flight)

## <agent-name>

- (replace `<agent-name>` with the basename of a file in `.claude/agents/`,
  e.g. `aba-architect`, then list 1–3 topics under it)
- ...
