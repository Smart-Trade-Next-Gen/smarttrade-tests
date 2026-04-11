import asyncio

import pytest

from e2e.clients.bas_ws_client import BASWebSocketClient
from e2e.clients.mds_client import MDSWebSocketClient


@pytest.mark.asyncio
async def test_bas_websocket_connect_includes_account_id(monkeypatch):
    captured = {}

    class DummyConnection:
        def __init__(self):
            self._messages = ['{"type":"connection_ack"}']

        async def recv(self):
            if self._messages:
                return self._messages.pop(0)
            await asyncio.Future()

        async def send(self, _message):
            return None

        def close(self):
            return None

        async def wait_closed(self):
            return None

    async def fake_connect(url):
        captured["url"] = url
        return DummyConnection()

    monkeypatch.setattr("websockets.asyncio.client.connect", fake_connect)

    client = BASWebSocketClient(
        ws_url="ws://localhost:8005/api/v1/ws",
        account_id="ACC-123",
        token="jwt-token",
        timeout=0.1,
        heartbeat_interval=60.0,
    )

    await client.connect()
    await client.disconnect()

    assert captured["url"] == "ws://localhost:8005/api/v1/ws?token=jwt-token&account_id=ACC-123"


@pytest.mark.asyncio
async def test_mds_websocket_connect_includes_account_id(monkeypatch):
    captured = {}

    class DummyConnection:
        def __init__(self):
            self._messages = ['{"type":"system.connected"}']

        async def recv(self):
            if self._messages:
                return self._messages.pop(0)
            await asyncio.Future()

        async def send(self, _message):
            return None

        def close(self):
            return None

        async def wait_closed(self):
            return None

    async def fake_connect(url):
        captured["url"] = url
        return DummyConnection()

    monkeypatch.setattr("websockets.asyncio.client.connect", fake_connect)

    client = MDSWebSocketClient(
        ws_url="ws://localhost:8004/ws/fyers/ui",
        account_id="ACC-456",
        token="jwt-token",
        timeout=0.1,
        heartbeat_interval=60.0,
    )

    await client.connect()
    await client.disconnect()

    assert captured["url"] == "ws://localhost:8004/ws/fyers/ui?token=jwt-token&account_id=ACC-456"
