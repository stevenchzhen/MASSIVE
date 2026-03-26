from __future__ import annotations

import json
from uuid import uuid4

from pydantic import ValidationError

from cell.agents.base import Agent, AgentInput, AgentOutput
from cell.models.base import parse_json_content
from cell.types import Blocker


EXECUTOR_SYSTEM_TEMPLATE = """
You are an executor agent within a CellForge cell.

Your task: {instruction}

Your available tools:
{tools_description}

You must return a single JSON object that matches this exact response schema:
{response_schema}

CRITICAL RULES:
- If your confidence in any step drops below {confidence_threshold}, emit a blocker signal instead of proceeding.
- If you attempt the same approach twice without progress, emit a blocker signal.
- Do not guess. Do not fabricate results.
- If you cannot complete the task, say so explicitly.
- If status is "blocker", the blocker object must use exactly these fields:
  category, description, attempted_approaches, what_would_unblock, input_sample, confidence_in_diagnosis.
- If status is "tool_call", provide tool_call.tool_name and tool_call.arguments only for tools listed below.
- Use a tool when exact parsing, transformation, or calculation is required; do not pretend you executed a tool when you did not.

Scoped context:
{context}

{additional_instructions}
""".strip()


class ToolRuntime:
    def __init__(self, *, registry, sandbox, available_tool_ids: list[str]):
        self.registry = registry
        self.sandbox = sandbox
        self.available_tool_ids = set(available_tool_ids)

    async def execute(self, tool_name: str, arguments: dict) -> dict:
        if tool_name not in self.available_tool_ids:
            raise KeyError(f"Tool {tool_name!r} is not available")
        output = await self.registry.execute(tool_name, arguments, self.sandbox)
        return {"tool_name": tool_name, "arguments": arguments, "output": output}


class ExecutorAgent(Agent):
    def __init__(self, model, tool_runtime: ToolRuntime | None = None):
        super().__init__(model)
        self.tool_runtime = tool_runtime

    async def invoke(self, input: AgentInput) -> AgentOutput:
        tool_descriptions = input.config.get("tool_descriptions", [])
        tool_lines = _render_tool_descriptions(tool_descriptions, input.tools)
        context = input.context_window.strip() or "No additional context provided."
        confidence_threshold = input.config.get("confidence_threshold", 0.7)
        max_tool_calls = int(input.config.get("max_tool_calls", 8))
        result_schema = input.payload.get("result_schema", {"type": "object"})
        response_schema = {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["complete", "blocker", "tool_call"]},
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
                "tool_call": {
                    "type": "object",
                    "properties": {
                        "tool_name": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["tool_name", "arguments"],
                },
            },
            "required": ["status", "confidence"],
        }
        system_prompt = EXECUTOR_SYSTEM_TEMPLATE.format(
            instruction=input.payload.get("instruction") or str(input.payload),
            tools_description=tool_lines,
            response_schema=json.dumps(response_schema, indent=2),
            confidence_threshold=confidence_threshold,
            context=context,
            additional_instructions=input.config.get("additional_instructions", "").strip()
            or "No additional instructions.",
        )
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "executor_response",
                "schema": response_schema,
            },
        }
        prompt_payload = {
            "instruction": input.payload.get("instruction"),
            "input_data": input.payload.get("input_data", {}),
            "input_documents": input.payload.get("input_documents", []),
            "context": input.payload.get("context", {}),
        }
        messages = [{"role": "user", "content": json.dumps(prompt_payload, indent=2)}]
        tools_invoked: list[str] = []
        token_usage = {"input": 0, "output": 0}
        total_latency_ms = 0
        total_cost_usd = 0.0
        model_id = input.config.get("model", "unknown")
        traces: list[str] = []

        for _ in range(max_tool_calls + 1):
            result = await self.model.complete(
                messages=messages,
                system=system_prompt,
                temperature=0.0,
                max_tokens=4096,
                response_format=response_format,
            )
            token_usage["input"] += result.tokens_in
            token_usage["output"] += result.tokens_out
            total_latency_ms += result.latency_ms
            total_cost_usd += result.cost_usd
            model_id = result.model
            traces.append(result.content)
            try:
                payload = parse_json_content(result.content)
            except Exception as exc:
                return AgentOutput(
                    status="error",
                    payload={"error": f"Executor returned invalid JSON: {exc}"},
                    reasoning_trace="\n\n".join(traces),
                    token_usage=token_usage,
                    model_id=model_id,
                    latency_ms=total_latency_ms,
                    cost_usd=total_cost_usd,
                )

            status = payload.get("status")
            if status == "tool_call":
                if self.tool_runtime is None:
                    return AgentOutput(
                        status="error",
                        payload={"error": "Executor requested a tool call, but no tool runtime is configured."},
                        reasoning_trace="\n\n".join(traces),
                        token_usage=token_usage,
                        model_id=model_id,
                        latency_ms=total_latency_ms,
                        cost_usd=total_cost_usd,
                    )
                tool_call = payload.get("tool_call") or {}
                tool_name = tool_call.get("tool_name")
                arguments = tool_call.get("arguments")
                if not isinstance(tool_name, str) or not isinstance(arguments, dict):
                    return AgentOutput(
                        status="error",
                        payload={"error": f"Invalid tool_call payload: {tool_call!r}"},
                        reasoning_trace="\n\n".join(traces),
                        token_usage=token_usage,
                        model_id=model_id,
                        latency_ms=total_latency_ms,
                        cost_usd=total_cost_usd,
                    )
                try:
                    tool_result = await self.tool_runtime.execute(tool_name, arguments)
                except Exception as exc:
                    return AgentOutput(
                        status="error",
                        payload={"error": f"Tool execution failed for {tool_name}: {exc}"},
                        reasoning_trace="\n\n".join(traces),
                        token_usage=token_usage,
                        model_id=model_id,
                        latency_ms=total_latency_ms,
                        cost_usd=total_cost_usd,
                    )
                tools_invoked.append(tool_name)
                messages.append({"role": "assistant", "content": json.dumps(payload, indent=2)})
                messages.append(
                    {
                        "role": "user",
                        "content": json.dumps({"tool_result": tool_result}, indent=2),
                    }
                )
                continue

            if status == "blocker":
                blocker_payload = _normalize_blocker_payload(payload.get("blocker", {}))
                blocker_payload.setdefault("blocker_id", f"blk_{uuid4().hex[:12]}")
                try:
                    blocker = Blocker.model_validate(blocker_payload)
                except ValidationError as exc:
                    return AgentOutput(
                        status="error",
                        payload={
                            "error": (
                                "Executor returned an invalid blocker payload: "
                                f"{exc.errors(include_url=False)}; payload={blocker_payload}"
                            )
                        },
                        reasoning_trace="\n\n".join(traces),
                        token_usage=token_usage,
                        model_id=model_id,
                        latency_ms=total_latency_ms,
                        cost_usd=total_cost_usd,
                    )
                payload["blocker"] = blocker.model_dump(mode="json")
                payload["tools_invoked"] = tools_invoked
                return AgentOutput(
                    status=status,
                    payload=payload,
                    reasoning_trace="\n\n".join(traces),
                    token_usage=token_usage,
                    model_id=model_id,
                    latency_ms=total_latency_ms,
                    cost_usd=total_cost_usd,
                )

            if status == "complete":
                payload["tools_invoked"] = tools_invoked
                return AgentOutput(
                    status=status,
                    payload=payload,
                    reasoning_trace="\n\n".join(traces),
                    token_usage=token_usage,
                    model_id=model_id,
                    latency_ms=total_latency_ms,
                    cost_usd=total_cost_usd,
                )

            return AgentOutput(
                status="error",
                payload={
                    "error": (
                        f"Unsupported executor status: {status!r}; "
                        f"top_level_keys={sorted(payload.keys())}"
                    )
                },
                reasoning_trace="\n\n".join(traces),
                token_usage=token_usage,
                model_id=model_id,
                latency_ms=total_latency_ms,
                cost_usd=total_cost_usd,
            )

        return AgentOutput(
            status="error",
            payload={"error": f"Executor exceeded max_tool_calls={max_tool_calls} without completing."},
            reasoning_trace="\n\n".join(traces),
            token_usage=token_usage,
            model_id=model_id,
            latency_ms=total_latency_ms,
            cost_usd=total_cost_usd,
        )


