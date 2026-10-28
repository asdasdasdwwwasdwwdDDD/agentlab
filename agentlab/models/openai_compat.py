"""OpenAI 兼容 Chat Completions 客户端（httpx 直连，不绑定 SDK）。

支持任何兼容端点（OpenAI / DeepSeek / vLLM / Ollama 的 /v1 代理）：
  OPENAI_BASE_URL=https://api.deepseek.com/v1 OPENAI_API_KEY=... python -m agentlab run --model deepseek-chat
"""

from __future__ import annotations

import json
import os
import time

import httpx

from agentlab.models.base import ModelResponse

# USD / 1M tokens，粗略公开价，仅用于成本量级比较；可用环境变量覆盖。
PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.4, 1.6),
    "o3": (2.0, 8.0),
    "o4-mini": (1.1, 4.4),
    "deepseek-chat": (0.27, 1.1),
    "deepseek-reasoner": (0.55, 2.19),
}


class OpenAICompatModel:
    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_s: float = 180.0,
        max_retries: int = 2,
    ):
        self.model = model
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or ""
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.name = f"openai:{model}"
        if not self.api_key:
            raise RuntimeError(
                "缺少 OPENAI_API_KEY。请设置该环境变量（可配合 OPENAI_BASE_URL 指向任意兼容端点），"
                "或使用 --model mock 做离线自检。"
            )

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> ModelResponse:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_s) as client:
                    response = client.post(
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                        json=payload,
                    )
                if response.status_code >= 400:
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
                data = response.json()
                return self._parse(data)
            except Exception as exc:  # 网络/限流重试
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"模型调用失败（{self.name}）: {last_error}")

    def _parse(self, data: dict) -> ModelResponse:
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        text = message.get("content") or ""
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        price_in = float(os.environ.get("AGENTLAB_PRICE_IN", PRICES.get(self.model, (0.0, 0.0))[0]))
        price_out = float(os.environ.get("AGENTLAB_PRICE_OUT", PRICES.get(self.model, (0.0, 0.0))[1]))
        cost = prompt_tokens / 1e6 * price_in + completion_tokens / 1e6 * price_out
        return ModelResponse(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            model=self.model,
            raw={"id": data.get("id"), "finish_reason": choice.get("finish_reason")},
        )


def probe() -> dict:
    """doctor 用：只检查配置，不发请求。"""
    base_url = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    return {
        "base_url": base_url,
        "api_key_set": bool(os.environ.get("OPENAI_API_KEY")),
        "known_models": sorted(PRICES),
    }
