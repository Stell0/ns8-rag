# STRUCTURE.md

# ns8-rag Structure and Architecture

`ns8-rag` is a NethServer 8 module that indexes selected business data sources and exposes an internal-only retrieval API for AI assistants and other same-node consumers.

The module is intentionally NS8-native:

- configuration is stored in NS8 environment files;
- administrative operations are implemented as NS8 actions;
- the UI talks only to NS8 actions;
- runtime services run inside one Podman pod;
- the query API is not publicly routed through Traefik;
- PostgreSQL is the source of truth;
- Qdrant is a disposable vector acceleration layer.

---

## 1. Hard architecture rules

These rules are mandatory.

```text
PostgreSQL is the truth.
Qdrant is disposable.
NS8 actions are the admin backend.
The API is internal-only.
Same-node localhost access only in MVP.
Unknown ACL means deny.
Stale ACL means deny.
No chunk leaves rag-api without PostgreSQL ACL confirmation.
Hermes imports a user RAG token; ns8-rag does not generate Hermes-specific files.
```

Security invariants:

```text
- Source credentials stay inside ns8-rag.
- Hermes never receives downstream source credentials.
- Hermes receives only a user-scoped RAG token.
- Clear RAG tokens exist only in %S/state/tokens/users.json.
- PostgreSQL stores token hashes only.
- Qdrant is never trusted for authorization.
- Parser containers receive file bytes, not source credentials.
- There is no public admin HTTP API.
```

---

## 2. Repository structure

Expected module repository layout:

```text
ns8-rag/
  README.md
  AGENTS.md
  STRUCTURE.md

  imageroot/
    actions/
      create-module/
        10generate-secrets
        20init-environment
        30init-directories
        40enable-service

      configure-module/
        10validate-input
        20discover-instances
        30write-environment
        40write-secrets
        50start-postgres-if-needed
        60run-migrations
        70write-effective-source-config
        80generate-or-update-user-tokens
        90restart-api-worker
        100enqueue-initial-sync

      get-configuration/
        10read-environment
        20list-available-instances
        30read-source-status
        40read-index-status
        50read-token-status
        60return-json

      get-defaults/
        10defaults

      start-sync/
        10lock
        20enqueue-sync

      get-sync-status/
        10read-postgres

      get-user-token/
        10validate-request
        20read-token-file
        30return-user-token

      regenerate-user-token/
        10validate-user
        20revoke-old-token
        30generate-new-token
        40write-token-file
        50store-token-hash

      backup-module/
        10enter-maintenance
        20pause-worker
        30wait-or-abort-active-job
        40dump-postgres
        50snapshot-qdrant-optional
        60backup-state
        70exit-maintenance

      restore-module/
        10stop-service
        20restore-env
        30restore-postgres
        40restore-qdrant-optional
        50run-migrations
        60validate-active-vector-collection
        70mark-rebuild-required-if-needed
        80restart-service

      destroy-module/
        10stop-service
        20cleanup-state

    systemd/
      user/
        rag.service
        rag-sync.timer
        rag-sync.service
        rag-maintenance.timer
        rag-maintenance.service

    ui/
      # NS8 UI assets.
      # The UI must call NS8 actions only.
      # No custom rag-ui-backend container.

    migrations/
      001_initial.sql
      002_indexes.sql
      003_optional_full_text.sql

    scripts/
      lib/
        env.sh
        json.sh
        locks.sh
        postgres.sh
        tokens.sh
        podman.sh
        sources.sh
        migrations.sh

  images/
    rag-api/
      Containerfile
      src/

    rag-worker/
      Containerfile
      src/

    rag-embedder/
      Containerfile
      src/

    parser/
      Containerfile
      # Tika by default; Docling/Unstructured later if added.

  src/
    common/
      config/
      db/
      auth/
      acl/
      audit/
      models/
      errors/

    api/
      main.py
      routes/
        query.py
        status.py
        health.py
      services/
        auth.py
        retrieval.py
        acl.py
        audit.py
        embedding.py
        qdrant.py

    worker/
      main.py
      jobs/
        sync_all.py
        sync_source.py
        rebuild_acl.py
        rebuild_vectors.py
        delete_source.py
        maintenance.py
      adapters/
        nextcloud.py
        samba.py
        webtop.py
        nethvoice.py
        mattermost.py
      pipeline/
        discover.py
        fetch.py
        parse.py
        chunk.py
        embed.py
        index.py
        acl.py

    embedder/
      main.py
      models.py
      batching.py

  tests/
    unit/
    integration/
    fixtures/

  docs/
    examples/
      configure-module.input.json
      get-configuration.output.json
      query.response.json
```

