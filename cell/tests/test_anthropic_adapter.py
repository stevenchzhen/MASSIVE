from __future__ import annotations

import httpx

from cell.models.anthropic import AnthropicAdapter


class _FakeAsyncClient:
    def __init__(self, response: httpx.Response, capture: dict[str, object]):
        self._response = response
        self._capture = capture

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, headers: dict[str, str], json: dict[str, object]) -> httpx.Response:
        self._capture["url"] = url
        self._capture["headers"] = headers
        self._capture["json"] = json
        return self._response


async def test_anthropic_adapter_ignores_response_format(monkeypatch) -> None:
    capture: dict[str, object] = {}
    response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
        json={
            "model": "claude-sonnet-4-20250514",
            "content": [{"type": "text", "text": "{\"ok\": true}"}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
    )
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda timeout: _FakeAsyncClient(response, capture),
    )

    adapter = AnthropicAdapter(model="claude-sonnet-4-20250514", api_key="test-key")
    result = await adapter.complete(
        messages=[{"role": "user", "content": "hello"}],
        response_format={"type": "json_schema", "json_schema": {"name": "x", "schema": {"type": "object"}}},
    )

    assert result.content == "{\"ok\": true}"
    assert "response_format" not in capture["json"]


async def test_anthropic_adapter_surfaces_error_body(monkeypatch) -> None:
    capture: dict[str, object] = {}
    response = httpx.Response(
        400,
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
        json={"error": {"type": "invalid_request_error", "message": "bad field: response_format"}},
    )
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda timeout: _FakeAsyncClient(response, capture),
    )

    adapter = AnthropicAdapter(model="claude-sonnet-4-20250514", api_key="test-key")

    try:
        await adapter.complete(messages=[{"role": "user", "content": "hello"}], response_format={"type": "json_object"})
    except RuntimeError as exc:
        assert "invalid_request_error" in str(exc)
        assert "response_format" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for a 400 response")
