from fastapi import APIRouter

from common.state import enabled_sources, internal_url, load_runtime_state, load_sync_status


router = APIRouter(prefix="/api")


@router.get("/status")
def status() -> dict:
    return {
        "internal_url": internal_url(),
        "same_node_only": True,
        "status": load_runtime_state(),
        "sync": load_sync_status(),
        "enabled_sources": enabled_sources(),
    }