Notes:

- `imageroot/actions` is the NS8 administrative backend.
- `imageroot/systemd/user` owns runtime lifecycle and timers.
- `src/api` exposes only query/status/health.
- `src/worker` owns ingestion, ACL refresh, parsing, chunking, embedding and Qdrant indexing.
- `src/common` contains shared contracts used by API and worker.
- `images/*` can be split by container image if separate images are built.
- The MVP can collapse source directories if implementation starts smaller, but contracts must remain the same.

---

## 3. Runtime architecture

Runtime shape:

```text
ns8-rag
  ├── one NS8 module
  ├── one Podman pod: rag-pod
  │   ├── rag-api
  │   ├── rag-worker
  │   ├── rag-embedder
  │   ├── postgres
  │   ├── qdrant
  │   └── parser
  ├── PostgreSQL state DB
  ├── embedded Qdrant vector cache
  ├── NS8 environment files
  ├── generated user token file
  ├── NS8 actions
  ├── NS8 UI without custom backend
  └── systemd user unit + timers
```

Container responsibilities:

| Container | Responsibility | Exposed to host |
|---|---|---|
| `rag-api` | Internal query API, bearer token validation, ACL-enforced retrieval, audit | `127.0.0.1:${TCP_PORT}:8080` only |
| `rag-worker` | Ingestion orchestration, source sync, parsing, chunking, embedding, Qdrant writes | No |
| `rag-embedder` | Internal embedding service | No |
| `postgres` | Metadata, chunks, tokens, ACLs, sync state, audit | No |
| `qdrant` | Vector-only disposable index | No |
| `parser` | Tika parser by default | No |

---

## 4. Pod networking

Pod name:

```text
rag-pod
```

Same-pod containers share one network namespace.

Use loopback between containers:

```text
postgres: 127.0.0.1:5432
qdrant:   127.0.0.1:6333
parser:   127.0.0.1:9998
embedder: 127.0.0.1:8090
rag-api:  127.0.0.1:8080
```

Important rule:

```text
Do not assume postgres, qdrant, parser or embedder hostnames resolve inside the pod.
Use 127.0.0.1 between same-pod containers.
```

Container map:

```text
rag-api
  listens: 0.0.0.0:8080
  host binding: 127.0.0.1:${TCP_PORT}:8080
  talks to:
    postgres 127.0.0.1:5432
    qdrant   127.0.0.1:6333
    embedder 127.0.0.1:8090

rag-worker
  no exposed ports
  talks to:
    postgres 127.0.0.1:5432
    qdrant   127.0.0.1:6333
    parser   127.0.0.1:9998
    embedder 127.0.0.1:8090

rag-embedder
  listens: 127.0.0.1:8090 or 0.0.0.0:8090 inside pod only

postgres
  listens: 127.0.0.1:5432 or 0.0.0.0:5432 inside pod only
  storage: %S/state/postgresql

qdrant
  listens: 127.0.0.1:6333 or 0.0.0.0:6333 inside pod only
  storage: %S/state/qdrant

parser
  listens: 127.0.0.1:9998 or 0.0.0.0:9998 inside pod only
```

---

## 5. Host exposure

There is no public route.

Forbidden:

```text
- Traefik route
- Let's Encrypt certificate
- public firewall opening
- public admin API
- exposed PostgreSQL
- exposed Qdrant
- exposed parser
- exposed worker
- exposed embedder
```

Only allowed host exposure:

```bash
-p 127.0.0.1:${TCP_PORT}:8080
```

Internal API URL:

```env
NS8_RAG_URL=http://127.0.0.1:${TCP_PORT}/api
```

MVP scope:

```text
127.0.0.1 means same node only, not the whole cluster.
```

Valid API consumers:

```text
- same module actions
- host namespace on the same node
- same-node containers with host-loopback access
- Hermes on the same node with suitable network mode
```

Out of scope for MVP:

```text
- cluster-wide API routing
- public HTTP route
- Traefik exposure
- cross-node internal service discovery
```

`get-configuration` must expose this limitation:

```json
{
  "internal_url": "http://127.0.0.1:20073/api",
  "same_node_only": true,
  "node_id": "node1"
}
```

---

## 6. Port allocation

Use one NS8-allocated TCP port.

Image label:

```ini
org.nethserver.tcp-ports-demand = 1
```

Runtime environment:

```env
RAG_API_BIND=0.0.0.0
RAG_API_PORT=8080
RAG_API_PUBLIC_BIND=127.0.0.1
RAG_API_INTERNAL_URL=http://127.0.0.1:${TCP_PORT}/api
```

