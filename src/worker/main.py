from __future__ import annotations

import hashlib
import json
import os
import time
import uuid

from common.bootstrap import bootstrap_all, import_pending_jobs
from common.db import transaction
from common.state import (
    active_collection,
    enabled_sources,
    load_runtime_state,
    nextcloud_user_passwords,
    save_runtime_state,
    source_config,
    utcnow,
)
from worker.adapters.nextcloud import NextcloudClient, iter_personal_files
from worker.chunker import CHUNKER_VERSION, chunk_text
from worker.embedder_client import embed
from worker.parser import parse
from worker.qdrant_ops import ensure_collection, upsert_points


def _next_queued_job(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, source_id, job_type, payload_json FROM ingest_job "
            "WHERE status = 'queued' ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
        return cur.fetchone()


def _mark_running(conn, job_id):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE ingest_job SET status='running', started_at=now() WHERE id=%s",
            (job_id,),
        )


def _mark_finished(conn, job_id, error: str | None = None):
    status = "failed" if error else "finished"
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE ingest_job SET status=%s, finished_at=now(), error=%s WHERE id=%s",
            (status, error, job_id),
        )


def _ensure_vector_collection(conn) -> tuple[str, str, int]:
    """Return (collection_id, qdrant_name, dimension), creating if needed."""
    coll = active_collection()
    name = coll["name"]
    dim = int(coll["embedding_dimension"])
    model = coll["embedding_model"]
    provider = os.environ.get("EMBEDDING_PROVIDER", "local")
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM vector_collection WHERE name=%s", (name,))
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE vector_collection SET status='active', activated_at=COALESCE(activated_at, now()) "
                "WHERE id=%s",
                (row["id"],),
            )
            collection_id = str(row["id"])
        else:
            cur.execute(
                """
                INSERT INTO vector_collection
                    (id, name, embedding_provider, embedding_model, embedding_dimension,
                     chunker_version, status, activated_at)
                VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, 'active', now())
                RETURNING id
                """,
                (name, provider, model, dim, CHUNKER_VERSION),
            )
            collection_id = str(cur.fetchone()["id"])
        cur.execute(
            "INSERT INTO module_state(key, value_json) VALUES ('active_collection_id', %s::jsonb) "
            "ON CONFLICT (key) DO UPDATE SET value_json=EXCLUDED.value_json, updated_at=now()",
            (json.dumps(collection_id),),
        )
    ensure_collection(name, dim)
    return collection_id, name, dim


