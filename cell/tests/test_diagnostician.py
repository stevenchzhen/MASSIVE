import json

from cell.agents.base import AgentInput
from cell.agents.diagnostician import DiagnosticianAgent


async def test_diagnostician_emits_tool_spec(mock_model_factory) -> None:
    agent = DiagnosticianAgent(
        mock_model_factory(
            [
                json.dumps(
                    {
                        "action": "create_new",
                        "tool_spec": {
                            "name": "adder",
                            "description": "Adds two numbers",
                            "input_schema": {
                                "type": "object",
                                "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                                "required": ["a", "b"],
                            },
                            "output_schema": {
                                "type": "object",
                                "properties": {"result": {"type": "number"}},
                                "required": ["result"],
                            },
                            "test_cases": [
                                {"description": "one", "input": {"a": 1, "b": 2}, "expected_output": {"result": 3}},
                                {"description": "two", "input": {"a": -1, "b": 2}, "expected_output": {"result": 1}},
                                {"description": "three", "input": {"a": 0, "b": 0}, "expected_output": {"result": 0}},
                            ],
                            "edge_cases": [
                                {"description": "large", "input": {"a": 1000000, "b": 1}, "expected_output": {"result": 1000001}},
                                {"description": "float", "input": {"a": 1.5, "b": 2.5}, "expected_output": {"result": 4.0}},
                            ],
                            "constraints": ["pure"],
                            "task_validation_cases": [
                                {
                                    "description": "task sample",
                                    "input": {"a": 10, "b": 5},
                                    "expected_output": {"result": 15},
                                }
                            ],
                        },
                    }
                )
            ]
        )
    )
    result = await agent.invoke(
        AgentInput(payload={"blocker": "missing capability"}, tools=[], context_window="", config={})
    )
    assert result.status == "complete"
    assert result.payload["action"] == "create_new"
    assert result.payload["tool_spec"]["name"] == "adder"
    assert result.payload["tool_spec"]["task_validation_cases"][0]["expected_output"]["result"] == 15


async def test_diagnostician_context_request(mock_model_factory) -> None:
    agent = DiagnosticianAgent(mock_model_factory([json.dumps({"action": "context_request", "context_needed": "Need schema"})]))
    result = await agent.invoke(AgentInput(payload={"blocker": "missing context"}, tools=[], context_window="", config={}))
    assert result.status == "complete"
    assert result.payload["context_needed"] == "Need schema"


async def test_diagnostician_use_existing(mock_model_factory) -> None:
    agent = DiagnosticianAgent(mock_model_factory([json.dumps({"action": "use_existing", "existing_tool_id": "csv_reader"})]))
    result = await agent.invoke(AgentInput(payload={"blocker": "need csv filtering"}, tools=[], context_window="", config={}))
    assert result.status == "complete"
    assert result.payload["action"] == "use_existing"
    assert result.payload["existing_tool_id"] == "csv_reader"
