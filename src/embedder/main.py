import os
import threading

from fastapi import FastAPI
from pydantic import BaseModel


app = FastAPI(title="ns8-rag embedder", version="0.1.0")

_model = None
_model_lock = threading.Lock()


def _load_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        from sentence_transformers import SentenceTransformer

        model_name = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3")
        cache = os.environ.get("MODEL_CACHE_DIR", "/state/model-cache")
        device = os.environ.get("EMBEDDING_DEVICE", "cpu")
        _model = SentenceTransformer(model_name, cache_folder=cache, device=device)
    return _model


class EmbedRequest(BaseModel):
    texts: list[str]


@app.on_event("startup")
def _warmup() -> None:
    _load_model()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model_loaded": _model is not None}


@app.post("/embed")
def embed(payload: EmbedRequest) -> dict:
    model = _load_model()
    normalize = os.environ.get("EMBEDDING_NORMALIZE", "true").lower() in {"1", "true", "yes", "on"}
    vectors = model.encode(
        payload.texts,
        batch_size=int(os.environ.get("EMBEDDING_BATCH_SIZE", "16")),
        normalize_embeddings=normalize,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return {"vectors": [vec.tolist() for vec in vectors]}
