"""One-shot server flash messages, rendered client-side via _app_modal.html."""
from __future__ import annotations
import json
from typing import Literal
from urllib.parse import quote, unquote

from fastapi import Request
from starlette.responses import Response


Level = Literal["info", "success", "error"]


def set_flash(response: Response, msg: str, level: Level = "info") -> None:
    """Attach a one-shot flash cookie to a response (typically a redirect).

    The cookie is non-HttpOnly because _app_modal.html's client script reads it
    on DOMContentLoaded, then deletes it. Only short, server-authored,
    user-visible text should ever be placed here — never credentials or tokens.

    The JSON payload is URL-encoded so that commas, semicolons, quotes, or
    Cyrillic characters in `msg` survive the cookie round-trip (Starlette's
    set_cookie does not URL-encode values). The client uses decodeURIComponent.
    """
    payload = quote(json.dumps({"msg": msg, "level": level}, ensure_ascii=False))
    response.set_cookie(
        key="flash",
        value=payload,
        max_age=10,
        path="/",
        httponly=False,
        samesite="lax",
    )


def read_flash(request: Request) -> dict | None:
    """Server-side read of the flash cookie. Currently unused — the client owns
    consumption — but provided for routes that may want to render the flash
    inline instead of relying on the modal."""
    raw = request.cookies.get("flash")
    if not raw:
        return None
    try:
        return json.loads(unquote(raw))
    except (json.JSONDecodeError, ValueError):
        return None
