from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS fingerprints (
                    id INTEGER PRIMARY KEY, digest_date TEXT NOT NULL, message_hash TEXT NOT NULL,
                    author TEXT NOT NULL, source_time TEXT NOT NULL, created_at TEXT NOT NULL,
                    UNIQUE(digest_date, message_hash)
                );
                CREATE TABLE IF NOT EXISTS raw_messages (
                    id INTEGER PRIMARY KEY, fingerprint_id INTEGER NOT NULL UNIQUE,
                    digest_date TEXT NOT NULL, author TEXT NOT NULL, source_time TEXT NOT NULL,
                    content TEXT NOT NULL, links_json TEXT NOT NULL, created_at TEXT NOT NULL,
                    FOREIGN KEY(fingerprint_id) REFERENCES fingerprints(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS digests (
                    id INTEGER PRIMARY KEY, digest_date TEXT NOT NULL UNIQUE,
                    generated_at TEXT NOT NULL, stats_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS digest_items (
                    id INTEGER PRIMARY KEY, digest_id INTEGER NOT NULL, section TEXT NOT NULL,
                    rank INTEGER NOT NULL, category TEXT NOT NULL, conclusion TEXT NOT NULL,
                    why_read TEXT NOT NULL, context_summary TEXT NOT NULL, source_excerpt TEXT NOT NULL,
                    source_time TEXT NOT NULL, source_author TEXT NOT NULL, links_json TEXT NOT NULL,
                    credibility TEXT NOT NULL,
                    FOREIGN KEY(digest_id) REFERENCES digests(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, digest_date TEXT NOT NULL, status TEXT NOT NULL,
                    stage TEXT NOT NULL, progress INTEGER NOT NULL, error TEXT,
                    new_count INTEGER NOT NULL DEFAULT 0, duplicate_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS usage_events (
                    id INTEGER PRIMARY KEY, model TEXT NOT NULL, input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL, cost_cny REAL NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY, digest_item_id INTEGER, value TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(digest_item_id) REFERENCES digest_items(id) ON DELETE SET NULL
                );
                """
            )

    def settings(self) -> dict[str, str]:
        with self.connect() as db:
            return {row["key"]: row["value"] for row in db.execute("SELECT key, value FROM settings")}

    def update_settings(self, values: dict[str, str]) -> None:
        with self.connect() as db:
            db.executemany(
                "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                values.items(),
            )

    def ingest(self, digest_date: str, messages: list[dict[str, Any]]) -> tuple[int, int]:
        new_count = duplicate_count = 0
        with self.connect() as db:
            for message in messages:
                cursor = db.execute(
                    "INSERT OR IGNORE INTO fingerprints(digest_date,message_hash,author,source_time,created_at) VALUES(?,?,?,?,?)",
                    (digest_date, message["hash"], message["author"], message["time"], utcnow()),
                )
                if cursor.rowcount == 0:
                    duplicate_count += 1
                    continue
                fingerprint_id = int(cursor.lastrowid)
                db.execute(
                    "INSERT INTO raw_messages(fingerprint_id,digest_date,author,source_time,content,links_json,created_at) VALUES(?,?,?,?,?,?,?)",
                    (fingerprint_id, digest_date, message["author"], message["time"], message["content"], json.dumps(message["links"], ensure_ascii=False), utcnow()),
                )
                new_count += 1
        return new_count, duplicate_count

    def raw_messages(self, digest_date: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM raw_messages WHERE digest_date=? ORDER BY id", (digest_date,)).fetchall()
        return [{**dict(row), "links": json.loads(row["links_json"])} for row in rows]

    def create_job(self, digest_date: str, new_count: int, duplicate_count: int) -> str:
        job_id = str(uuid.uuid4())
        now = utcnow()
        with self.connect() as db:
            db.execute(
                "INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)",
                (job_id, digest_date, "queued", "等待处理", 0, None, new_count, duplicate_count, now, now),
            )
        return job_id

    def update_job(self, job_id: str, *, status: str | None = None, stage: str | None = None, progress: int | None = None, error: str | None = None) -> None:
        fields: list[str] = ["updated_at=?"]
        values: list[Any] = [utcnow()]
        for name, value in (("status", status), ("stage", stage), ("progress", progress), ("error", error)):
            if value is not None:
                fields.append(f"{name}=?")
                values.append(value)
        values.append(job_id)
        with self.connect() as db:
            db.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id=?", values)

    def job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def digest(self, digest_date: str) -> dict[str, Any] | None:
        with self.connect() as db:
            digest = db.execute("SELECT * FROM digests WHERE digest_date=?", (digest_date,)).fetchone()
            if not digest:
                return None
            rows = db.execute("SELECT * FROM digest_items WHERE digest_id=? ORDER BY section DESC, rank", (digest["id"],)).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["links"] = json.loads(item.pop("links_json"))
            items.append(item)
        return {**dict(digest), "stats": json.loads(digest["stats_json"]), "items": items}

    def save_digest(self, digest_date: str, items: list[dict[str, Any]], stats: dict[str, Any]) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO digests(digest_date,generated_at,stats_json) VALUES(?,?,?) ON CONFLICT(digest_date) DO UPDATE SET generated_at=excluded.generated_at,stats_json=excluded.stats_json",
                (digest_date, utcnow(), json.dumps(stats, ensure_ascii=False)),
            )
            digest_id = db.execute("SELECT id FROM digests WHERE digest_date=?", (digest_date,)).fetchone()["id"]
            db.execute("DELETE FROM digest_items WHERE digest_id=?", (digest_id,))
            for item in items:
                db.execute(
                    """INSERT INTO digest_items(digest_id,section,rank,category,conclusion,why_read,context_summary,source_excerpt,source_time,source_author,links_json,credibility)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (digest_id, item["section"], item["rank"], item["category"], item["conclusion"], item["why_read"], item["context_summary"], item["source_excerpt"], item["source_time"], item["source_author"], json.dumps(item.get("links", []), ensure_ascii=False), item["credibility"]),
                )
            db.execute("DELETE FROM raw_messages WHERE digest_date=?", (digest_date,))

    def history(self, query: str = "") -> list[dict[str, Any]]:
        with self.connect() as db:
            if query:
                pattern = f"%{query}%"
                rows = db.execute(
                    """SELECT DISTINCT d.digest_date,d.generated_at,d.stats_json FROM digests d
                    LEFT JOIN digest_items i ON i.digest_id=d.id
                    WHERE i.conclusion LIKE ? OR i.context_summary LIKE ? OR i.category LIKE ?
                    ORDER BY d.digest_date DESC""", (pattern, pattern, pattern)).fetchall()
            else:
                rows = db.execute("SELECT digest_date,generated_at,stats_json FROM digests ORDER BY digest_date DESC").fetchall()
        return [{**dict(row), "stats": json.loads(row["stats_json"])} for row in rows]

    def monthly_spend(self) -> float:
        month = date.today().strftime("%Y-%m") + "%"
        with self.connect() as db:
            row = db.execute("SELECT COALESCE(SUM(cost_cny),0) AS total FROM usage_events WHERE created_at LIKE ?", (month,)).fetchone()
        return float(row["total"])

    def add_usage(self, model: str, input_tokens: int, output_tokens: int, cost_cny: float) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO usage_events(model,input_tokens,output_tokens,cost_cny,created_at) VALUES(?,?,?,?,?)", (model, input_tokens, output_tokens, cost_cny, utcnow()))

    def cleanup(self, retention_days: int) -> None:
        cutoff = (date.today() - timedelta(days=max(1, retention_days))).isoformat()
        with self.connect() as db:
            db.execute("DELETE FROM digests WHERE digest_date < ?", (cutoff,))

