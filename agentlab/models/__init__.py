"""模型工厂：`mock` 或任意 OpenAI 兼容模型名。"""

from __future__ import annotations

from agentlab.core.types import Action
from agentlab.models.base import ModelClient, ModelResponse
from agentlab.models.mock import create_mock_model
from agentlab.models.openai_compat import OpenAICompatModel, probe

__all__ = ["ModelClient", "ModelResponse", "create_model", "probe"]


def create_model(spec: str, plan: list[Action] | None = None, noise: float = 0.0, seed: int = 0) -> ModelClient:
    spec = (spec or "mock").strip()
    if spec == "mock" or spec.startswith("mock:"):
        if spec.startswith("mock:"):
            noise = float(spec.split(":", 1)[1] or 0.0)
        return create_mock_model(plan or [], noise=noise, seed=seed)
    model = spec.split(":", 1)[1] if spec.startswith("openai:") else spec
    return OpenAICompatModel(model=model)
