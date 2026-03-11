from cell.tools.registry import ToolRegistry


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
