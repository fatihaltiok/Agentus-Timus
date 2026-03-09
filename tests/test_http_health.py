from __future__ import annotations

import http.client

import pytest

from utils.http_health import fetch_http_text


class _FakeResponse:
    def __init__(self, status: int = 200, body: bytes = b'{"status":"healthy"}') -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body


class _FakeConnection:
    def __init__(self, host: str, port: int | None = None, timeout: float = 0.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.request_args = None

    def request(self, method: str, path: str) -> None:
        self.request_args = (method, path)

    def getresponse(self) -> _FakeResponse:
        return _FakeResponse()

    def close(self) -> None:
        return None


def test_fetch_http_text_restricts_scheme() -> None:
    with pytest.raises(ValueError, match="Unsupported health-check scheme"):
        fetch_http_text("file:///tmp/health", timeout=1.0)


def test_fetch_http_text_uses_expected_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[_FakeConnection] = []

    def _factory(host: str, port: int | None = None, timeout: float = 0.0) -> _FakeConnection:
        conn = _FakeConnection(host, port, timeout)
        created.append(conn)
        return conn

    monkeypatch.setattr(http.client, "HTTPConnection", _factory)

    result = fetch_http_text("http://127.0.0.1:5000/health?full=1", timeout=2.5)

    assert result["status_code"] == 200
    assert '"healthy"' in result["body"]
    assert created[0].host == "127.0.0.1"
    assert created[0].port == 5000
    assert created[0].timeout == 2.5
    assert created[0].request_args == ("GET", "/health?full=1")
