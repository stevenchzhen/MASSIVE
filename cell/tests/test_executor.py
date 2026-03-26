import json

from cell.agents.base import AgentInput
from cell.agents.executor import ExecutorAgent
from cell.models.base import CompletionResult, ModelAdapter
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


async def test_executor_normalizes_alias_style_blocker(mock_model_factory) -> None:
    agent = ExecutorAgent(
        mock_model_factory(
            [
                json.dumps(
                    {
                        "status": "blocker",
                        "confidence": 0.2,
                        "blocker": {
                            "category": "missing_parser_tool",
                            "reason": "Cannot deterministically parse proprietary segments with current tools",
                            "required_capability": "A parser tool that handles repeated ROW<<...>> entries",
                            "minimum_parser_spec": {"name": "invoice_parser"},
                            "blocking_elements": ["ROW<<name=Rotor Kit;qty=2;unit_usd=12.50>>"],
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
    assert blocker.description == "Cannot deterministically parse proprietary segments with current tools"
    assert blocker.what_would_unblock == "A parser tool that handles repeated ROW<<...>> entries"
    assert blocker.attempted_approaches


async def test_executor_returns_error_for_invalid_blocker_payload(mock_model_factory) -> None:
    agent = ExecutorAgent(
        mock_model_factory(
            [
                json.dumps(
                    {
                        "status": "blocker",
                        "confidence": 0.1,
                        "blocker": {
                            "category": "not-a-real-category",
                            "description": "bad blocker",
                            "attempted_approaches": [],
                            "what_would_unblock": "something",
                            "confidence_in_diagnosis": 1.2,
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
    assert result.status == "error"
    assert "invalid blocker payload" in result.payload["error"]


class _StubToolRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, tool_name: str, arguments: dict) -> dict:
        self.calls.append((tool_name, arguments))
        return {"tool_name": tool_name, "arguments": arguments, "output": {"result": 33.25}}


async def test_executor_can_request_and_use_tool(mock_model_factory) -> None:
    agent = ExecutorAgent(
        mock_model_factory(
            [
                json.dumps(
                    {
                        "status": "tool_call",
                        "confidence": 0.9,
                        "tool_call": {
                            "tool_name": "proprietary_invoice_parser",
                            "arguments": {"invoice_text": "ROW<<name=Rotor Kit;qty=2;unit_usd=12.50>>"},
                        },
                    }
                ),
                json.dumps(
                    {
                        "status": "complete",
                        "confidence": 0.93,
                        "completion_status": "complete",
                        "result": {"summary": "done", "key_findings": ["parsed"]},
                        "sources": [],
                        "assumptions": [],
                    }
                ),
            ]
        ),
        tool_runtime=_StubToolRuntime(),
    )
    result = await agent.invoke(
        AgentInput(
            payload={
                "instruction": "Parse the invoice",
                "input_data": {},
                "result_schema": ResultSchemaRegistry.analysis(),
                "context": {},
            },
            tools=["proprietary_invoice_parser"],
            context_window="ctx",
            config={
                "tool_descriptions": [
                    {
                        "tool_id": "proprietary_invoice_parser",
                        "description": "Parses proprietary invoice segments.",
                        "input_schema": {"type": "object"},
                        "output_schema": {"type": "object"},
                    }
                ]
            },
        )
    )
    assert result.status == "complete"
    assert result.payload["tools_invoked"] == ["proprietary_invoice_parser"]
    assert result.payload["result"]["summary"] == "done"


class _CapturingModel(ModelAdapter):
    def __init__(self, content: str):
        self.content = content
        self.last_system: str | None = None

    async def complete(self, **kwargs) -> CompletionResult:
        self.last_system = kwargs.get("system")
        return CompletionResult(
            content=self.content,
            tokens_in=1,
            tokens_out=1,
            model="mock",
            latency_ms=1,
            cost_usd=0.0,
        )


async def test_executor_prompt_describes_wrapper_schema() -> None:
    model = _CapturingModel(
        json.dumps(
            {
                "status": "complete",
                "confidence": 0.9,
                "completion_status": "complete",
                "result": {"summary": "done", "key_findings": ["x"]},
                "sources": [],
                "assumptions": [],
            }
        )
    )
    agent = ExecutorAgent(model)
    await agent.invoke(
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
    assert model.last_system is not None
    assert '"status"' in model.last_system
    assert '"result"' in model.last_system
    assert '"summary"' in model.last_system
