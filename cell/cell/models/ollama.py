from __future__ import annotations

import time
from typing import Any

import httpx

from cell.models.base import CompletionResult, ModelAdapter


class OllamaAdapter(ModelAdapter):
    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        timeout: float = 60.0,
    ):
        self.model = model
        self.base_url = base_url or "http://localhost:11434/api/chat"
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
        payload_messages = list(messages)
        if system:
            payload_messages.insert(0, {"role": "system", "content": system})
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": payload_messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if tools:
            payload["tools"] = tools
        if response_format:
            payload["format"] = response_format

        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.base_url, json=payload)
        latency_ms = int((time.perf_counter() - started) * 1000)
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "")
        prompt_tokens = int(data.get("prompt_eval_count", 0))
        completion_tokens = int(data.get("eval_count", 0))
        return CompletionResult(
            content=content,
            tokens_in=prompt_tokens,
            tokens_out=completion_tokens,
            model=self.model,
            latency_ms=latency_ms,
            cost_usd=0.0,
        )

