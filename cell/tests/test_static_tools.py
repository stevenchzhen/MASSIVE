from cell.tools.registry import ToolRegistry
from cell.tools.sandbox import Sandbox, SandboxPolicy
from cell.types import TestCase, ToolArtifact, ToolSpec


def test_static_tool_registry_loads_all_tools() -> None:
    registry = ToolRegistry(
        ["calculator_basic", "json_parser", "csv_reader", "date_arithmetic", "statistical_tests"]
    )
    assert len(registry.list()) == 5


def test_calculator_basic() -> None:
    registry = ToolRegistry(["calculator_basic"])
    tool = registry.get("calculator_basic")
    assert tool.func(operation="add", operands=[1, 2, 3]) == {"result": 6.0}


def test_json_parser() -> None:
    registry = ToolRegistry(["json_parser"])
    tool = registry.get("json_parser")
    assert tool.func(operation="query", data={"a": {"b": 3}}, path="a.b") == {"result": 3}


def test_csv_reader() -> None:
    registry = ToolRegistry(["csv_reader"])
    tool = registry.get("csv_reader")
    result = tool.func(operation="stats", csv_data="x,y\n1,2\n3,4", column="x")
    assert result["result"]["mean"] == 2.0


def test_date_arithmetic() -> None:
    registry = ToolRegistry(["date_arithmetic"])
    tool = registry.get("date_arithmetic")
    assert tool.func(operation="days_between", start_date="2026-03-01", end_date="2026-03-10") == {"result": 9}


def test_statistical_tests() -> None:
    registry = ToolRegistry(["statistical_tests"])
    tool = registry.get("statistical_tests")
    result = tool.func(operation="z_score", value=7, population_mean=5, population_stddev=2)
    assert result == {"result": 1.0}


def test_public_tool_can_be_installed_into_local_registry() -> None:
    ToolRegistry.register_public_package(
        "public_adder",
        ToolArtifact(
            spec_id="spec-1",
            name="public_adder",
            entry_point="public_adder",
            source_code="def public_adder(a, b): return {'result': a + b}",
        ),
        ToolSpec(
            spec_id="spec-1",
            name="public_adder",
            description="Adds two numbers",
            input_schema={
                "type": "object",
                "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                "required": ["a", "b"],
            },
            output_schema={
                "type": "object",
                "properties": {"result": {"type": "number"}},
                "required": ["result"],
            },
            test_cases=[
                TestCase(description="one", input={"a": 1, "b": 2}, expected_output={"result": 3}),
                TestCase(description="two", input={"a": 2, "b": 3}, expected_output={"result": 5}),
                TestCase(description="three", input={"a": 0, "b": 0}, expected_output={"result": 0}),
            ],
            edge_cases=[
                TestCase(description="float", input={"a": 1.5, "b": 2.5}, expected_output={"result": 4.0}),
                TestCase(description="large", input={"a": 10000, "b": 1}, expected_output={"result": 10001}),
            ],
            constraints=["pure"],
        ),
    )
    registry = ToolRegistry(["calculator_basic"])
    package = registry.install_public_package("public_adder")
    assert package.artifact.name == "public_adder"
    assert registry.is_local_tool("public_adder") is True


async def test_registered_dynamic_tool_can_execute() -> None:
    registry = ToolRegistry(["calculator_basic"])
    tool_id = registry.register_dynamic(
        ToolArtifact(
            spec_id="spec-2",
            name="dynamic_adder",
            entry_point="dynamic_adder",
            source_code="def dynamic_adder(a, b):\n    return {'result': a + b}\n",
        ),
        ToolSpec(
            spec_id="spec-2",
            name="dynamic_adder",
            description="Adds two numbers dynamically",
            input_schema={
                "type": "object",
                "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                "required": ["a", "b"],
            },
            output_schema={
                "type": "object",
                "properties": {"result": {"type": "number"}},
                "required": ["result"],
            },
            test_cases=[
                TestCase(description="one", input={"a": 1, "b": 2}, expected_output={"result": 3}),
                TestCase(description="two", input={"a": 2, "b": 3}, expected_output={"result": 5}),
                TestCase(description="three", input={"a": 0, "b": 0}, expected_output={"result": 0}),
            ],
            edge_cases=[
                TestCase(description="float", input={"a": 1.5, "b": 2.5}, expected_output={"result": 4.0}),
                TestCase(description="large", input={"a": 10000, "b": 1}, expected_output={"result": 10001}),
            ],
            constraints=["pure"],
        ),
    )
    result = await registry.execute(
        tool_id,
        {"a": 4, "b": 5},
        Sandbox(SandboxPolicy(max_execution_time_sec=2, max_memory_mb=128, allowed_imports=[])),
    )
    assert result == {"result": 9}
