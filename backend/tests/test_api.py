from pathlib import Path

from app.db import Database
from app.services.parser import parse_chat


def test_same_day_ingestion_is_idempotent(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    messages = parse_chat("张三 09:31\n开源工具发布了", "2026-08-11")
    assert db.ingest("2026-08-11", messages) == (1, 0)
    assert db.ingest("2026-08-11", messages) == (0, 1)


def test_save_digest_deletes_raw_but_keeps_fingerprint(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    messages = parse_chat("张三 09:31\n开源工具发布了", "2026-08-11")
    db.ingest("2026-08-11", messages)
    db.save_digest("2026-08-11", [], {"total": 0})
    assert db.raw_messages("2026-08-11") == []
    assert db.ingest("2026-08-11", messages) == (0, 1)