Rules:

```text
- TCP_PORT is allocated by NS8.
- Do not hardcode RAG_TCP_PORT=20073 as authoritative configuration.
- Do not expose PostgreSQL.
- Do not expose Qdrant.
- Do not expose parser.
- Do not expose worker.
- Do not expose embedder.
```

---

## 7. State and configuration files

State directory files:

```text
%S/state/environment
%S/state/secrets.env
%S/state/generated.env
%S/state/tokens/
%S/state/postgresql/
%S/state/qdrant/
%S/state/model-cache/
```

### `environment`

Admin-controlled configuration only.

Example:

```env
SYNC_INTERVAL_MINUTES=30

EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIMENSION=1024
EMBEDDING_BATCH_SIZE=16
EMBEDDING_DEVICE=cpu
EMBEDDING_NORMALIZE=true

MAX_FILE_SIZE_MB=100
WORKER_CONCURRENCY=1

PARSER_TIMEOUT_SECONDS=120
PARSER_MAX_FILE_SIZE_MB=100
PARSER_MAX_EXTRACTED_TEXT_MB=20
PARSER_MAX_PAGES=500
PARSER_OCR_ENABLED=false
PARSER_ADVANCED_PDF_ENABLED=false

AUDIT_QUERY_MAX_CHARS=500
AUDIT_RETENTION_DAYS=180
FAILED_OBJECT_RETENTION_DAYS=30
DELETED_OBJECT_RETENTION_DAYS=30

NEXTCLOUD_ENABLED=true
NEXTCLOUD_INSTANCE=nextcloud2
NEXTCLOUD_MODE=personal_files
NEXTCLOUD_BASE_URL=https://nextcloud.example.com
NEXTCLOUD_TLS_VERIFY=true
NEXTCLOUD_USERS_JSON=[{"principal_id":"user:openldap1:alice","username":"alice","root_path":"docs"}]

SAMBA_ENABLED=true
SAMBA_INSTANCE=samba1
SAMBA_SHARES=Company,Projects
SAMBA_ACL_MODE=share_groups

WEBTOP_ENABLED=true
WEBTOP_INSTANCE=webtop1
WEBTOP_INGEST_CONTACTS=true
WEBTOP_INGEST_CALENDARS=true
WEBTOP_INGEST_MAIL=false

NETHVOICE_ENABLED=true
NETHVOICE_INSTANCE=nethvoice1
NETHVOICE_INGEST_PHONEBOOK=true
NETHVOICE_INGEST_TRANSCRIPTIONS=true
NETHVOICE_INGEST_RECORDINGS=false

MATTERMOST_ENABLED=true
MATTERMOST_INSTANCE=mattermost1
MATTERMOST_INGEST_POSTS=true
MATTERMOST_INGEST_FILES=true
MATTERMOST_INGEST_DIRECT_MESSAGES=false
```

### `secrets.env`

Module secrets and DB credentials.

```env
POSTGRES_USER=rag
POSTGRES_PASSWORD=...
POSTGRES_DB=rag

RAG_INTERNAL_SECRET=...
RAG_TOKEN_PEPPER=...
QDRANT_API_KEY=...
NEXTCLOUD_USER_PASSWORDS_JSON={"alice":"<app-password>"}
```

### `generated.env`

Runtime values generated by NS8 or `create-module`.

```env
RAG_INSTANCE_ID=rag1
RAG_MODULE_ID=rag1
MODEL_CACHE_DIR=%S/state/model-cache
```

Do not store `TCP_PORT` as permanent authoritative config unless required by NS8 module conventions. Prefer the runtime `TCP_PORT`.

---

## 8. Token files

Generated user token directory:

```text
%S/state/tokens/
  users.json
```

No `hermes.env` is generated by this module.

Example token file:

```json
{
  "generated_at": "2026-05-12T15:00:00Z",
  "tokens": [
    {
      "principal_id": "user:openldap1:alice",
      "username": "alice",
      "token_id": "ut_01HX...",
      "token": "rag_ut_ut_01HX..._7b6f7f3b9d..."
    }
  ]
}
```

Permissions:

```text
%S/state/tokens/            0700
%S/state/tokens/users.json  0600
```

Rules:

```text
- Clear tokens exist only in users.json.
- PostgreSQL stores token hashes only.
- get-configuration never returns clear tokens.
- get-user-token returns one existing token for one configured principal.
- Regeneration revokes old token hashes and rewrites users.json.
```

---

## 9. Hermes integration model

`ns8-rag` exposes a narrow action:

```text
get-user-token
```

Input:

```json
{
  "principal_id": "user:openldap1:alice"
}
```

