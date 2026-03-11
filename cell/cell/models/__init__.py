from __future__ import annotations

from cell.models.anthropic import AnthropicAdapter
from cell.models.base import CompletionResult, ModelAdapter
from cell.models.ollama import OllamaAdapter
from cell.models.openai import OpenAIAdapter


def create_adapter(model_config: str | dict) -> ModelAdapter:
    if isinstance(model_config, str):
        if model_config.startswith("claude"):
            return AnthropicAdapter(model=model_config)
        if model_config.startswith(("gpt", "o1", "o3")):
            return OpenAIAdapter(model=model_config)
        return OllamaAdapter(model=model_config)

    provider = model_config.get("provider")
    model = model_config.get("model")
    if provider == "anthropic":
        return AnthropicAdapter(model=model)
    if provider == "openai":
        return OpenAIAdapter(model=model)
    if provider == "ollama":
        return OllamaAdapter(model=model, base_url=model_config.get("base_url"))
    raise ValueError(f"Unsupported model configuration: {model_config!r}")


__all__ = [
    "AnthropicAdapter",
    "CompletionResult",
    "ModelAdapter",
    "OllamaAdapter",
    "OpenAIAdapter",
    "create_adapter",
]

