from __future__ import annotations

from uuid import uuid4

from cell.agents.base import Agent, AgentInput, AgentOutput
from cell.models.base import parse_json_content
from cell.types import Blocker


class ExecutorAgent(Agent):
    async def invoke(self, input: AgentInput) -> AgentOutput:
        tool_lines = "\n".join(f"- {tool}" for tool in input.tools) or "- none"
        context = input.context_window.strip() or "No additional context provided."
        system_prompt = (
            "You are the Executor agent for a verification cell.\n"
            "Role: perform the assigned analytical task using only the available verified tools.\n"
            "Output: respond with JSON only and match the required schema.\n"
            "Blocker protocol: If your confidence in any step drops below 0.7, or if you attempt the same "
            "approach twice without progress, you MUST respond with status 'blocker' and a complete blocker "
            "object. Do not guess. Do not fabricate results.\n"
            "Available tools:\n"
            f"{tool_lines}\n"
            "Scoped context:\n"
            f"{context}"
        )
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "executor_response",
                "schema": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["complete", "blocker"]},
                        "confidence": {"type": "number"},
                        "findings": {"type": "object"},
                        "evidence": {"type": "array"},
                        "assumptions": {"type": "array", "items": {"type": "string"}},
                        "blocker": {"type": "object"},
                    },
                    "required": ["status", "confidence"],
                },
            },
        }
        result = await self.model.complete(
            messages=[{"role": "user", "content": input.payload.get("scope") or str(input.payload)}],
            system=system_prompt,
            temperature=0.0,
            max_tokens=4096,
            response_format=response_format,
        )
        try:
            payload = parse_json_content(result.content)
        except Exception as exc:
            return AgentOutput(
                status="error",
                payload={"error": f"Executor returned invalid JSON: {exc}"},
                reasoning_trace=result.content,
                token_usage={"input": result.tokens_in, "output": result.tokens_out},
                model_id=result.model,
                latency_ms=result.latency_ms,
                cost_usd=result.cost_usd,
            )

        status = payload.get("status")
        if status == "blocker":
            blocker_payload = dict(payload.get("blocker", {}))
            blocker_payload.setdefault("blocker_id", f"blk_{uuid4().hex[:12]}")
            blocker = Blocker.model_validate(blocker_payload)
            payload["blocker"] = blocker.model_dump(mode="json")
        elif status != "complete":
            return AgentOutput(
                status="error",
                payload={"error": f"Unsupported executor status: {status!r}"},
                reasoning_trace=result.content,
                token_usage={"input": result.tokens_in, "output": result.tokens_out},
                model_id=result.model,
                latency_ms=result.latency_ms,
                cost_usd=result.cost_usd,
            )

        return AgentOutput(
            status=status,
            payload=payload,
            reasoning_trace=result.content,
            token_usage={"input": result.tokens_in, "output": result.tokens_out},
            model_id=result.model,
            latency_ms=result.latency_ms,
            cost_usd=result.cost_usd,
        )

