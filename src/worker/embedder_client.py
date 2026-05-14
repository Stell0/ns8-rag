"""Embedder client (same-pod HTTP)."""
from __future__ import annotations

import os
import requests


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    url = os.environ.get("EMBEDDER_URL", "http://127.0.0.1:8090").rstrip("/") + "/embed"
    resp = requests.post(url, json={"texts": texts}, timeout=600)
    resp.raise_for_status()
    return resp.json()["vectors"]
