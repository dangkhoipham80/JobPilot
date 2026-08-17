"""WebSocket hub for realtime dashboard updates.

A connection manager + ``/api/ws`` endpoint that authenticates, then relays
crawl/tailor/apply progress pushed by ``manager.broadcast(...)``.

**The token arrives in the first frame, not in the query string.** A query
string is part of the request line, so every proxy in front of this — uvicorn's
own access log included — writes it to disk in plaintext, and it shows up in
browser history and in any Referer. The frame body is logged by none of them.
The cost is one round trip before the socket is usable.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from jobpilot import __version__
from jobpilot.api.security import token_matches
from jobpilot.config import get_secrets

#: How long an accepted socket may stay silent before it has authenticated.
#: Bounds how many unauthenticated sockets can be parked on the server at once.
AUTH_TIMEOUT_SECONDS = 10.0


class ConnectionManager:
    def __init__(self) -> None:
        self.active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        """Accept and subscribe. Only for sockets that have already authenticated."""
        await ws.accept()
        self.active.add(ws)

    def subscribe(self, ws: WebSocket) -> None:
        """Start broadcasting to an already-accepted socket.

        Separate from ``connect`` because authentication needs the socket
        accepted (you cannot read a frame otherwise) but must finish *before* it
        joins the broadcast set — otherwise a caller with no token still
        receives every job update while it is being asked for one.
        """
        self.active.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)

    async def broadcast(self, message: dict) -> None:
        for ws in list(self.active):
            try:
                if ws.application_state == WebSocketState.CONNECTED:
                    await ws.send_json(message)
            except Exception:
                self.disconnect(ws)


manager = ConnectionManager()


async def _authenticate(ws: WebSocket) -> bool:
    """Read the opening frame and check the token it carries.

    Expects ``{"type": "auth", "token": "…"}``. Anything else — a malformed
    frame, a wrong token, or silence — closes the socket without ever
    subscribing it.
    """
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=AUTH_TIMEOUT_SECONDS)
    except (TimeoutError, WebSocketDisconnect):
        return False

    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return False

    if not isinstance(payload, dict) or payload.get("type") != "auth":
        return False
    return token_matches(payload.get("token"), get_secrets().jobpilot_api_token)


async def _reject(ws: WebSocket) -> None:
    """Close an unauthenticated socket without making noise about it.

    Authentication fails in two shapes, and one of them is a client that simply
    went away — a tab closed while the socket was still being set up, or the
    reconnect backoff giving up. Calling ``close()`` on a socket that has
    already sent ``websocket.disconnect`` makes uvicorn raise ``Unexpected ASGI
    message``, which surfaces as a full traceback in the service log for what is
    a completely ordinary event. Enough of those and the log stops being worth
    reading.
    """
    if ws.client_state is WebSocketState.DISCONNECTED:
        return
    try:
        await ws.close(code=1008)  # policy violation
    except RuntimeError:
        # Vanished between the check and the close. Nothing left to do.
        pass


async def websocket_endpoint(ws: WebSocket) -> None:
    # Accepted before authenticating — a frame cannot be read from a socket that
    # was never accepted — but deliberately not subscribed until it passes.
    await ws.accept()
    if not await _authenticate(ws):
        await _reject(ws)
        return

    manager.subscribe(ws)
    try:
        await ws.send_json({"type": "hello", "version": __version__})
        while True:
            data = await ws.receive_text()
            await ws.send_json({"type": "echo", "data": data})
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)
        raise
