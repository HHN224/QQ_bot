from __future__ import annotations

import asyncio

import pytest

from app.services.fetcher import UnsafeUrlError, fetch_public_page


def test_private_address_is_blocked_before_request():
    with pytest.raises(UnsafeUrlError, match="私网|本机|保留"):
        asyncio.run(fetch_public_page("http://127.0.0.1/private"))
