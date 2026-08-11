from __future__ import annotations

import json
import re
from typing import Any

import httpx

from ..config import AppConfig
from ..db import Database


class BudgetExceededError(RuntimeError):
    pass


class ModelClient:
    def __init__(self, config: AppConfig, db: Database):
        self.config = config
        self.db = db

    @property
    def enabled(self) -> bool:
        return bool(self.config.api_key)

    def ensure_budget(self) -> None:
        if self.db.monthly_spend() >= self.config.monthly_budget_cny:
            raise BudgetExceededError(f"本月模型预算已达到 ¥{self.config.monthly_budget_cny:.2f}")

    async def json_completion(self, model: str, system: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_budget()
        if not self.enabled:
            raise RuntimeError("未配置 OPENAI_API_KEY")
        body = {
            "model": model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        }
        headers = {"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.config.request_timeout_seconds) as client:
            response = await client.post(f"{self.config.api_base_url}/chat/completions", headers=headers, json=body)
            response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise ValueError("模型没有返回 JSON 对象")
        result = json.loads(match.group(0))
        usage = data.get("usage", {})
        input_tokens = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
        output_tokens = int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0)
        cost = (input_tokens * self.config.input_price_cny_per_million + output_tokens * self.config.output_price_cny_per_million) / 1_000_000
        self.db.add_usage(model, input_tokens, output_tokens, cost)
        return result

