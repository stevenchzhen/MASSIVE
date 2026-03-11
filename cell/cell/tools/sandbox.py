from __future__ import annotations

import builtins
import multiprocessing
import tracemalloc
import traceback
from dataclasses import dataclass
from typing import Any

try:
    import resource
except ImportError:  # pragma: no cover
    resource = None

try:
    from RestrictedPython import compile_restricted
    from RestrictedPython.Guards import safe_builtins
except ImportError:  # pragma: no cover
    compile_restricted = None
    safe_builtins = {}

from pydantic import BaseModel, ConfigDict, Field

from cell.types import TestCase, ToolArtifact, VerificationResult


class SandboxPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_execution_time_sec: int = Field(default=30, ge=1)
    max_memory_mb: int = Field(default=256, ge=16)
    allowed_imports: list[str] = Field(default_factory=list)


@dataclass
class Sandbox:
    policy: SandboxPolicy

    async def execute(self, artifact: ToolArtifact, input_data: dict[str, Any]) -> Any:
        return _run_in_subprocess(self.policy, artifact.source_code, artifact.entry_point, input_data)

    async def run_test(self, artifact: ToolArtifact, case: TestCase) -> VerificationResult:
        try:
            output = await self.execute(artifact, case.input)
        except Exception as exc:
            return VerificationResult(
                check_name=f"test:{case.case_id}",
                passed=False,
                details=f"Execution error: {exc}",
            )
        return VerificationResult(
            check_name=f"test:{case.case_id}",
            passed=output == case.expected_output,
            details="Test case passed" if output == case.expected_output else "Unexpected output",
            observed_output=output,
        )

    async def run_fuzz(
        self,
        artifact: ToolArtifact,
        fuzz_input: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> VerificationResult:
        from cell.agents.verifier import schema_matches

        try:
            output = await self.execute(artifact, fuzz_input)
        except Exception as exc:
            return VerificationResult(
                check_name="fuzz",
                passed=False,
                details=f"Fuzz input crashed tool: {exc}",
                observed_output=fuzz_input,
            )
        return VerificationResult(
            check_name="fuzz",
            passed=schema_matches(output, output_schema),
            details="Fuzz execution respected output schema"
            if schema_matches(output, output_schema)
            else "Fuzz execution returned schema-invalid output",
            observed_output=output,
        )


def _run_in_subprocess(
    policy: SandboxPolicy,
    source: str,
    entry_point: str,
    input_data: dict[str, Any],
) -> Any:
    ctx = multiprocessing.get_context("spawn")
    result_queue: multiprocessing.Queue = ctx.Queue()
    proc = ctx.Process(
        target=_sandbox_worker,
        args=(policy.model_dump(mode="json"), source, entry_point, input_data, result_queue),
    )
    proc.start()
    proc.join(timeout=policy.max_execution_time_sec)

    if proc.is_alive():
        proc.kill()
        proc.join(timeout=1)
        raise TimeoutError(f"Tool execution exceeded {policy.max_execution_time_sec}s")

    if result_queue.empty():
        raise RuntimeError("Tool produced no output")

    status, payload = result_queue.get()
    if status == "error":
        raise RuntimeError(payload)
    return payload


def _sandbox_worker(
    policy_data: dict[str, Any],
    source: str,
    entry_point: str,
    input_data: dict[str, Any],
    result_queue: multiprocessing.Queue,
) -> None:
    try:
        policy = SandboxPolicy.model_validate(policy_data)
        if resource is not None:
            memory_bytes = policy.max_memory_mb * 1024 * 1024
            try:
                current_soft, current_hard = resource.getrlimit(resource.RLIMIT_AS)
                if current_hard in (-1, getattr(resource, "RLIM_INFINITY", -1)):
                    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, current_hard))
                else:
                    resource.setrlimit(resource.RLIMIT_AS, (min(memory_bytes, current_hard), current_hard))
            except (ValueError, OSError):
                pass

        allowed_imports = set(policy.allowed_imports)

        def guarded_import(
            name: str,
            globals_: Any = None,
            locals_: Any = None,
            fromlist: Any = (),
            level: int = 0,
        ) -> Any:
            root = name.split(".")[0]
            if root not in allowed_imports:
                raise ImportError(f"Import '{name}' is not allowed")
            return builtins.__import__(name, globals_, locals_, fromlist, level)

        builtins_dict = dict(safe_builtins) if safe_builtins else {}
        builtins_dict.update(
            {
                "__import__": guarded_import,
                "abs": abs,
                "all": all,
                "any": any,
                "bool": bool,
                "dict": dict,
                "enumerate": enumerate,
                "Exception": Exception,
                "float": float,
                "int": int,
                "len": len,
                "list": list,
                "max": max,
                "min": min,
                "range": range,
                "round": round,
                "set": set,
                "sorted": sorted,
                "str": str,
                "sum": sum,
                "tuple": tuple,
                "ValueError": ValueError,
                "zip": zip,
            }
        )
        restricted_globals = {"__builtins__": builtins_dict, "__name__": "__main__"}
        for mod_name in policy.allowed_imports:
            restricted_globals[mod_name] = builtins.__import__(mod_name)

        tracemalloc.start()
        byte_code = compile(source, "<tool>", "exec")
        exec(byte_code, restricted_globals)
        func = restricted_globals[entry_point]
        result = func(**input_data)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if peak > policy.max_memory_mb * 1024 * 1024:
            raise MemoryError(
                f"Peak memory {peak} exceeded {policy.max_memory_mb * 1024 * 1024} bytes"
            )
        result_queue.put(("ok", result))
    except BaseException as exc:  # pragma: no cover - exercised in tests
        result_queue.put(("error", f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"))
