from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

from app.config import load_config
from app.db import Database
from app.services.parser import parse_chat
from app.services.pipeline import DigestPipeline


def test_local_pipeline_generates_digest_and_removes_raw_text(tmp_path: Path):
    db = Database(tmp_path / "pipeline.db")
    digest_date = "2026-08-11"
    messages = parse_chat(
        "github API tool release with a detailed performance debugging guide",
        digest_date,
    )
    assert db.ingest(digest_date, messages) == (1, 0)
    job_id = db.create_job(digest_date, 1, 0)
    config = replace(
        load_config(),
        database_path=tmp_path / "pipeline.db",
        api_key="",
        allow_local_fallback=True,
    )

    asyncio.run(DigestPipeline(db, config).run(job_id, digest_date))

    assert db.job(job_id)["status"] == "completed"
    digest = db.digest(digest_date)
    assert digest is not None
    assert 1 <= len(digest["items"]) <= 10
    assert db.raw_messages(digest_date) == []
    assert db.ingest(digest_date, messages) == (0, 1)
