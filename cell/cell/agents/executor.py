from __future__ import annotations

from uuid import uuid4

from cell.agents.base import Agent, AgentInput, AgentOutput
from cell.models.base import parse_json_content
from cell.types import Blocker


EXECUTOR_SYSTEM_TEMPLATE = """
You are an executor agent within a CellForge cell.

Your task: {instruction}

Your available tools:
{tools_description}

Your output must conform to this JSON schema:
{result_schema}

CRITICAL RULES:
- If your confidence in any step drops below {confidence_threshold}, emit a blocker signal instead of proceeding.
- If you attempt the same approach twice without progress, emit a blocker signal.
- Do not guess. Do not fabricate results.
- If you cannot complete the task, say so explicitly.

Scoped context:
{context}

{additional_instructions}
""".strip()


class ExecutorAgent(Agent):
    async def invoke(self, input: AgentInput) -> AgentOutput:
        tool_lines = "\n".join(f"- {tool}" for tool in input.tools) or "- none"
        context = input.context_window.strip() or "No additional context provided."
        confidence_threshold = input.config.get("confidence_threshold", 0.7)
        system_prompt = EXECUTOR_SYSTEM_TEMPLATE.format(
            instruction=input.payload.get("instruction") or str(input.payload),
            tools_description=tool_lines,
            result_schema=input.payload.get("result_schema", {"type": "object"}),
            confidence_threshold=confidence_threshold,
            context=context,
            additional_instructions=input.config.get("additional_instructions", "").strip()
            or "No additional instructions.",
        )
        result_schema = input.payload.get("result_schema", {"type": "object"})
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "executor_response",
                "schema": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["complete", "blocker"]},
                        "confidence": {"type": "number"},
                        "completion_status": {
                            "type": "string",
                            "enum": ["complete", "partial", "inconclusive"],
                        },
                        "result": result_schema,
                        "sources": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "source_id": {"type": "string"},
                                    "content_hash": {"type": "string"},
                                    "usage_description": {"type": "string"},
                                },
                                "required": ["source_id", "content_hash", "usage_description"],
                            },
                        },
                        "assumptions": {"type": "array", "items": {"type": "string"}},
                        "blocker": {"type": "object"},
                    },
                    "required": ["status", "confidence"],
                },
            },
        }
        prompt_payload = {
            "instruction": input.payload.get("instruction"),
            "input_data": input.payload.get("input_data", {}),
            "input_documents": input.payload.get("input_documents", []),
            "context": input.payload.get("context", {}),
        }
        result = await self.model.complete(
            messages=[{"role": "user", "content": str(prompt_payload)}],
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
