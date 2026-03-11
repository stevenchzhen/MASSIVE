from __future__ import annotations

from collections.abc import Iterator

import pytest

from cell.models.base import CompletionResult, ModelAdapter


class MockModelAdapter(ModelAdapter):
    def __init__(self, responses: list[str]):
        self._responses = iter(responses)

    async def complete(self, **kwargs) -> CompletionResult:
        content = next(self._responses)
        return CompletionResult(
            content=content,
            tokens_in=100,
            tokens_out=50,
            model="mock",
            latency_ms=10,
            cost_usd=0.001,
        )


@pytest.fixture
def mock_model_factory() -> Iterator[type[MockModelAdapter]]:
    yield MockModelAdapter

