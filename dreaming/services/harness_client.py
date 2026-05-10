"""HTTP/SSE harness adapter for orchestration UI."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator
from urllib.parse import urljoin
from uuid import uuid4

import httpx

log = logging.getLogger(__name__)


class HarnessError(RuntimeError):
    """Harness-side failure safe for user-visible logging."""


class HarnessClient:
    """Adapter for external harness start/stream/send APIs.

    Expected payloads are intentionally permissive:
    - start response: run_id/external_id/id anywhere in top-level or `data`
    - stream events: SSE `event:` + `data:` JSON OR NDJSON lines
    """

    def __init__(self, settings: "Any" = None, **kwargs):
        """Accept either a settings-like object (duck-typed via getattr) or kwargs.

        Compatible with ALC's original signature: HarnessClient(settings).
        Also supports HarnessClient(base_url=..., api_key=...) for direct construction.
        """
        def _get(key: str, default):
            if settings is not None:
                v = getattr(settings, key, None)
                if v is not None:
                    return v
            return kwargs.get(key, default)

        self.base_url = (str(_get("harness_base_url", "")) or "").strip().rstrip("/")
        self.api_key = (str(_get("harness_api_key", "")) or "").strip()
        self.timeout_sec = int(_get("harness_timeout_sec", 30) or 30)
        self.start_path = _get("harness_start_path", "/api/orchestration/start") \
            or "/api/orchestration/start"
        self.events_stream_path = _get(
            "harness_events_stream_path", "/api/orchestration/{run_id}/stream"
        ) or "/api/orchestration/{run_id}/stream"
        self.events_path = _get(
            "harness_events_path", "/api/orchestration/{run_id}/events"
        ) or "/api/orchestration/{run_id}/events"
        self.send_input_path = _get(
            "harness_send_input_path",
            "/api/orchestration/{run_id}/nodes/{node_id}/message",
        ) or "/api/orchestration/{run_id}/nodes/{node_id}/message"
        verify = _get("harness_verify_tls", True)
        self.verify_tls = True if verify is None else bool(verify)
        self._client: httpx.AsyncClient | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"Accept": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                timeout=self.timeout_sec,
                headers=headers,
                verify=self.verify_tls,
            )
        return self._client

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not self.base_url:
            raise HarnessError("harness_base_url не задан")
        return urljoin(self.base_url + "/", path.lstrip("/"))

    @staticmethod
    def _extract_run_id(payload: dict[str, Any]) -> str | None:
        for k in ("run_id", "external_id", "id"):
            v = payload.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        data = payload.get("data")
        if isinstance(data, dict):
            for k in ("run_id", "external_id", "id"):
                v = data.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        return None

    async def start_orchestration(self, goal: str, meta: dict[str, Any] | None = None) -> str:
        if not self.enabled:
            return f"stub-{uuid4()}"
        payload = {"goal": goal, "meta": meta or {}}
        client = await self._get_client()
        url = self._url(self.start_path)
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise HarnessError(f"Ошибка запуска оркестрации в harness: {e}") from None
        data = resp.json() if resp.content else {}
        run_id = self._extract_run_id(data if isinstance(data, dict) else {})
        if not run_id:
            raise HarnessError("Harness не вернул run_id")
        return run_id

    async def send_input(
        self,
        *,
        run_external_id: str | None,
        node_external_id: str | None,
        text: str,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": True, "echo": text}
        if not run_external_id:
            raise HarnessError("Неизвестен внешний run_id")
        node_id = node_external_id or "roman-orchestrator"
        path = self.send_input_path.format(run_id=run_external_id, node_id=node_id)
        url = self._url(path)
        body = {"text": text, "node_id": node_id, "run_id": run_external_id}
        client = await self._get_client()
        try:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise HarnessError(f"Ошибка отправки сообщения в harness: {e}") from None
        return resp.json() if resp.content else {"ok": True}

    async def stream_events(self, external_run_id: str) -> AsyncIterator[dict[str, Any]]:
        """Yield normalized events from harness stream endpoint.

        Output shape:
        {"event_type": "<type>", "payload": {...}}
        """
        if not self.enabled:
            return
        path = self.events_stream_path.format(run_id=external_run_id)
        url = self._url(path)
        client = await self._get_client()

        async with client.stream("GET", url, headers={"Accept": "text/event-stream"}) as resp:
            resp.raise_for_status()
            current_event = "message"
            async for raw in resp.aiter_lines():
                line = raw.strip()
                if not line:
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    current_event = line.split(":", 1)[1].strip() or "message"
                    continue
                if not line.startswith("data:"):
                    # NDJSON fallback
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    normalized = self._normalize_event(obj.get("event_type") or obj.get("type"), obj.get("payload") or obj)
                    if normalized:
                        yield normalized
                    continue
                data_str = line.split(":", 1)[1].strip()
                if not data_str:
                    continue
                try:
                    payload = json.loads(data_str)
                except json.JSONDecodeError:
                    payload = {"text": data_str}
                normalized = self._normalize_event(current_event, payload)
                if normalized:
                    yield normalized

    async def fetch_events(
        self, external_run_id: str, since: str | None = None
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Polling fallback for harnesses without SSE support."""
        if not self.enabled:
            return [], since
        path = self.events_path.format(run_id=external_run_id)
        url = self._url(path)
        params = {"since": since} if since else None
        client = await self._get_client()
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise HarnessError(f"Ошибка получения events из harness: {e}") from None
        body = resp.json() if resp.content else {}
        if isinstance(body, list):
            raw_events = body
            next_cursor = since
        else:
            raw_events = body.get("events") if isinstance(body.get("events"), list) else []
            next_cursor = body.get("next_cursor") or body.get("cursor") or since

        out: list[dict[str, Any]] = []
        for ev in raw_events:
            if not isinstance(ev, dict):
                continue
            normalized = self._normalize_event(ev.get("event_type") or ev.get("type"), ev.get("payload") or ev)
            if normalized:
                out.append(normalized)
        return out, (str(next_cursor) if next_cursor else None)

    @staticmethod
    def _normalize_event(event_type: str | None, payload: Any) -> dict[str, Any] | None:
        if not event_type:
            return None
        if not isinstance(payload, dict):
            payload = {"value": payload}
        alias = {
            "spawn": "node_created",
            "agent_spawned": "node_created",
            "node_spawned": "node_created",
            "status": "node_status_changed",
            "action": "node_action_changed",
            "message": "message_added",
            "chat": "message_added",
            "run_completed": "run_finished",
            "completed": "run_finished",
            "done": "run_finished",
        }
        et = alias.get(event_type, event_type)
        return {"event_type": et, "payload": payload}

    async def simulated_agent_reply(self, agent_name: str, text: str) -> str:
        return f"{agent_name}: получил сообщение \"{text}\"."

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class HarnessClientCache:
    """Per-project lazy cache. Resolves harness_* settings via project overrides."""

    def __init__(self):
        self._clients: dict[int, HarnessClient] = {}

    async def get_for_project(self, project, resolver) -> "HarnessClient | None":
        """Returns a HarnessClient for the project, or None if harness_base_url not set."""
        if project.id in self._clients:
            return self._clients[project.id]
        base_url = await resolver.get(project, "harness_base_url", "")
        if not base_url:
            return None

        # Build a minimal settings-like object from per-project overrides
        class _S:
            pass
        s = _S()
        for k in ("harness_base_url", "harness_api_key", "harness_timeout_sec",
                  "harness_stream_enabled", "harness_start_path",
                  "harness_events_stream_path", "harness_events_path",
                  "harness_send_input_path", "harness_verify_tls"):
            setattr(s, k, await resolver.get(project, k, None))
        client = HarnessClient(s)
        self._clients[project.id] = client
        return client

    def invalidate(self, project_id: int) -> None:
        self._clients.pop(project_id, None)
