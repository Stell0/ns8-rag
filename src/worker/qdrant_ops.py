"""Qdrant client helper."""
from __future__ import annotations

import os

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm


def client() -> QdrantClient:
    return QdrantClient(
        host=os.environ.get("QDRANT_HOST", "127.0.0.1"),
        port=int(os.environ.get("QDRANT_PORT", "6333")),
        api_key=os.environ.get("QDRANT_API_KEY") or None,
        https=False,
        prefer_grpc=False,
    )


def ensure_collection(name: str, dimension: int) -> None:
    qc = client()
    existing = {c.name for c in qc.get_collections().collections}
    if name in existing:
        return
    qc.create_collection(
        collection_name=name,
        vectors_config=qm.VectorParams(size=dimension, distance=qm.Distance.COSINE),
    )


def upsert_points(
    name: str,
    ids: list[str],
    vectors: list[list[float]],
    payloads: list[dict],
) -> None:
    qc = client()
    points = [
        qm.PointStruct(id=pid, vector=vec, payload=payload)
        for pid, vec, payload in zip(ids, vectors, payloads)
    ]
    qc.upsert(collection_name=name, points=points)


def search(
    name: str,
    vector: list[float],
    limit: int,
    principal_ids: list[str] | None = None,
) -> list[qm.ScoredPoint]:
    qc = client()
    flt = None
    if principal_ids:
        flt = qm.Filter(should=[
            qm.FieldCondition(key="principal_ids", match=qm.MatchValue(value=p))
            for p in principal_ids
        ])
    response = qc.query_points(
        collection_name=name, query=vector, limit=limit, query_filter=flt,
    )
    return response.points
