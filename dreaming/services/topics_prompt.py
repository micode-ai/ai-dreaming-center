"""Build the `extra_prompt` block fed into /self-study from custom_topics."""
from __future__ import annotations


async def build_topics_extra_prompt(db, project_id: int, agent_name: str) -> str:
    """Returns a markdown block listing active custom_topics targeted at this
    agent, or "" if none. The empty case is important: callers prepend the
    string unconditionally, so "" must mean "no change to current behavior".
    """
    rows = await db.list_custom_topics_for_agent(project_id, agent_name)
    if not rows:
        return ""
    blocks = ["## Темы на сегодня (из DC)"]
    for r in rows:
        blocks.append(f"### {r['title']}")
        if r["module"]:
            blocks.append(f"Модуль: {r['module']}")
        if r["question"]:
            blocks.append(f"Что изучить: {r['question']}")
        if r["why_important"]:
            blocks.append(f"Почему важно: {r['why_important']}")
        blocks.append("")
    return "\n".join(blocks).rstrip()
