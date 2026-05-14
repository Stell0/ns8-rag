"""Tika parser client."""
from __future__ import annotations

import os

import requests


def parse(content: bytes, content_type: str = "") -> str:
    url = os.environ.get("PARSER_URL", "http://127.0.0.1:9998").rstrip("/") + "/tika"
    headers = {"Accept": "text/plain"}
    if content_type:
        headers["Content-Type"] = content_type
    timeout = int(os.environ.get("PARSER_TIMEOUT_SECONDS", "120"))
    resp = requests.put(url, data=content, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text or ""
