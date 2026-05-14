-- ns8-rag database schema.
-- Applied at every rag-pod startup; all statements are idempotent.
-- This module is fresh-install only: no migration tracking.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS module_state (
    key TEXT PRIMARY KEY,
    value_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS source (
    id UUID PRIMARY KEY,
    source_type TEXT NOT NULL,
    instance_id TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT false,
    config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    sync_cursor TEXT,
    last_sync_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS source_object (
    id UUID PRIMARY KEY,
    source_id UUID NOT NULL REFERENCES source(id) ON DELETE CASCADE,
    source_object_id TEXT NOT NULL,
    object_type TEXT NOT NULL,
    uri TEXT NOT NULL,
    title TEXT,
    content_type TEXT,
    size_bytes BIGINT,
    etag TEXT,
    mtime TIMESTAMPTZ,
    content_hash TEXT,
    acl_hash TEXT,
    acl_checked_at TIMESTAMPTZ,
    acl_state TEXT NOT NULL DEFAULT 'unknown',
    acl_error TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    state TEXT NOT NULL DEFAULT 'discovered',
    deleted_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source_id, source_object_id)
);

CREATE TABLE IF NOT EXISTS source_acl (
    source_object_id UUID NOT NULL REFERENCES source_object(id) ON DELETE CASCADE,
    principal_id TEXT NOT NULL,
    permission TEXT NOT NULL DEFAULT 'read',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(source_object_id, principal_id, permission)
);

CREATE TABLE IF NOT EXISTS chunk (
    id UUID PRIMARY KEY,
    source_object_id UUID NOT NULL REFERENCES source_object(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    token_count INTEGER,
    page_start INTEGER,
    page_end INTEGER,
    locator_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source_object_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS vector_collection (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    embedding_provider TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding_dimension INTEGER NOT NULL,
    distance_metric TEXT NOT NULL DEFAULT 'Cosine',
    chunker_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'building',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    activated_at TIMESTAMPTZ,
    deprecated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS chunk_vector (
    chunk_id UUID NOT NULL REFERENCES chunk(id) ON DELETE CASCADE,
    collection_id UUID NOT NULL REFERENCES vector_collection(id) ON DELETE CASCADE,
    qdrant_point_id UUID NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready',
    embedded_at TIMESTAMPTZ,
    error TEXT,
    PRIMARY KEY(chunk_id, collection_id)
);

CREATE TABLE IF NOT EXISTS ingest_job (
    id UUID PRIMARY KEY,
    source_id UUID REFERENCES source(id) ON DELETE SET NULL,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS user_token (
    id TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL,
    username TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    scopes TEXT[] NOT NULL DEFAULT ARRAY['query'],
    enabled BOOLEAN NOT NULL DEFAULT true,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY,
    request_id TEXT NOT NULL,
    principal_id TEXT,
    token_id TEXT,
    action TEXT NOT NULL,
    source_object_id UUID,
    query TEXT,
    result_count INTEGER,
    status TEXT NOT NULL,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS source_one_active_type_idx
    ON source(source_type) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS source_object_source_state_idx ON source_object(source_id, state);
CREATE INDEX IF NOT EXISTS source_object_deleted_idx ON source_object(deleted_at);
CREATE INDEX IF NOT EXISTS source_object_seen_idx ON source_object(source_id, last_seen_at);
CREATE INDEX IF NOT EXISTS source_object_acl_state_idx ON source_object(acl_state);
CREATE INDEX IF NOT EXISTS source_acl_principal_idx ON source_acl(principal_id, source_object_id);
CREATE INDEX IF NOT EXISTS chunk_object_idx ON chunk(source_object_id);
CREATE INDEX IF NOT EXISTS chunk_vector_collection_status_idx ON chunk_vector(collection_id, status);
CREATE INDEX IF NOT EXISTS ingest_job_status_idx ON ingest_job(status, created_at);
CREATE INDEX IF NOT EXISTS audit_log_created_idx ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS user_token_principal_enabled_idx ON user_token(principal_id, enabled);
