from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class GenerateRequest(BaseModel):
    digest_date: date
    text: str = Field(min_length=1, max_length=500_000)

    @field_validator("text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("聊天记录不能为空")
        return value


class SettingsUpdate(BaseModel):
    api_base_url: str = Field(min_length=8, max_length=500)
    screening_model: str = Field(min_length=1, max_length=200)
    final_model: str = Field(min_length=1, max_length=200)
    monthly_budget_cny: float = Field(ge=0, le=100000)
    retention_days: int = Field(ge=1, le=3650)
    input_price_cny_per_million: float = Field(ge=0)
    output_price_cny_per_million: float = Field(ge=0)


class FeedbackRequest(BaseModel):
    digest_item_id: int | None = None
    value: Literal["useful", "not_useful"]