def _sync_nextcloud(conn, collection_id: str, qdrant_name: str) -> tuple[int, int]:
    cfg = source_config()["nextcloud"]
    if not cfg["enabled"] or not cfg["base_url"]:
        return 0, 0
    passwords = nextcloud_user_passwords()
    users = cfg.get("users") or []
    if not users:
        return 0, 0

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM source WHERE source_type='nextcloud' AND deleted_at IS NULL"
        )
        row = cur.fetchone()
        if not row:
            return 0, 0
        source_id = str(row["id"])

    client = NextcloudClient(cfg["base_url"], tls_verify=cfg.get("tls_verify", True))
    objects = 0
    chunks_written = 0

    for nc in iter_personal_files(users, passwords, client):
        objects += 1
        source_object_id = f"nextcloud://{nc.username}/{nc.path}"
        uri = source_object_id
        title = nc.path.split("/")[-1] or nc.path
        try:
            content = client.download(nc.username, passwords[nc.username], nc.href)
        except Exception as exc:  # noqa: BLE001
            print(f"[worker] download failed {uri}: {exc}", flush=True)
            continue
        content_hash = hashlib.sha256(content).hexdigest()

        # Upsert source_object first
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO source_object
                    (id, source_id, source_object_id, object_type, uri, title,
                     content_type, size_bytes, etag, content_hash, acl_state, acl_checked_at,
                     state, last_seen_at)
                VALUES (gen_random_uuid(), %s, %s, 'file', %s, %s, %s, %s, %s, %s,
                        'valid', now(), 'indexed', now())
                ON CONFLICT (source_id, source_object_id) DO UPDATE SET
                    uri = EXCLUDED.uri,
                    title = EXCLUDED.title,
                    content_type = EXCLUDED.content_type,
                    size_bytes = EXCLUDED.size_bytes,
                    etag = EXCLUDED.etag,
                    content_hash = EXCLUDED.content_hash,
                    acl_state = 'valid',
                    acl_checked_at = now(),
                    state = 'indexed',
                    last_seen_at = now(),
                    updated_at = now()
                RETURNING id
                """,
                (source_id, source_object_id, uri, title, nc.content_type,
                 nc.size, nc.etag, content_hash),
            )
            object_id = str(cur.fetchone()["id"])
            # ACL: this user only.
            cur.execute(
                "INSERT INTO source_acl(source_object_id, principal_id, permission) "
                "VALUES (%s, %s, 'read') ON CONFLICT DO NOTHING",
                (object_id, nc.principal_id),
            )

        # Parse with Tika
        try:
            text = parse(content, nc.content_type)
        except Exception as exc:  # noqa: BLE001
            print(f"[worker] parse failed {uri}: {exc}", flush=True)
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE source_object SET state='failed', acl_error=%s, updated_at=now() WHERE id=%s",
                    (str(exc)[:500], object_id),
                )
            continue

        pieces = chunk_text(text)
        if not pieces:
            continue

        # Replace any existing chunks for this object (simple full refresh)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chunk WHERE source_object_id=%s", (object_id,))

        vectors = embed(pieces)
        point_ids: list[str] = []
        chunk_rows: list[tuple] = []
        payloads: list[dict] = []
        for idx, (piece, vec) in enumerate(zip(pieces, vectors)):
            chunk_id = str(uuid.uuid4())
            point_id = str(uuid.uuid4())
            piece_hash = hashlib.sha256(piece.encode()).hexdigest()
            chunk_rows.append((chunk_id, object_id, idx, piece, piece_hash, len(piece)))
            point_ids.append(point_id)
            payloads.append({
                "chunk_id": chunk_id,
                "source_object_id": object_id,
                "source_type": "nextcloud",
                "source_instance": cfg["instance"],
                "principal_ids": [nc.principal_id],
                "acl_state": "valid",
                "deleted": False,
            })

        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO chunk(id, source_object_id, chunk_index, content, content_hash, token_count)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                chunk_rows,
            )
            for (chunk_id, *_), point_id in zip(chunk_rows, point_ids):
                cur.execute(
                    """
                    INSERT INTO chunk_vector(chunk_id, collection_id, qdrant_point_id, status, embedded_at)
                    VALUES (%s, %s, %s, 'ready', now())
                    ON CONFLICT (chunk_id, collection_id) DO UPDATE SET
                        qdrant_point_id = EXCLUDED.qdrant_point_id,
                        status = 'ready',
                        embedded_at = now()
                    """,
                    (chunk_id, collection_id, point_id),
                )

        upsert_points(qdrant_name, point_ids, vectors, payloads)
        chunks_written += len(pieces)

    return objects, chunks_written


def process_next_job() -> bool:
    with transaction() as conn:
        job = _next_queued_job(conn)
        if not job:
            return False
        _mark_running(conn, job["id"])

    error: str | None = None
    try:
        with transaction() as conn:
            collection_id, qdrant_name, _ = _ensure_vector_collection(conn)
            objects, chunks_written = _sync_nextcloud(conn, collection_id, qdrant_name)
            print(f"[worker] sync done: objects={objects} chunks={chunks_written}", flush=True)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        print(f"[worker] job failed: {error}", flush=True)

    with transaction() as conn:
        _mark_finished(conn, job["id"], error)
        # Update runtime status counters from authoritative DB
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS c FROM source_object WHERE deleted_at IS NULL AND state='indexed'"
            )
            objects_total = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM chunk")
            chunks_total = cur.fetchone()["c"]
    state = load_runtime_state()
    state.update({
        "objects": int(objects_total),
        "chunks": int(chunks_total),
        "errors": 1 if error else 0,
        "index_status": "ready" if not error else "error",
        "active_collection": active_collection(),
        "last_sync_at": utcnow(),
    })
    save_runtime_state(state)
    return True


def main() -> None:
    bootstrap_all()
    poll_seconds = int(os.environ.get("RAG_WORKER_POLL_SECONDS", "5"))
    while True:
        try:
            bootstrap_all()
            import_pending_jobs()
            processed = process_next_job()
        except Exception as exc:  # noqa: BLE001
            print(f"[worker] loop error: {exc}", flush=True)
            processed = False
        if not processed:
            time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
