"""Thin async client for Jira REST API v3.

Single purpose: create a Task in the configured Jira project with reporter =
assignee = the configured user. Used by the "Create Jira Task" button on the
Product Idea / Tech-Debt detail pages.

Project-aware: takes a duck-typed `settings` object whose attrs are read via
`getattr` so AppSettings doesn't have to declare every Jira field upfront. The
caller is also free to pass a `project_key_override` for per-project routing.
"""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)


class JiraError(RuntimeError):
    """User-facing Jira failure — message is safe to show in the UI."""


def _adf_description(item_url: str, item_id: str, body: str, kind: str = "идея") -> dict:
    """Build Atlassian Document Format body with a link back + body text."""
    paragraphs: list[dict] = [
        {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": f"{kind.capitalize()}: "},
                {
                    "type": "text",
                    "text": item_id,
                    "marks": [{"type": "link", "attrs": {"href": item_url}}],
                },
            ],
        }
    ]
    if body:
        paragraphs.append({
            "type": "paragraph",
            "content": [{"type": "text", "text": body[:3000]}],   # truncate to keep ADF small
        })
    return {"type": "doc", "version": 1, "content": paragraphs}


async def create_task(
    settings,
    *,
    summary: str,
    item_id: str,
    item_url: str,
    description: str = "",
    project_key_override: str | None = None,
    kind: str = "идея",
) -> dict:
    """Create a Jira Task. Returns {'key': 'RGS-123', 'url': '<browse-url>'}.

    Raises JiraError with a human-readable message on any failure.
    """
    jira_email = getattr(settings, "jira_email", None)
    jira_api_token = getattr(settings, "jira_api_token", None)
    jira_user_account_id = getattr(settings, "jira_user_account_id", None)
    jira_url = getattr(settings, "jira_url", None)
    if not jira_email or not jira_api_token:
        raise JiraError("Настройте Jira (email + API token) в /settings")
    if not jira_user_account_id:
        raise JiraError("Настройте jira_user_account_id в /settings")
    if not jira_url:
        raise JiraError("Настройте jira_url в /settings")

    project_key = project_key_override or getattr(settings, "jira_project_key", None)
    if not project_key:
        raise JiraError("Не задан jira_project_key (ни глобально, ни в project override)")

    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": "Task"},
            "reporter": {"accountId": jira_user_account_id},
            "assignee": {"accountId": jira_user_account_id},
            "description": _adf_description(item_url, item_id, description, kind),
        }
    }

    url = f"{jira_url.rstrip('/')}/rest/api/3/issue"
    auth = (jira_email, jira_api_token)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, auth=auth)
    except httpx.TimeoutException:
        raise JiraError("Jira не отвечает (timeout 10s)") from None
    except httpx.ConnectError as e:
        raise JiraError(f"Не удалось подключиться к Jira: {e}") from None

    if resp.status_code >= 400:
        detail = _extract_error(resp)
        log.warning("Jira create_task failed %s: %s", resp.status_code, detail)
        raise JiraError(f"Jira вернула {resp.status_code}: {detail}")

    data = resp.json()
    key = data.get("key")
    if not key:
        raise JiraError(f"Jira ответила без key: {data}")

    browse_url = f"{jira_url.rstrip('/')}/browse/{key}"
    log.info("Created Jira Task %s for %s", key, item_id)
    return {"key": key, "url": browse_url}


def _extract_error(resp: httpx.Response) -> str:
    """Pull the most useful message out of a Jira error body."""
    try:
        data = resp.json()
    except Exception:
        return resp.text[:300] or resp.reason_phrase
    msgs = data.get("errorMessages") or []
    errs = data.get("errors") or {}
    parts: list[str] = list(msgs)
    parts.extend(f"{k}: {v}" for k, v in errs.items())
    return "; ".join(parts) or (resp.text[:300] or resp.reason_phrase)
