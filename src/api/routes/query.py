import os
import secrets

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from common.auth import validate_bearer_token
from common.db import transaction
from common.state import active_collection
from worker.embedder_client import embed
from worker.qdrant_ops import search


router = APIRouter(prefix="/api")


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=10, ge=1, le=50)


def _resolve_principals(principal_id: str) -> list[str]:
    """Return all principal_ids that count as the caller for ACL checks.

    Personal-files mode uses exact user match only; groups can be added later.
    """
    return [principal_id]


@router.post("/query")
def query(payload: QueryRequest, authorization: str | None = Header(default=None)) -> dict:
    token = validate_bearer_token(authorization)
    request_id = f"ragq_{secrets.token_hex(8)}"
    principal_ids = _resolve_principals(token["principal_id"])

    overfetch = max(payload.top_k * 5, 20)
    coll = active_collection()
    vectors = embed([payload.query])
    if not vectors:
        return {"request_id": request_id, "results": []}

    try:
        candidates = search(coll["name"], vectors[0], overfetch, principal_ids)
    except Exception as exc:  # noqa: BLE001
        # Collection may not exist yet (no sync completed). Return empty.
        candidates = []
        print(f"[api] qdrant search failed: {exc}", flush=True)

    results: list[dict] = []
    if candidates:
        chunk_ids = [str(c.payload.get("chunk_id")) for c in candidates if c.payload]
        scores = {str(c.payload.get("chunk_id")): float(c.score) for c in candidates if c.payload}
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT c.id AS chunk_id, c.content, c.chunk_index,
                           o.id AS source_object_id, o.uri, o.title, o.content_type,
                           o.acl_state, s.source_type, s.instance_id AS source_instance
                    FROM chunk c
                    JOIN source_object o ON o.id = c.source_object_id
                    JOIN source s ON s.id = o.source_id
                    WHERE c.id = ANY(%s::uuid[])
                      AND o.acl_state = 'valid'
                      AND o.deleted_at IS NULL
                      AND EXISTS (
                          SELECT 1 FROM source_acl a
                          WHERE a.source_object_id = o.id
                            AND a.principal_id = ANY(%s)
                      )
                    """,
                    (chunk_ids, principal_ids),
                )
                rows = cur.fetchall()
        # Sort rows by candidate score order
        rows.sort(key=lambda r: scores.get(str(r["chunk_id"]), 0.0), reverse=True)
        for row in rows[: payload.top_k]:
            results.append({
                "chunk_id": str(row["chunk_id"]),
                "source_object_id": str(row["source_object_id"]),
                "source_type": row["source_type"],
                "source_instance": row["source_instance"],
                "title": row["title"],
                "uri": row["uri"],
                "locator": {"chunk_index": row["chunk_index"]},
                "content": row["content"],
                "score": scores.get(str(row["chunk_id"]), 0.0),
            })

    max_chars = int(os.environ.get("AUDIT_QUERY_MAX_CHARS", "500"))
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit_log(id, request_id, principal_id, token_id, action, query,
                                      result_count, status)
                VALUES (gen_random_uuid(), %s, %s, %s, 'query', %s, %s, 'allowed')
                """,
                (request_id, token["principal_id"], token["token_id"],
                 payload.query[:max_chars], len(results)),
            )

    return {"request_id": request_id, "results": results}
