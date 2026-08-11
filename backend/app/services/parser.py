from __future__ import annotations

import hashlib
import re
from typing import Any

URL_RE = re.compile(r"https?://[^\s<>\]\[\"']+", re.IGNORECASE)
HEADER_PATTERNS = (
    re.compile(r"^\[?(?P<time>\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?\s+\d{1,2}:\d{2}(?::\d{2})?)\]?\s+(?P<author>[^:：]{1,80})[:：]?\s*(?P<content>.*)$"),
    re.compile(r"^(?P<author>[^\s:：]{1,40})\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*$"),
    re.compile(r"^(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s+(?P<author>[^:：]{1,80})[:：]\s*(?P<content>.*)$"),
    re.compile(r"^(?P<author>[^:：]{1,40})[:：]\s*(?P<content>.+)$"),
)


def normalize(text: str) -> str:
    text = text.replace("\u200b", "").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def _finish(author: str, source_time: str, parts: list[str], digest_date: str) -> dict[str, Any] | None:
    content = normalize("\n".join(parts))
    if not content:
        return None
    links = [link.rstrip(".,;!?，。；！？)") for link in URL_RE.findall(content)]
    stable = re.sub(r"\s+", " ", content).casefold()
    digest = hashlib.sha256(f"{digest_date}|{author.strip()}|{source_time.strip()}|{stable}".encode("utf-8")).hexdigest()
    return {"author": author.strip() or "未知发送者", "time": source_time.strip() or "时间未知", "content": content, "links": list(dict.fromkeys(links)), "hash": digest}


def parse_chat(text: str, digest_date: str) -> list[dict[str, Any]]:
    lines = normalize(text).splitlines()
    messages: list[dict[str, Any]] = []
    author, source_time, parts = "未知发送者", "时间未知", []
    matched_any = False
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        match = None
        for index, pattern in enumerate(HEADER_PATTERNS):
            # A URL contains a colon but is message content, not an "author: content" header.
            if index == len(HEADER_PATTERNS) - 1 and "://" in line:
                continue
            match = pattern.match(line)
            if match:
                break
        if match:
            matched_any = True
            previous = _finish(author, source_time, parts, digest_date)
            if previous:
                messages.append(previous)
            groups = match.groupdict()
            author = groups.get("author") or "未知发送者"
            source_time = groups.get("time") or "时间未知"
            parts = [groups.get("content") or ""]
        else:
            parts.append(line)
    final = _finish(author, source_time, parts, digest_date)
    if final:
        messages.append(final)
    if not matched_any and len(messages) == 1:
        # Unknown exports are kept as line-sized messages so one long paste does not become one candidate.
        messages = []
        for line in lines:
            item = _finish("未知发送者", "时间未知", [line], digest_date)
            if item:
                messages.append(item)
    return messages
