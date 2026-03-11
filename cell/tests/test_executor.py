import json

from cell.agents.base import AgentInput
from cell.agents.executor import ExecutorAgent
from cell.types import Blocker


async def test_executor_returns_complete(mock_model_factory) -> None:
    agent = ExecutorAgent(
        mock_model_factory(
            [
                json.dumps(
                    {
                        "status": "complete",
                        "confidence": 0.91,
                        "findings": {"answer": 42},
                        "evidence": [{"summary": "calc"}],
                        "assumptions": ["input is accurate"],
                    }
                )
            ]
        )
    )
    result = await agent.invoke(
        AgentInput(
            payload={"scope": "Calculate 6*7"},
            tools=["calculator_basic"],
            context_window="Math task",
            config={},
        )
    )
    assert result.status == "complete"
    assert result.payload["confidence"] == 0.91
    assert result.payload["findings"] == {"answer": 42}
    assert result.payload["evidence"] == [{"summary": "calc"}]


async def test_executor_returns_blocker(mock_model_factory) -> None:
    agent = ExecutorAgent(
        mock_model_factory(
            [
                json.dumps(
                    {
                        "status": "blocker",
                        "confidence": 0.4,
                        "blocker": {
                            "category": "missing_capability",
                            "description": "Need a tool",
                            "attempted_approaches": ["manual analysis"],
                            "what_would_unblock": "Build a parser",
                            "input_sample": "abc",
                            "confidence_in_diagnosis": 0.85,
                        },
                    }
                )
            ]
        )
    )
    result = await agent.invoke(
        AgentInput(payload={"scope": "Parse text"}, tools=[], context_window="ctx", config={})
    )
    assert result.status == "blocker"
    blocker = Blocker.model_validate(result.payload["blocker"])
    assert blocker.category.value == "missing_capability"

