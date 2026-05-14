from __future__ import annotations

import hashlib
import hmac
import os

from fastapi import HTTPException

from common.db import transaction


def _token_hash(token_id: str, secret: str) -> str:
    pepper = os.environ.get("RAG_TOKEN_PEPPER", "")
    payload = f"{token_id}.{secret}".encode()
    return hmac.new(pepper.encode(), payload, hashlib.sha256).hexdigest()


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    return value.strip()


def validate_bearer_token(authorization: str | None) -> dict:
    token = _extract_bearer_token(authorization)
    if not token.startswith("rag_ut_"):
        raise HTTPException(status_code=401, detail="Invalid token format")

    token_body = token[len("rag_ut_") :]
    try:
        token_id, secret = token_body.rsplit("_", 1)
    except ValueError as error:
        raise HTTPException(status_code=401, detail="Invalid token format") from error

    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, principal_id, username, token_hash, enabled, revoked_at
                FROM user_token WHERE id = %s
                """,
                (token_id,),
            )
            row = cur.fetchone()
            if not row or not row["enabled"] or row["revoked_at"] is not None:
                raise HTTPException(status_code=401, detail="Invalid token")
            candidate = _token_hash(token_id, secret)
            if not hmac.compare_digest(candidate, row["token_hash"]):
                raise HTTPException(status_code=401, detail="Invalid token")
            cur.execute(
                "UPDATE user_token SET last_used_at = now() WHERE id = %s",
                (token_id,),
            )
    return {
        "token_id": row["id"],
        "principal_id": row["principal_id"],
        "username": row["username"],
    }

