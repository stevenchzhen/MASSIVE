from __future__ import annotations

import ast
import re

from cell.agents.base import Agent, AgentInput, AgentOutput
from cell.models.base import parse_json_content
from cell.types import ToolArtifact, ToolSpec


class BuilderAgent(Agent):
    async def invoke(self, input: AgentInput) -> AgentOutput:
        spec = ToolSpec.model_validate(input.payload["tool_spec"])
        previous_failure = input.payload.get("previous_failure")
        imports = input.config.get("allowed_imports", [])
        prompt = [
            "You are a Python function builder. You receive a specification and write a single Python function that implements it.",
            "Your function must be pure: no side effects, no network calls, no file I/O.",
            f"You may only import from this whitelist: {imports}",
            "Respond with ONLY the Python source code. No markdown, no explanation, no backticks.",
            f"ToolSpec:\n{spec.model_dump_json(indent=2)}",
        ]
        if previous_failure:
            prompt.extend(
                [
                    "Previous attempt source code:",
                    previous_failure.get("source_code", ""),
                    "Verifier failure report:",
                    previous_failure.get("failure_report", ""),
                ]
            )
        result = await self.model.complete(
            messages=[{"role": "user", "content": "\n".join(prompt)}],
            temperature=0.0,
            response_format=None,
        )
        source_code = _extract_source(result.content)
        try:
            module = ast.parse(source_code)
        except SyntaxError as exc:
            return AgentOutput(
                status="error",
                payload={"error": f"Builder produced invalid Python: {exc}"},
                reasoning_trace=result.content,
                token_usage={"input": result.tokens_in, "output": result.tokens_out},
                model_id=result.model,
                latency_ms=result.latency_ms,
                cost_usd=result.cost_usd,
            )

        entry_point = next(
            (node.name for node in module.body if isinstance(node, ast.FunctionDef)),
            spec.name,
        )
        artifact = ToolArtifact(
            spec_id=spec.spec_id,
            name=spec.name,
            entry_point=entry_point,
            source_code=source_code,
        )
        return AgentOutput(
            status="complete",
            payload={"artifact": artifact.model_dump(mode="json")},
            reasoning_trace=result.content,
            token_usage={"input": result.tokens_in, "output": result.tokens_out},
            model_id=result.model,
            latency_ms=result.latency_ms,
            cost_usd=result.cost_usd,
        )


def _extract_source(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        match = re.search(r"```(?:python)?\s*(.*?)```", stripped, flags=re.DOTALL)
        if match:
            return match.group(1).strip()
    try:
        payload = parse_json_content(stripped)
        if isinstance(payload, dict) and "source_code" in payload:
            return str(payload["source_code"]).strip()
    except Exception:
        pass
    return stripped

