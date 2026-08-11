from __future__ import annotations

import asyncio
import re
from collections import Counter
from typing import Any

from ..config import AppConfig
from ..db import Database
from ..prompts import FINAL_SYSTEM, SCREEN_SYSTEM
from .fetcher import fetch_public_page
from .llm import ModelClient

KEYWORDS = ("github", "开源", "工具", "教程", "漏洞", "安全", "政策", "更新", "发布", "踩坑", "解决", "报错", "公告", "活动", "限时", "研究", "性能", "api", "框架")


class DigestPipeline:
    def __init__(self, db: Database, config: AppConfig):
        self.db = db
        self.config = config
        self.model = ModelClient(config, db)

    def _local_candidates(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates = []
        for message in messages:
            content = message["content"].lower()
            keyword_hits = sum(1 for keyword in KEYWORDS if keyword in content)
            score = min(100, keyword_hits * 18 + (25 if message["links"] else 0) + min(len(content) // 20, 20))
            if score >= 25:
                candidates.append({"message_id": message["id"], "category": self._category(content), "importance": score, "relevance": score, "reason": "本地规则初筛"})
        return sorted(candidates, key=lambda item: item["importance"], reverse=True)[:16]

    @staticmethod
    def _category(content: str) -> str:
        if any(word in content for word in ("漏洞", "安全", "攻击", "cve")):
            return "安全"
        if any(word in content for word in ("公告", "活动", "限时")):
            return "公告"
        if any(word in content for word in ("讨论", "争议", "观点", "为什么")):
            return "讨论"
        if any(word in content for word in ("工具", "github", "开源", "教程")):
            return "工具"
        return "资讯"

    async def _screen(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.model.enabled:
            if not self.config.allow_local_fallback:
                raise RuntimeError("未配置 OPENAI_API_KEY，且本地回退已关闭")
            return self._local_candidates(messages)
        compact = [{"id": m["id"], "author": m["author"], "time": m["source_time"], "content": m["content"][:3000], "links": m["links"]} for m in messages]
        result = await self.model.json_completion(self.config.screening_model, SCREEN_SYSTEM, {"messages": compact})
        valid_ids = {m["id"] for m in messages}
        return [item for item in result.get("candidates", []) if item.get("message_id") in valid_ids][:16]

    async def _fetch_links(self, candidates: list[dict[str, Any]], by_id: dict[int, dict[str, Any]]) -> dict[str, dict[str, str]]:
        urls = list(dict.fromkeys(url for candidate in candidates for url in by_id[candidate["message_id"]]["links"]))[:12]

        async def fetch(url: str) -> tuple[str, dict[str, str]]:
            try:
                return url, await fetch_public_page(url)
            except Exception as exc:
                return url, {"url": url, "title": "链接无法核验", "text": str(exc)[:300], "status": "unverified"}

        return dict(await asyncio.gather(*(fetch(url) for url in urls))) if urls else {}

    def _local_final(self, candidates: list[dict[str, Any]], by_id: dict[int, dict[str, Any]], pages: dict[str, dict[str, str]], existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
        produced = []
        for candidate in candidates[:10]:
            message = by_id[candidate["message_id"]]
            verified = any(pages.get(url, {}).get("status") == "verified" for url in message["links"])
            excerpt = re.sub(r"\s+", " ", message["content"]).strip()
            produced.append({
                "section": "must_read" if candidate["importance"] >= 65 else "interesting",
                "category": candidate.get("category", "资讯"),
                "conclusion": excerpt[:90] + ("…" if len(excerpt) > 90 else ""),
                "why_read": candidate.get("reason", "命中默认筛选规则，值得快速查看。"),
                "context_summary": excerpt[:360], "source_excerpt": excerpt[:180],
                "source_time": message["source_time"], "source_author": message["author"],
                "links": message["links"], "credibility": "verified" if verified else "unverified",
            })
        # Existing items remain eligible during same-day incremental regeneration.
        keys = set()
        combined = produced + [{k: v for k, v in item.items() if k not in {"id", "digest_id", "rank"}} for item in existing]
        unique = []
        for item in combined:
            key = (item.get("source_author"), item.get("source_time"), item.get("source_excerpt"))
            if key not in keys:
                keys.add(key)
                unique.append(item)
        must = [i for i in unique if i.get("section") == "must_read"][:3]
        interesting = [i for i in unique if i.get("section") != "must_read"][:7]
        return self._rank(must, interesting)

    @staticmethod
    def _rank(must: list[dict[str, Any]], interesting: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items = []
        for section, source, limit in (("must_read", must, 3), ("interesting", interesting, 7)):
            for rank, item in enumerate(source[:limit], 1):
                credibility = item.get("credibility", "unverified")
                if credibility not in {"verified", "unverified", "disputed"}:
                    credibility = "unverified"
                items.append({
                    "section": section, "rank": rank, "category": str(item.get("category", "资讯"))[:20],
                    "conclusion": str(item.get("conclusion", ""))[:500], "why_read": str(item.get("why_read", ""))[:1000],
                    "context_summary": str(item.get("context_summary", ""))[:3000], "source_excerpt": str(item.get("source_excerpt", ""))[:1000],
                    "source_time": str(item.get("source_time", "时间未知"))[:100], "source_author": str(item.get("source_author", "未知发送者"))[:200],
                    "links": [str(url) for url in item.get("links", []) if str(url).startswith(("http://", "https://"))][:10], "credibility": credibility,
                })
        return [item for item in items if item["conclusion"] and item["source_excerpt"]]

    async def run(self, job_id: str, digest_date: str) -> None:
        try:
            self.db.update_job(job_id, status="running", stage="解析与去重完成", progress=15)
            messages = self.db.raw_messages(digest_date)
            existing_digest = self.db.digest(digest_date)
            existing = existing_digest["items"] if existing_digest else []
            if not messages:
                self.db.update_job(job_id, status="completed", stage="没有新增消息", progress=100)
                return
            serialized_size = sum(len(m["content"]) for m in messages)
            if serialized_size > self.config.max_input_chars:
                raise ValueError(f"本次新增文本过长（{serialized_size} 字符），请分批粘贴")
            self.db.update_job(job_id, stage="廉价模型初筛", progress=30)
            candidates = await self._screen(messages)
            by_id = {m["id"]: m for m in messages}
            self.db.update_job(job_id, stage="核验候选链接", progress=55)
            pages = await self._fetch_links(candidates, by_id)
            self.db.update_job(job_id, stage="生成最终简报", progress=75)
            if self.model.enabled:
                candidate_payload = []
                for candidate in candidates:
                    message = by_id[candidate["message_id"]]
                    candidate_payload.append({"screening": candidate, "message": {"author": message["author"], "time": message["source_time"], "content": message["content"], "links": message["links"]}, "verified_pages": [pages[url] for url in message["links"] if url in pages]})
                result = await self.model.json_completion(self.config.final_model, FINAL_SYSTEM, {"candidates": candidate_payload, "existing_digest_items": existing})
                items = self._rank(result.get("must_read", []), result.get("interesting", []))
            else:
                items = self._local_final(candidates, by_id, pages, existing)

            # Never retain model-invented links or trust a model-only verification claim.
            allowed_links = {url for message in messages for url in message["links"]}
            allowed_links.update(url for item in existing for url in item.get("links", []))
            verified_links = {url for url, page in pages.items() if page.get("status") == "verified"}
            verified_links.update(
                url
                for item in existing
                if item.get("credibility") == "verified"
                for url in item.get("links", [])
            )
            for item in items:
                item["links"] = [url for url in item["links"] if url in allowed_links]
                if item["credibility"] == "verified" and not any(url in verified_links for url in item["links"]):
                    item["credibility"] = "unverified"

            stats = {"total": len(items), "must_read": sum(i["section"] == "must_read" for i in items), "interesting": sum(i["section"] == "interesting" for i in items), "categories": dict(Counter(i["category"] for i in items)), "model_mode": "cloud" if self.model.enabled else "local_fallback"}
            self.db.save_digest(digest_date, items, stats)
            self.db.update_job(job_id, status="completed", stage="简报已生成，原始文本已删除", progress=100)
        except Exception as exc:
            self.db.update_job(job_id, status="failed", stage="处理失败，原始文本已保留", progress=100, error=str(exc)[:1000])