Output:

```json
{
  "principal_id": "user:openldap1:alice",
  "token": "rag_ut_ut_01HX..._7b6f7f3b9d...",
  "api_url": "http://127.0.0.1:20073/api",
  "same_node_only": true,
  "node_id": "node1"
}
```

Hermes module behavior:

```text
1. Hermes configure action asks ns8-rag for the selected user token.
2. Hermes writes its own local env/config file.
3. Hermes uses NS8_RAG_URL + bearer token to query ns8-rag.
4. ns8-rag does not know or manage Hermes file layout.
```

Security rule:

```text
This is safe only when the Hermes instance/profile is user-bound.
A shared multi-user Hermes gateway must not use one shared RAG token.
```

---

## 10. Database role

Truth model:

```text
Environment files = admin configuration source of truth.
PostgreSQL = normalized runtime state and indexed content source of truth.
Qdrant = rebuildable acceleration layer.
```

PostgreSQL stores:

```text
- effective source configuration snapshots
- source metadata
- source object metadata
- ACL snapshots
- chunks
- chunk text
- vector collection metadata
- chunk-to-vector mapping
- ingestion jobs
- parser errors
- generated token hashes
- audit log
- sync cursors
- module state
```

On configure/startup:

```text
environment -> validation -> normalized source rows in PostgreSQL
```

---

## 11. Database schema

### `module_state`

Stores module runtime status and global state.

