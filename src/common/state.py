from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


STATE_DIR = Path(os.environ.get("STATE_DIR", "/state"))


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent) as handle:
        handle.write(content)
        temp_name = handle.name
    Path(temp_name).replace(path)


def load_json(relative_path: str, default: dict) -> dict:
    path = STATE_DIR / relative_path
    if not path.exists():
        return default.copy()
    with path.open() as handle:
        return json.load(handle)


def save_json(relative_path: str, payload: dict) -> None:
    _atomic_write(STATE_DIR / relative_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def append_jsonl(relative_path: str, payload: dict) -> None:
    path = STATE_DIR / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def default_runtime_state() -> dict:
    return {
        "objects": 0,
        "chunks": 0,
        "errors": 0,
        "index_status": "not_configured",
        "active_collection": None,
        "last_sync_at": None,
    }


def default_sync_status() -> dict:
    return {
        "status": "idle",
        "current_job_id": None,
        "queued_at": None,
        "last_started_at": None,
        "last_finished_at": None,
        "last_successful_sync_at": None,
        "last_error": None,
    }


def load_runtime_state() -> dict:
    return load_json("runtime-state.json", default_runtime_state())


def save_runtime_state(payload: dict) -> None:
    save_json("runtime-state.json", payload)


def load_sync_status() -> dict:
    return load_json("sync-status.json", default_sync_status())


def save_sync_status(payload: dict) -> None:
    save_json("sync-status.json", payload)


def load_jobs() -> dict:
    return load_json("jobs.json", {"jobs": []})


def save_jobs(payload: dict) -> None:
    save_json("jobs.json", payload)


def load_token_hashes() -> dict:
    return load_json("tokens/hashes.json", {"updated_at": utcnow(), "tokens": []})


def save_token_hashes(payload: dict) -> None:
    save_json("tokens/hashes.json", payload)


def to_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def internal_url() -> str:
    return f"http://127.0.0.1:{os.environ.get('TCP_PORT', '20073')}/api"


def _safe_json(raw: str | None, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def nextcloud_user_passwords() -> dict:
    return _safe_json(os.environ.get("NEXTCLOUD_USER_PASSWORDS_JSON"), {})


def source_config() -> dict:
    return {
        "nextcloud": {
            "enabled": to_bool(os.environ.get("NEXTCLOUD_ENABLED")),
            "instance": os.environ.get("NEXTCLOUD_INSTANCE", ""),
            "mode": os.environ.get("NEXTCLOUD_MODE", "personal_files"),
            "base_url": os.environ.get("NEXTCLOUD_BASE_URL", ""),
            "tls_verify": to_bool(os.environ.get("NEXTCLOUD_TLS_VERIFY"), True),
            "users": _safe_json(os.environ.get("NEXTCLOUD_USERS_JSON"), []),
        },
        "samba": {
            "enabled": to_bool(os.environ.get("SAMBA_ENABLED")),
            "instance": os.environ.get("SAMBA_INSTANCE", ""),
        },
        "webtop": {
            "enabled": to_bool(os.environ.get("WEBTOP_ENABLED")),
            "instance": os.environ.get("WEBTOP_INSTANCE", ""),
        },
        "nethvoice": {
            "enabled": to_bool(os.environ.get("NETHVOICE_ENABLED")),
            "instance": os.environ.get("NETHVOICE_INSTANCE", ""),
        },
        "mattermost": {
            "enabled": to_bool(os.environ.get("MATTERMOST_ENABLED")),
            "instance": os.environ.get("MATTERMOST_INSTANCE", ""),
        },
    }


def enabled_sources() -> list[dict]:
    return [
        {"source": name, "instance": entry["instance"]}
        for name, entry in source_config().items()
        if entry["enabled"]
    ]


def active_collection() -> dict:
    model = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3")
    model_name = model.split("/")[-1].lower().replace("_", "-")
    return {
        "name": f"{model_name}-v1",
        "embedding_model": model,
        "embedding_dimension": int(os.environ.get("EMBEDDING_DIMENSION", "1024")),
    }
