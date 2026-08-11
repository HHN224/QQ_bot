from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class AppConfig:
    database_path: Path
    api_key: str
    api_base_url: str
    screening_model: str
    final_model: str
    monthly_budget_cny: float
    retention_days: int
    input_price_cny_per_million: float
    output_price_cny_per_million: float
    allow_local_fallback: bool
    request_timeout_seconds: float
    max_input_chars: int


def load_config(overrides: dict[str, str] | None = None) -> AppConfig:
    overrides = overrides or {}

    def value(key: str, default: str) -> str:
        return overrides.get(key, os.getenv(key, default)).strip()

    db_value = value("DATABASE_PATH", str(PROJECT_ROOT / "data" / "qq_digest.db"))
    return AppConfig(
        database_path=Path(db_value),
        api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        api_base_url=value("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        screening_model=value("SCREENING_MODEL", "gpt-4.1-mini"),
        final_model=value("FINAL_MODEL", "gpt-4.1"),
        monthly_budget_cny=float(value("MONTHLY_BUDGET_CNY", str(_float("MONTHLY_BUDGET_CNY", 30.0)))),
        retention_days=int(value("RETENTION_DAYS", str(_int("RETENTION_DAYS", 30)))),
        input_price_cny_per_million=float(value("INPUT_PRICE_CNY_PER_MILLION", str(_float("INPUT_PRICE_CNY_PER_MILLION", 0.0)))),
        output_price_cny_per_million=float(value("OUTPUT_PRICE_CNY_PER_MILLION", str(_float("OUTPUT_PRICE_CNY_PER_MILLION", 0.0)))),
        allow_local_fallback=value("ALLOW_LOCAL_FALLBACK", "true").lower() in {"1", "true", "yes", "on"},
        request_timeout_seconds=_float("MODEL_TIMEOUT_SECONDS", 60.0),
        max_input_chars=_int("MAX_INPUT_CHARS", 120_000),
    )

