from __future__ import annotations


def test_webhook_server_defaults_to_loopback(monkeypatch):
    from gateway.webhook_gateway import WebhookServer

    monkeypatch.delenv("WEBHOOK_HOST", raising=False)
    server = WebhookServer()

    assert server._host == "127.0.0.1"


def test_webhook_server_allows_explicit_unspecified_host(monkeypatch):
    from gateway.webhook_gateway import WebhookServer

    monkeypatch.setenv("WEBHOOK_HOST", "0.0.0.0")
    server = WebhookServer()

    assert server._host == "0.0.0.0"
