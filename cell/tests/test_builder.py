from cell.agents.base import AgentInput
from cell.agents.builder import BuilderAgent


async def test_builder_wraps_source_into_artifact(mock_model_factory) -> None:
    source = "def adder(a, b):\n    return {'result': a + b}\n"
    agent = BuilderAgent(mock_model_factory([source]))
    result = await agent.invoke(
        AgentInput(
            payload={
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
                        {"description": "two", "input": {"a": 0, "b": 0}, "expected_output": {"result": 0}},
                        {"description": "three", "input": {"a": -1, "b": 2}, "expected_output": {"result": 1}},
                    ],
                    "edge_cases": [
                        {"description": "float", "input": {"a": 1.5, "b": 2.5}, "expected_output": {"result": 4.0}},
                        {"description": "large", "input": {"a": 10000, "b": 1}, "expected_output": {"result": 10001}},
                    ],
                    "constraints": ["pure"],
                }
            },
            tools=[],
            context_window="",
            config={"allowed_imports": ["math"]},
        )
    )
    assert result.status == "complete"
    assert result.payload["artifact"]["entry_point"] == "adder"
