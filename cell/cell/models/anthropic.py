from __future__ import annotations

import os
import time
from typing import Any

import httpx

from cell.models.base import CompletionResult, ModelAdapter


class AnthropicAdapter(ModelAdapter):
    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str = "https://api.anthropic.com/v1/messages",
        timeout: float = 60.0,
    ):
        self.model = model
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.base_url = base_url
        self.timeout = timeout

    async def complete(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
    ) -> CompletionResult:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = tools
        # Anthropic's native Messages API does not accept OpenAI-style response_format.
        # Callers still pass prompt-level JSON instructions, so we ignore this here.
        _ = response_format

        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.base_url,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.is_error:
            detail = _error_detail(response)
            raise RuntimeError(
                f"Anthropic API error {response.status_code} for model {self.model}: {detail}"
            )
        data = response.json()
        blocks = data.get("content", [])
        text = "\n".join(block.get("text", "") for block in blocks if block.get("type") == "text")
        usage = data.get("usage", {})
        tokens_in = int(usage.get("input_tokens", 0))
        tokens_out = int(usage.get("output_tokens", 0))
        cost = (tokens_in / 1_000_000 * 3.0) + (tokens_out / 1_000_000 * 15.0)
        return CompletionResult(
            content=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=data.get("model", self.model),
            latency_ms=latency_ms,
            cost_usd=round(cost, 8),
        )


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text or response.reason_phrase
    error = payload.get("error")
    if isinstance(error, dict):
        error_type = error.get("type")
        message = error.get("message")
        if error_type and message:
            return f"{error_type}: {message}"
        if message:
            return str(message)
    return str(payload)
