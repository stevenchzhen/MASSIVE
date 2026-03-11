import json

from cell.agents.base import AgentInput
from cell.agents.executor import ExecutorAgent
from cell.schema_registry import ResultSchemaRegistry
from cell.types import Blocker


async def test_executor_returns_complete(mock_model_factory) -> None:
    agent = ExecutorAgent(
        mock_model_factory(
            [
                json.dumps(
                    {
                        "status": "complete",
                        "confidence": 0.91,
                        "completion_status": "complete",
                        "result": {"summary": "done", "key_findings": ["x"]},
                        "sources": [
                            {
                                "source_id": "doc-1",
                                "content_hash": "abc123",
                                "usage_description": "Provided the finding.",
                            }
                        ],
                        "assumptions": ["input is accurate"],
                    }
                )
            ]
        )
    )
    result = await agent.invoke(
        AgentInput(
            payload={
                "instruction": "Summarize the dataset",
                "input_data": {"rows": 10},
                "result_schema": ResultSchemaRegistry.analysis(),
                "context": {},
            },
            tools=["calculator_basic"],
            context_window="Analysis task",
            config={"confidence_threshold": 0.7},
        )
    )
    assert result.status == "complete"
    assert result.payload["confidence"] == 0.91
    assert result.payload["result"]["summary"] == "done"
    assert result.payload["sources"][0]["source_id"] == "doc-1"


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
        AgentInput(
            payload={"instruction": "Parse text", "result_schema": {"type": "object"}},
            tools=[],
            context_window="ctx",
            config={},
        )
    )
    assert result.status == "blocker"
    blocker = Blocker.model_validate(result.payload["blocker"])
    assert blocker.category.value == "missing_capability"