```sql
CREATE TABLE module_state (
    key TEXT PRIMARY KEY,
    value_json JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Suggested keys:

```text
maintenance_mode
index_status
active_collection_id
last_successful_sync_at
last_backup_started_at
last_backup_finished_at
```

### `source`

One active source instance per source type.

```sql
CREATE TABLE source (
    id UUID PRIMARY KEY,
    source_type TEXT NOT NULL,
    instance_id TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT false,
    config_json JSONB NOT NULL DEFAULT '{}',
    sync_cursor TEXT,
    last_sync_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX source_one_active_type_idx
ON source(source_type)
WHERE deleted_at IS NULL;
```

Rule:

```text
Only one active instance per source type.
Historical rows are preserved when switching instance.
```

### `source_object`

Represents each indexed object.

```sql
CREATE TABLE source_object (
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
    metadata_json JSONB NOT NULL DEFAULT '{}',
    state TEXT NOT NULL DEFAULT 'discovered',
    deleted_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source_id, source_object_id)
);
```

ACL states:

```text
unknown
valid
stale
failed
unmapped
```

Only `acl_state='valid'` objects can be returned.

### `source_acl`

Maps objects to principals.

```sql
CREATE TABLE source_acl (
    source_object_id UUID NOT NULL REFERENCES source_object(id) ON DELETE CASCADE,
    principal_id TEXT NOT NULL,
    permission TEXT NOT NULL DEFAULT 'read',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(source_object_id, principal_id, permission)
);
```

Principal format:

```text
user:<domain_id>:<username>
group:<domain_id>:<groupname>
```

Examples:

```text
user:openldap1:alice
group:openldap1:sales
user:samba1:alice
group:samba1:engineering
```

### `chunk`

Stores authoritative chunk text.

```sql
CREATE TABLE chunk (
    id UUID PRIMARY KEY,
    source_object_id UUID NOT NULL REFERENCES source_object(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    token_count INTEGER,
    page_start INTEGER,
    page_end INTEGER,
    locator_json JSONB NOT NULL DEFAULT '{}',
    metadata_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source_object_id, chunk_index)
);
```

Do not store `qdrant_point_id` in `chunk`.

### `vector_collection`

Tracks Qdrant collections and embedding configuration.

```sql
CREATE TABLE vector_collection (
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
```

Statuses:

```text
building
active
deprecated
failed
```

### `chunk_vector`

Maps chunks to Qdrant points.

```sql
CREATE TABLE chunk_vector (
    chunk_id UUID NOT NULL REFERENCES chunk(id) ON DELETE CASCADE,
    collection_id UUID NOT NULL REFERENCES vector_collection(id) ON DELETE CASCADE,
    qdrant_point_id UUID NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready',
    embedded_at TIMESTAMPTZ,
    error TEXT,
    PRIMARY KEY(chunk_id, collection_id)
);
```

Purpose:

```text
Support model changes, partial rebuilds, blue/green vector collection switches and failed re-embedding.
```

### `ingest_job`

Worker queue.

```sql
CREATE TABLE ingest_job (
    id UUID PRIMARY KEY,
    source_id UUID REFERENCES source(id) ON DELETE SET NULL,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    payload_json JSONB NOT NULL DEFAULT '{}',
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);
```

Job types:

```text
sync_source
sync_all
rebuild_acl
rebuild_vectors
delete_source
maintenance
```

### `user_token`

Stores token hashes only.

```sql
CREATE TABLE user_token (
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
```

Rules:

```text
- removed users => token disabled
- regenerate user token => old token revoked
- token hash only in DB
- clear token only in users.json
```

### `audit_log`

Records allowed and denied operations.

```sql
CREATE TABLE audit_log (
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
```

Rules:

```text
- truncate query to AUDIT_QUERY_MAX_CHARS
- never log bearer tokens
- audit denied queries too
```

### Required indexes

```sql
CREATE INDEX source_object_source_state_idx
ON source_object(source_id, state);

CREATE INDEX source_object_deleted_idx
ON source_object(deleted_at);

CREATE INDEX source_object_seen_idx
ON source_object(source_id, last_seen_at);

CREATE INDEX source_object_acl_state_idx
ON source_object(acl_state);

CREATE INDEX source_acl_principal_idx
ON source_acl(principal_id, source_object_id);

CREATE INDEX chunk_object_idx
ON chunk(source_object_id);

CREATE INDEX chunk_vector_collection_status_idx
ON chunk_vector(collection_id, status);

CREATE INDEX ingest_job_status_idx
ON ingest_job(status, created_at);

CREATE INDEX audit_log_created_idx
ON audit_log(created_at);

CREATE INDEX user_token_principal_enabled_idx
ON user_token(principal_id, enabled);
```

Optional later:

```sql
ALTER TABLE chunk ADD COLUMN content_tsv tsvector;
CREATE INDEX chunk_content_tsv_idx ON chunk USING GIN(content_tsv);
```

---

## 12. API authentication model

Each configured user/principal receives one generated token.

Token format:

```text
rag_ut_<token_id>_<secret>
```

Validation flow:

```text
1. Parse token_id and secret.
2. Lookup user_token.id.
3. Compute HMAC-SHA256(RAG_TOKEN_PEPPER, token_id || "." || secret).
4. Constant-time compare with token_hash.
5. Check enabled=true.
6. Check revoked_at IS NULL.
7. Resolve principal_id and group principals.
8. Run query with ACL filters.
9. Update last_used_at.
10. Write audit_log.
```

MVP scope:

```text
query
```

Optional later scopes:

```text
status:read
sources:read
admin
```

MVP has no public token management API.

Token operations are NS8 actions only:

```text
- generate missing user tokens
- regenerate all configured user tokens
- regenerate one user token
- disable removed user tokens
- get existing user token for integration import
```

---

## 13. Internal API surface

Only `rag-api` exposes HTTP.

Host binding:

```text
127.0.0.1:${TCP_PORT}:8080
```

Endpoints:

```text
POST /api/query
GET  /api/status
GET  /health
```

Forbidden:

```text
POST /api/tokens
GET  /api/tokens
POST /api/sources
GET  /api/sources
public admin API
```

Admin/configuration is handled by NS8 actions.

---

## 14. Query flow

```text
1. Hermes or internal consumer calls POST /api/query.
2. rag-api validates bearer token.
3. rag-api resolves principal_id.
4. rag-api resolves user and group principals.
5. rag-api embeds query through rag-embedder.
6. rag-api searches the active Qdrant collection.
7. rag-api uses Qdrant principal filters only as coarse optimization.
8. rag-api overfetches candidates.
9. rag-api rechecks every candidate chunk against PostgreSQL ACLs.
10. rag-api rejects stale, unknown, failed or unmapped ACLs.
11. rag-api loads chunk content from PostgreSQL.
12. rag-api returns context and citations.
13. rag-api writes an audit_log row.
```

Hard rule:

```text
No chunk leaves rag-api unless PostgreSQL confirms access.
```

Recommended retrieval defaults:

```text
requested_top_k = 10
qdrant_fetch_k = requested_top_k * 5
max_context_chars = configurable
```

Query response:

```json
{
  "request_id": "ragq_01HX...",
  "results": [
    {
      "chunk_id": "7be1...",
      "source_object_id": "95b2...",
      "source_type": "nextcloud",
      "source_instance": "nextcloud2",
      "title": "Company Policy.pdf",
      "uri": "nextcloud://groupfolders/Company/Company Policy.pdf",
      "locator": {
        "page_start": 4,
        "page_end": 5
      },
      "content": "...",
      "score": 0.82
    }
  ]
}
```

---

## 15. Qdrant role

Qdrant stores vectors and minimal payload only.

Example payload:

```json
{
  "chunk_id": "uuid",
  "source_object_id": "uuid",
  "source_type": "nextcloud",
  "source_instance": "nextcloud2",
  "principal_ids": [
    "user:openldap1:alice",
    "group:openldap1:sales"
  ],
  "acl_state": "valid",
  "deleted": false
}
```

Rules:

```text
- Qdrant does not store authoritative chunk text.
- Qdrant does not store authoritative ACLs.
- Qdrant can be rebuilt from PostgreSQL.
- PostgreSQL ACL check is mandatory.
```

Payload fields to index:

```text
chunk_id
source_object_id
source_type
source_instance
principal_ids
acl_state
deleted
```

Model change flow:

```text
1. Create vector_collection row with status=building.
2. Create new Qdrant collection.
3. Create chunk_vector rows for the new collection.
4. Re-embed chunks from PostgreSQL.
5. Validate collection completeness.
6. Switch active_collection_id in module_state.
7. Mark new vector_collection as active.
8. Mark old collection as deprecated.
9. Optionally delete old Qdrant collection later.
```

---

## 16. Source adapters

MVP rule:

```text
Only one active instance per source type.
```

### Nextcloud

Configuration:

```env
NEXTCLOUD_ENABLED=true
NEXTCLOUD_INSTANCE=nextcloud2
NEXTCLOUD_MODE=groupfolders
```

Index only:

```text
- group folders
- explicitly supported shared folders
- objects whose ACL can be mapped safely to LDAP users/groups
```

Do not index:

```text
- personal folders
- public links
- external storage with unresolved permissions
- shares whose recipient cannot be mapped to LDAP
```

Implementation rule:

```text
Do not ingest by reading raw Nextcloud storage directly.
Use Nextcloud APIs/WebDAV/OCS metadata so ACLs remain verifiable.
```

Safe rule:

```text
If ACL cannot be mapped, the object is not searchable.
```

### Samba

Configuration:

```env
SAMBA_ENABLED=true
SAMBA_INSTANCE=samba1
SAMBA_SHARES=Company,Projects
SAMBA_ACL_MODE=share_groups
```

MVP ACL model:

```text
share -> allowed LDAP groups
```

Safe rule:

```text
Index a Samba object only if:
- the share is explicitly enabled
- the share is mapped to LDAP groups
- the object path is under that share
- the querying user belongs to at least one mapped group
```

Explicit limitation:

```text
File-level ACLs are ignored in MVP.
All indexed files under a configured share are visible to the mapped groups.
```

### WebTop

Configuration:

```env
WEBTOP_ENABLED=true
WEBTOP_INSTANCE=webtop1
WEBTOP_INGEST_CONTACTS=true
WEBTOP_INGEST_CALENDARS=true
WEBTOP_INGEST_MAIL=false
```

MVP:

```text
- shared contacts
- shared calendars
- user-visible contacts/calendars only if ACL can be represented
```

Do not ingest:

```text
- mail
- private user data with unresolved ACL
```

Safe rule:

```text
If owner/share visibility cannot be represented, do not index or return.
```

### NethVoice

Configuration:

```env
NETHVOICE_ENABLED=true
NETHVOICE_INSTANCE=nethvoice1
NETHVOICE_INGEST_PHONEBOOK=true
NETHVOICE_INGEST_TRANSCRIPTIONS=true
NETHVOICE_INGEST_RECORDINGS=false
```

Correct rule:

```text
Do not ingest recordings.
```

Ingest only:

```text
- phonebook contacts
- existing transcriptions
```

Transcriptions are restricted objects.

Visibility mapping must consider:

```text
- extension owner
- call participants
- queue/group membership
- supervisor/admin visibility
```

Safe rule:

```text
If transcription visibility cannot be mapped to user/group principals, do not index it.
```

### Mattermost

Configuration:

```env
MATTERMOST_ENABLED=true
MATTERMOST_INSTANCE=mattermost1
MATTERMOST_INGEST_POSTS=true
MATTERMOST_INGEST_FILES=true
MATTERMOST_INGEST_DIRECT_MESSAGES=false
```

Ingest:

```text
- teams
- channels
- posts
- threads
- attached files
```

Do not ingest in MVP:

```text
- direct messages
- private channels unless membership mapping is exact
```

Required mapping:

```text
Mattermost user email -> LDAP user
channel membership -> principal_ids
team membership -> principal_ids
post/file -> channel_id
```

Must handle:

```text
- edited posts
- deleted posts
- channel membership changes
- file deletion
- private channel membership churn
```

Safe rule:

```text
If channel membership cannot be resolved, do not return the chunk.
```

---

## 17. Parser stack

Default parser:

```text
Tika
```

Optional later:

```text
Docling
Unstructured
OCR
```

MVP parser limits:

```env
PARSER_TIMEOUT_SECONDS=120
PARSER_MAX_FILE_SIZE_MB=100
PARSER_MAX_EXTRACTED_TEXT_MB=20
PARSER_MAX_PAGES=500
PARSER_OCR_ENABLED=false
PARSER_ADVANCED_PDF_ENABLED=false
WORKER_CONCURRENCY=1
```

Parser failure behavior:

```text
- store error in PostgreSQL
- mark object as failed
- continue sync
- do not block entire source ingestion
```

Security rule:

```text
Parser receives file bytes.
Parser does not receive source credentials.
Parser does not mount source credential directories.
```

---

## 18. NS8 UI model

The UI has no custom backend.

Allowed UI operations:

```text
- get-defaults
- get-configuration
- configure-module
- get-sync-status
- start-sync
- regenerate-user-token
```

Forbidden:

```text
- rag-ui-backend container
- custom UI helper backend
- public admin HTTP API
```

UI data comes from:

```text
configure-module input
get-configuration output
get-sync-status output
```

---

## 19. Action contracts

### `configure-module` input

```json
{
  "sync_interval_minutes": 30,
  "embedding_provider": "local",
  "embedding_model": "BAAI/bge-m3",
  "embedding_dimension": 1024,
  "max_file_size_mb": 100,
  "users": [
    {
      "principal_id": "user:openldap1:alice",
      "username": "alice"
    }
  ],
  "regenerate_user_tokens": false,
  "sources": {
    "nextcloud": {
      "enabled": true,
      "instance": "nextcloud2",
      "mode": "groupfolders"
    },
    "samba": {
      "enabled": true,
      "instance": "samba1",
      "shares": ["Company", "Projects"],
      "share_group_map": {
        "Company": ["group:openldap1:employees"],
        "Projects": ["group:openldap1:engineering"]
      }
    },
    "webtop": {
      "enabled": true,
      "instance": "webtop1",
      "contacts": true,
      "calendars": true,
      "mail": false
    },
    "nethvoice": {
      "enabled": true,
      "instance": "nethvoice1",
      "phonebook": true,
      "transcriptions": true,
      "recordings": false
    },
    "mattermost": {
      "enabled": true,
      "instance": "mattermost1",
      "posts": true,
      "files": true,
      "direct_messages": false
    }
  }
}
```

Token behavior:

```text
- if user has no token, generate one
- if user already has token, keep it
- if regenerate_user_tokens=true, revoke and regenerate all configured user tokens
- if a configured user is removed, disable their token
- write clear tokens to %S/state/tokens/users.json
- store token hashes in PostgreSQL
```

### `get-configuration` output

Must include:

```json
{
  "configuration": {
    "internal_url": "http://127.0.0.1:20073/api",
    "same_node_only": true,
    "node_id": "node1",
    "sync_interval_minutes": 30,
    "embedding_provider": "local",
    "embedding_model": "BAAI/bge-m3",
    "embedding_dimension": 1024,
    "max_file_size_mb": 100,
    "users": [
      {
        "principal_id": "user:openldap1:alice",
        "username": "alice"
      }
    ],
    "nextcloud_instance": "nextcloud2",
    "samba_instance": "samba1",
    "webtop_instance": "webtop1",
    "nethvoice_instance": "nethvoice1",
    "mattermost_instance": "mattermost1"
  },
  "available_instances": {
    "nextcloud": ["nextcloud1", "nextcloud2"],
    "samba": ["samba1"],
    "webtop": ["webtop1"],
    "nethvoice": ["nethvoice1"],
    "mattermost": ["mattermost1"]
  },
  "tokens": {
    "generated": true,
    "token_file": "%S/state/tokens/users.json",
    "users": [
      {
        "principal_id": "user:openldap1:alice",
        "username": "alice",
        "has_token": true,
        "last_used_at": "2026-05-12T12:00:00Z",
        "enabled": true
      }
    ]
  },
  "status": {
    "objects": 12500,
    "chunks": 88000,
    "last_sync_at": "2026-05-12T11:00:00Z",
    "errors": 7,
    "index_status": "ready",
    "active_collection": {
      "name": "bge-m3-v1",
      "embedding_model": "BAAI/bge-m3",
      "embedding_dimension": 1024
    }
  }
}
```

Rule:

```text
get-configuration does not return clear tokens.
```

---

## 20. Systemd structure

Files:

```text
imageroot/systemd/user/
  rag.service
  rag-sync.timer
  rag-sync.service
  rag-maintenance.timer
  rag-maintenance.service
```

### `rag.service`

Responsibilities:

```text
- create pod
- start postgres
- wait for postgres
- run migrations
- start qdrant
- wait for qdrant
- start parser
- wait for parser
- start rag-embedder
- wait for rag-embedder
- start rag-api
- start rag-worker
- stop containers in reverse order
```

Startup order:

```text
postgres -> migrations -> qdrant -> parser -> embedder -> rag-api -> rag-worker
```

Shutdown order:

```text
rag-worker -> rag-api -> embedder -> parser -> qdrant -> postgres
```

### Sync scheduling

Do not let both the worker and timer independently schedule sync.

Correct model:

```text
rag-sync.timer
  -> rag-sync.service
    -> start-sync action
      -> INSERT ingest_job

rag-worker
  -> consumes queued ingest_job rows
```

---

## 21. Backup and restore

Qdrant is a cache. PostgreSQL is the truth.

Backup flow:

```text
1. Enter maintenance mode.
2. Pause rag-worker.
3. Reject new write operations.
4. Wait for active ingest job to finish or abort.
5. Dump PostgreSQL with pg_dump/custom format.
6. Optionally create Qdrant snapshot.
7. Back up:
   - %S/state/environment
   - %S/state/secrets.env
   - %S/state/generated.env
   - %S/state/tokens/
   - PostgreSQL dump
   - optional Qdrant snapshot
8. Exit maintenance mode.
9. Restart worker.
```

Restore flow:

```text
1. Stop rag.service.
2. Restore env/secrets/tokens.
3. Restore PostgreSQL dump.
4. Try to restore Qdrant snapshot if available.
5. Run migrations.
6. Validate active vector collection.
7. If Qdrant is missing or inconsistent:
   - keep PostgreSQL
   - mark index_status=rebuild_required
   - enqueue rebuild_vectors
8. Restart rag.service.
```

Rule:

```text
Restore must not fail only because Qdrant restore failed.
```

---

## 22. Container mount rules

```text
rag-api:
  needs DB/Qdrant access and secrets
  does not need source raw credential stores except through controlled env

rag-worker:
  needs source connector credentials
  needs parser/embedder access
  needs DB/Qdrant access

parser:
  receives file bytes
  does not receive source credentials
  does not mount full %S/state

qdrant:
  mounts only %S/state/qdrant

postgres:
  mounts only %S/state/postgresql

embedder:
  mounts only model cache
```

---

## 23. Removed or explicitly out of scope

Removed from MVP:

```text
configure-route
delete-route
create-user-token
revoke-user-token
list-user-tokens
public token API
public admin API
custom UI backend
public Traefik route
cluster-wide RAG routing
recording ingestion from NethVoice
Mattermost direct-message ingestion
WebTop mail ingestion
Nextcloud personal-folder ingestion
```

Token-related actions kept:

```text
get-user-token
regenerate-user-token
```

Reason:

```text
Hermes needs a safe integration path to import one user's token.
The UI/admin may need emergency regeneration if a token leaks.
```

---

## 24. Implementation checklist

Initial MVP order:

```text
1. Create module skeleton from NS8 module conventions.
2. Add image label org.nethserver.tcp-ports-demand = 1.
3. Implement create-module action.
4. Implement environment/secrets/generated file handling.
5. Implement rag.service with one Podman pod.
6. Start PostgreSQL inside the pod.
7. Add migrations.
8. Implement module_state/source/source_object/chunk/token/audit schema.
9. Implement configure-module validation and environment writing.
10. Implement user token generation, hashing and users.json.
11. Implement rag-api /health and /api/status.
12. Implement bearer token validation.
13. Implement POST /api/query with placeholder retrieval.
14. Add Qdrant and vector_collection/chunk_vector logic.
15. Add rag-worker job loop.
16. Add parser integration.
17. Add one source adapter first.
18. Add ACL snapshot logic.
19. Enforce PostgreSQL ACL checks before returning chunks.
20. Add backup/restore.
21. Add UI action wiring.
22. Add tests.
```

Minimum acceptance criteria:

```text
- No public HTTP route is created.
- Only one host port is allocated.
- rag-api binds only to 127.0.0.1:${TCP_PORT} on the host.
- get-configuration reports same_node_only=true.
- PostgreSQL can restore the full state without Qdrant.
- Qdrant can be deleted and rebuilt.
- get-configuration never returns clear tokens.
- get-user-token returns only the requested configured principal token.
- Unknown/stale/unmapped ACL objects are never returned.
- NethVoice recordings are never ingested.
- Parser has no source credentials mounted.
```
