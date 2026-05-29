"""REST + WebSocket client for the Pollux API.

Kept thin on purpose — the API itself does all the heavy lifting. The
WebSocket helpers are sync wrappers around `asyncio.run()` so they slot
into Streamlit's synchronous script-rerun model without needing a
long-lived event loop.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Callable, Optional

import requests

# `websockets` raises ImportError if not installed; we import lazily so the
# rest of the client (REST calls) still works without it.
try:
    import websockets  # type: ignore
    _WS_AVAILABLE = True
except ImportError:
    websockets = None  # type: ignore
    _WS_AVAILABLE = False


class APIError(Exception):
    """Raised when an API call returns 4xx/5xx or the network fails."""


def _api_url() -> str:
    return os.environ.get("POLLUX_API_URL", "http://127.0.0.1:8001")


def _ws_url() -> str:
    base = _api_url()
    return base.replace("https://", "wss://").replace("http://", "ws://")


def _api_key() -> Optional[str]:
    return os.environ.get("POLLUX_API_KEY") or None


class APIClient:
    """Thin REST client. One instance per Streamlit script-run is fine —
    requests' connection pooling handles the rest."""

    def __init__(self) -> None:
        self.base_url = _api_url()
        self.timeout = 180  # Generous — full pipelines can take 30-60s.

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        key = _api_key()
        if key:
            h["X-API-Key"] = key
        return h

    def _get(self, path: str) -> Any:
        try:
            r = requests.get(
                f"{self.base_url}{path}",
                headers=self._headers(),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise APIError(f"Network error: {exc}") from exc
        if r.status_code >= 400:
            raise APIError(f"{r.status_code}: {r.text}")
        return r.json()

    def _post(self, path: str, json_body: dict) -> Any:
        try:
            r = requests.post(
                f"{self.base_url}{path}",
                json=json_body,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise APIError(f"Network error: {exc}") from exc
        if r.status_code >= 400:
            raise APIError(f"{r.status_code}: {r.text}")
        return r.json()

    # --- system ----------------------------------------------------------

    def health(self) -> dict:
        return self._get("/health")

    def list_agents(self) -> dict:
        return self._get("/agents")

    # --- tasks -----------------------------------------------------------

    def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> dict:
        params = [f"limit={limit}"]
        if status:
            params.append(f"status={status}")
        return self._get(f"/tasks?{'&'.join(params)}")

    def get_task(self, task_id: str) -> dict:
        return self._get(f"/tasks/{task_id}")

    def submit_question(self, question: str, wait: bool = False) -> dict:
        suffix = "?wait=true" if wait else ""
        return self._post(f"/tasks/question{suffix}", {"question": question})

    def submit_ticket(
        self,
        subject: str,
        body: str,
        customer_id: Optional[str] = None,
        wait: bool = False,
    ) -> dict:
        suffix = "?wait=true" if wait else ""
        payload: dict = {"subject": subject, "body": body}
        if customer_id:
            payload["customer_id"] = customer_id
        return self._post(f"/tasks/ticket{suffix}", payload)

    def submit_meeting(
        self,
        transcript: str,
        meeting_title: str = "Untitled meeting",
        attendees: Optional[list[str]] = None,
        wait: bool = False,
    ) -> dict:
        suffix = "?wait=true" if wait else ""
        return self._post(
            f"/tasks/meeting{suffix}",
            {
                "transcript": transcript,
                "meeting_title": meeting_title,
                "attendees": attendees or [],
            },
        )


# --- WebSocket helpers ---------------------------------------------------

def stream_task_blocking(
    task_id: str,
    on_event: Callable[[dict], None],
    max_seconds: float = 600.0,
) -> list[dict]:
    """Subscribe to `/tasks/{id}/stream`, call `on_event` for each event,
    return the full list once the WebSocket closes (terminal status, error,
    or timeout).

    Streamlit runs scripts synchronously — this wraps the async WebSocket
    machinery so the page can render live progress without managing its own
    event loop.
    """
    if not _WS_AVAILABLE:
        raise APIError(
            "The `websockets` package is required for live streaming. "
            "Install with: pip install websockets"
        )

    async def _stream() -> list[dict]:
        events: list[dict] = []
        url = f"{_ws_url()}/tasks/{task_id}/stream"
        try:
            async with websockets.connect(url, open_timeout=10) as ws:
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=max_seconds)
                    except asyncio.TimeoutError:
                        raise APIError(
                            f"WebSocket stalled for {max_seconds:.0f}s without an event."
                        )
                    event = json.loads(raw)
                    events.append(event)
                    try:
                        on_event(event)
                    except Exception:
                        # Don't let UI render errors kill the stream.
                        pass
                    if event.get("type") in ("result", "error"):
                        return events
        except websockets.exceptions.ConnectionClosed:
            return events

    return asyncio.run(_stream())
