"""Bootstrap PostgreSQL state from on-disk files written by NS8 actions.

This bridges between the action-layer truth (tokens/hashes.json, env vars) and
the database-layer truth used by rag-api/rag-worker at runtime.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from common.db import transaction
from common.state import STATE_DIR


def _load_hashes() -> list[dict]:
    path = STATE_DIR / "tokens" / "hashes.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text()).get("tokens", [])
    except (OSError, json.JSONDecodeError):
        return []


def sync_user_tokens() -> int:
    entries = _load_hashes()
    if not entries:
        return 0
    with transaction() as conn:
        with conn.cursor() as cur:
            for entry in entries:
                cur.execute(
                    """
                    INSERT INTO user_token
                        (id, principal_id, username, token_hash, enabled,
                         generated_at, revoked_at, last_used_at)
                    VALUES (%s, %s, %s, %s, %s,
                            COALESCE(%s::timestamptz, now()),
                            %s::timestamptz, %s::timestamptz)
                    ON CONFLICT (id) DO UPDATE SET
                        principal_id = EXCLUDED.principal_id,
                        username = EXCLUDED.username,
                        token_hash = EXCLUDED.token_hash,
                        enabled = EXCLUDED.enabled,
                        revoked_at = EXCLUDED.revoked_at
                    """,
                    (
                        entry["token_id"],
                        entry["principal_id"],
                        entry["username"],
                        entry["token_hash"],
                        bool(entry.get("enabled", True)),
                        entry.get("generated_at"),
                        entry.get("revoked_at"),
                        entry.get("last_used_at"),
                    ),
                )
    return len(entries)


def upsert_nextcloud_source() -> str | None:
    """Ensure a `source` row exists for the configured Nextcloud instance.

    Returns the source id, or None if Nextcloud is not enabled.
    """
    from common.state import source_config, to_bool, nextcloud_user_passwords

    cfg = source_config()["nextcloud"]
    if not cfg["enabled"] or not cfg["instance"] or not cfg["base_url"]:
        return None

    passwords = nextcloud_user_passwords()
    users = cfg.get("users") or []
    # Public config in the DB never includes secrets.
    config_payload = {
        "mode": cfg.get("mode", "personal_files"),
        "base_url": cfg["base_url"],
        "tls_verify": cfg.get("tls_verify", True),
        "users": [
            {
                "principal_id": u["principal_id"],
                "username": u["username"],
                "root_path": u["root_path"],
                "has_password": u["username"] in passwords,
            }
            for u in users
        ],
    }

    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM source WHERE source_type = 'nextcloud' AND deleted_at IS NULL"
            )
            row = cur.fetchone()
            if row:
                source_id = str(row["id"])
                cur.execute(
                    """
                    UPDATE source
                    SET instance_id = %s,
                        enabled = true,
                        config_json = %s::jsonb,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (cfg["instance"], json.dumps(config_payload), source_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO source (id, source_type, instance_id, enabled, config_json)
                    VALUES (gen_random_uuid(), 'nextcloud', %s, true, %s::jsonb)
                    RETURNING id
                    """,
                    (cfg["instance"], json.dumps(config_payload)),
                )
                source_id = str(cur.fetchone()["id"])
    return source_id


def bootstrap_all() -> None:
    try:
        sync_user_tokens()
    except Exception as e:  # noqa: BLE001 - log and continue
        print(f"[bootstrap] sync_user_tokens failed: {e}", flush=True)
    try:
        upsert_nextcloud_source()
    except Exception as e:  # noqa: BLE001
        print(f"[bootstrap] upsert_nextcloud_source failed: {e}", flush=True)


def import_pending_jobs() -> int:
    """Import queued jobs written by start-sync (jobs.json) into the DB queue.

    Each successfully imported entry is rewritten with status='imported' so it
    is not re-imported on the next poll. Jobs in any other state are left alone.
    """
    path = STATE_DIR / "jobs.json"
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return 0
    jobs = data.get("jobs") or []
    queued = [j for j in jobs if j.get("status") == "queued"]
    if not queued:
        return 0
    imported = 0
    with transaction() as conn:
        with conn.cursor() as cur:
            for job in queued:
                cur.execute(
                    """
                    INSERT INTO ingest_job(id, job_type, status, payload_json)
                    VALUES (gen_random_uuid(), %s, 'queued', %s::jsonb)
                    """,
                    (job.get("job_type", "sync_all"), json.dumps({"origin_id": job.get("id")})),
                )
                job["status"] = "imported"
                imported += 1
    if imported:
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return imported