def _normalize_blocker_payload(raw_payload: object) -> dict:
    payload = dict(raw_payload) if isinstance(raw_payload, dict) else {}
    if "description" not in payload and "reason" in payload:
        payload["description"] = payload["reason"]
    if "what_would_unblock" not in payload:
        payload["what_would_unblock"] = payload.get("required_capability") or "Additional capability or context is required."
    if "attempted_approaches" not in payload:
        attempted: list[str] = []
        if payload.get("blocking_elements"):
            attempted.append(f"Blocked on elements: {payload['blocking_elements']}")
        if payload.get("minimum_parser_spec"):
            attempted.append("Outlined a minimum parser specification.")
        if not attempted:
            attempted.append("Unable to complete with currently available tools.")
        payload["attempted_approaches"] = attempted
    if "confidence_in_diagnosis" not in payload:
        payload["confidence_in_diagnosis"] = 0.8
    payload["category"] = _normalize_blocker_category(payload.get("category"))
    if "input_sample" not in payload:
        blocking_elements = payload.get("blocking_elements")
        if isinstance(blocking_elements, list) and blocking_elements:
            payload["input_sample"] = str(blocking_elements[0])
        else:
            payload["input_sample"] = None
    allowed_keys = {
        "blocker_id",
        "category",
        "description",
        "attempted_approaches",
        "what_would_unblock",
        "input_sample",
        "confidence_in_diagnosis",
    }
    return {key: value for key, value in payload.items() if key in allowed_keys}


def _render_tool_descriptions(tool_descriptions: list[dict], fallback_tool_ids: list[str]) -> str:
    if tool_descriptions:
        lines = []
        for item in tool_descriptions:
            lines.append(
                "- {tool_id}: {description}\n  input_schema={input_schema}\n  output_schema={output_schema}".format(
                    tool_id=item.get("tool_id", "unknown"),
                    description=item.get("description", ""),
                    input_schema=json.dumps(item.get("input_schema", {}), sort_keys=True),
                    output_schema=json.dumps(item.get("output_schema", {}), sort_keys=True),
                )
            )
        return "\n".join(lines)
    return "\n".join(f"- {tool}" for tool in fallback_tool_ids) or "- none"


def _normalize_blocker_category(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return "missing_capability"
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {
        "missing_capability",
        "insufficient_context",
        "ambiguous_instruction",
        "impossibility",
    }:
        return normalized
    if normalized.startswith(("missing_", "unsupported_", "no_", "need_")):
        return "missing_capability"
    if "context" in normalized or "information" in normalized:
        return "insufficient_context"
    if "ambiguous" in normalized or "unclear" in normalized:
        return "ambiguous_instruction"
    if "impossible" in normalized or "cannot" in normalized:
        return "impossibility"
    return "missing_capability"
