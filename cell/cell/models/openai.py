from __future__ import annotations

import os
import time
from typing import Any

import httpx

from cell.models.base import CompletionResult, ModelAdapter


OPENAI_PRICING_PER_MILLION: dict[str, tuple[float, float]] = {
    "gpt-4o": (5.0, 15.0),
    "gpt-4o-mini": (0.15, 0.6),
}


class OpenAIAdapter(ModelAdapter):
    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1/chat/completions",
        timeout: float = 60.0,
    ):
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
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
            raise RuntimeError("OPENAI_API_KEY is not set")

        payload_messages = list(messages)
        if system:
            payload_messages.insert(0, {"role": "system", "content": system})
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": payload_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
        if response_format:
            payload["response_format"] = response_format

        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.base_url,
                headers={
                    "authorization": f"Bearer {self.api_key}",
                    "content-type": "application/json",
                },
                json=payload,
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        response.raise_for_status()
        data = response.json()
        choice = data["choices"][0]["message"]
        usage = data.get("usage", {})
        tokens_in = int(usage.get("prompt_tokens", 0))
        tokens_out = int(usage.get("completion_tokens", 0))
        in_price, out_price = OPENAI_PRICING_PER_MILLION.get(self.model, (5.0, 15.0))
        cost = (tokens_in / 1_000_000 * in_price) + (tokens_out / 1_000_000 * out_price)
        return CompletionResult(
            content=choice.get("content", ""),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=data.get("model", self.model),
            latency_ms=latency_ms,
            cost_usd=round(cost, 8),
        )

