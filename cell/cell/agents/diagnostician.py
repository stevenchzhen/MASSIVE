from __future__ import annotations

from cell.agents.base import Agent, AgentInput, AgentOutput
from cell.models.base import parse_json_content
from cell.types import DiagnosisAction, ToolSpec


class DiagnosticianAgent(Agent):
    async def invoke(self, input: AgentInput) -> AgentOutput:
        system_prompt = (
            "You are the Diagnostician agent.\n"
            "Analyze the blocker and choose one action: use_existing, install_public, adapt_existing, "
            "create_new, context_request, or escalate.\n"
            "Prefer the cheapest adequate path in this order: use_existing, install_public, adapt_existing, create_new.\n"
            "If action is adapt_existing or create_new, produce a complete ToolSpec with exact input/output "
            "schemas, at least 3 behavioral test cases, and at least 2 edge cases.\n"
            "If adapting a tool, include base_tool_id, base_tool_source, and base_test_cases when available.\n"
            "Good test cases use concrete inputs and exact expected outputs. Example: "
            '{"description":"Adds positive ints","input":{"a":2,"b":3},"expected_output":{"result":5}}.\n'
            "If action is use_existing, specify existing_tool_id.\n"
            "If action is install_public, specify public_tool_id.\n"
            "If action is context_request, specify the exact additional context required.\n"
            "If action is escalate, explain why the blocker cannot be resolved inside the cell.\n"
            "Respond with JSON only."
        )
        result = await self.model.complete(
            messages=[{"role": "user", "content": str(input.payload)}],
            system=system_prompt,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        try:
            payload = parse_json_content(result.content)
        except Exception as exc:
            return AgentOutput(
                status="error",
                payload={"error": f"Diagnostician returned invalid JSON: {exc}"},
                reasoning_trace=result.content,
                token_usage={"input": result.tokens_in, "output": result.tokens_out},
                model_id=result.model,
                latency_ms=result.latency_ms,
                cost_usd=result.cost_usd,
            )

        action = payload.get("action")
        if action in {DiagnosisAction.ADAPT_EXISTING.value, DiagnosisAction.CREATE_NEW.value}:
            payload["tool_spec"] = ToolSpec.model_validate(payload["tool_spec"]).model_dump(mode="json")
        elif action not in {
            DiagnosisAction.USE_EXISTING.value,
            DiagnosisAction.INSTALL_PUBLIC.value,
            DiagnosisAction.CONTEXT_REQUEST.value,
            DiagnosisAction.ESCALATE.value,
        }:
            return AgentOutput(
                status="error",
                payload={"error": f"Unsupported diagnostician action: {action!r}"},
                reasoning_trace=result.content,
                token_usage={"input": result.tokens_in, "output": result.tokens_out},
                model_id=result.model,
                latency_ms=result.latency_ms,
                cost_usd=result.cost_usd,
            )

        return AgentOutput(
            status="complete",
            payload=payload,
            reasoning_trace=result.content,
            token_usage={"input": result.tokens_in, "output": result.tokens_out},
            model_id=result.model,
            latency_ms=result.latency_ms,
            cost_usd=result.cost_usd,
        )
