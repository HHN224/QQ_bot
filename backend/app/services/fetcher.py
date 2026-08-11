from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


class UnsafeUrlError(ValueError):
    pass


async def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrlError("仅允许公开的 HTTP/HTTPS 链接")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("不允许带认证信息的链接")
    loop = asyncio.get_running_loop()
    try:
        results = await loop.run_in_executor(None, lambda: socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM))
    except socket.gaierror as exc:
        raise UnsafeUrlError("域名无法解析") from exc
    for result in results:
        ip = ipaddress.ip_address(result[4][0])
        if not ip.is_global:
            raise UnsafeUrlError("已拦截本机、私网或保留地址")


async def fetch_public_page(url: str, timeout: float = 10.0) -> dict[str, str]:
    headers = {"User-Agent": "QQDailyDigest/0.1 (local read-only summarizer)"}
    current = url
    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=False) as client:
        for _ in range(4):
            await _validate_url(current)
            response = await client.get(current)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    break
                current = urljoin(current, location)
                continue
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" not in content_type and "text/plain" not in content_type:
                return {"url": current, "title": "非文本页面", "text": "页面不是可摘要的文字内容。", "status": "unsupported"}
            raw = response.content[:1_500_000]
            soup = BeautifulSoup(raw, "html.parser")
            for tag in soup(["script", "style", "noscript", "svg"]):
                tag.decompose()
            title = soup.title.get_text(" ", strip=True) if soup.title else current
            text = " ".join(soup.get_text(" ", strip=True).split())[:12_000]
            return {"url": current, "title": title[:300], "text": text, "status": "verified"}
    raise UnsafeUrlError("重定向次数过多")

