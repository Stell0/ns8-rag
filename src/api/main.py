from fastapi import FastAPI

from api.routes.health import router as health_router
from api.routes.query import router as query_router
from api.routes.status import router as status_router
from common.bootstrap import bootstrap_all


app = FastAPI(title="ns8-rag API", version="0.1.0")
app.include_router(health_router)
app.include_router(status_router)
app.include_router(query_router)


@app.on_event("startup")
def _bootstrap() -> None:
    try:
        bootstrap_all()
    except Exception as exc:  # noqa: BLE001
        print(f"[api] bootstrap failed: {exc}", flush=True)
