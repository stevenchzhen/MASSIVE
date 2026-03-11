import pytest

from cell.tools.sandbox import Sandbox, SandboxPolicy
from cell.types import ToolArtifact


def _artifact(source_code: str) -> ToolArtifact:
    return ToolArtifact(
        spec_id="spec-1",
        name="tool",
        entry_point="tool",
        source_code=source_code,
    )


async def test_tool_cannot_access_network() -> None:
    sandbox = Sandbox(SandboxPolicy(max_execution_time_sec=2, max_memory_mb=128, allowed_imports=["math"]))
    with pytest.raises(RuntimeError):
        await sandbox.execute(_artifact("import socket\ndef tool():\n    return socket.gethostname()\n"), {})


async def test_tool_cannot_access_filesystem() -> None:
    sandbox = Sandbox(SandboxPolicy(max_execution_time_sec=2, max_memory_mb=128, allowed_imports=["math"]))
    with pytest.raises(RuntimeError):
        await sandbox.execute(_artifact("def tool():\n    return open('x').read()\n"), {})


async def test_tool_is_killed_after_timeout() -> None:
    sandbox = Sandbox(SandboxPolicy(max_execution_time_sec=1, max_memory_mb=128, allowed_imports=[]))
    with pytest.raises(TimeoutError):
        await sandbox.execute(_artifact("def tool():\n    while True:\n        pass\n"), {})


async def test_tool_memory_is_bounded() -> None:
    sandbox = Sandbox(SandboxPolicy(max_execution_time_sec=2, max_memory_mb=64, allowed_imports=[]))
    with pytest.raises(RuntimeError):
        await sandbox.execute(_artifact("def tool():\n    x = 'a' * (200 * 1024 * 1024)\n    return {'x': len(x)}\n"), {})


async def test_tool_can_only_import_whitelisted_modules() -> None:
    sandbox = Sandbox(SandboxPolicy(max_execution_time_sec=2, max_memory_mb=128, allowed_imports=["math"]))
    with pytest.raises(RuntimeError):
        await sandbox.execute(_artifact("import json\ndef tool():\n    return json.loads('{\"a\":1}')\n"), {})

