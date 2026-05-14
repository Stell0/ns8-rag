# ns8-rag

`ns8-rag` is a NethServer 8 module that indexes selected company data sources and exposes an internal-only Retrieval-Augmented Generation API for same-node consumers such as Hermes.

It is designed for private, ACL-aware grounding of AI assistant queries.

---

## What it does

`ns8-rag` ingests supported business sources, extracts text, chunks content, embeds chunks, stores metadata and ACLs, and exposes a query API that returns only content the requesting user is allowed to see.

Supported source families:

```text
- Nextcloud: group/shared folders with safe ACL mapping
- Samba: explicit share -> LDAP group mapping
- WebTop: contacts and calendars
- NethVoice: phonebook and existing transcriptions
- Mattermost: posts and files with resolved membership ACLs
```

NethVoice recordings are not ingested.

---

## Architecture summary

Runtime shape:

```text
ns8-rag
  ├── one Podman pod: rag-pod
  │   ├── rag-api
  │   ├── rag-worker
  │   ├── rag-embedder
  │   ├── postgres
  │   ├── qdrant
  │   └── parser
  ├── NS8 actions
  ├── NS8 environment files
  ├── generated user token file
  └── NS8 UI with no custom backend
```

Core model:

```text
PostgreSQL = authoritative state, metadata, chunks, ACLs, tokens, audit
Qdrant     = disposable vector cache
NS8 actions = admin backend
rag-api    = internal-only query API
```

---

## Exposure model

There is no public HTTP route.

There is no Traefik route.

There is no public firewall opening.

Only `rag-api` is bound on host loopback:

```bash
127.0.0.1:${TCP_PORT}:8080
```

Consumers use:

```env
NS8_RAG_URL=http://127.0.0.1:${TCP_PORT}/api
```

MVP limitation:

```text
127.0.0.1 means same node only.
```

---

## Security model

Hard rules:

```text
- Unknown ACL means deny.
- Stale ACL means deny.
- Qdrant is not trusted for authorization.
- PostgreSQL ACL check is mandatory before returning chunks.
- Source credentials stay inside ns8-rag.
- Hermes receives only a user RAG token.
- Hermes does not receive source credentials.
- Clear tokens are stored only in %S/state/tokens/users.json.
- PostgreSQL stores token hashes only.
- Authorization headers are never logged.
```

---

## Hermes integration

`ns8-rag` does not generate Hermes-specific files.

It exposes the NS8 action:

```text
get-user-token
```

Hermes imports one selected user token, writes its own local configuration, and calls:

```text
POST /api/query
```

This model is safe only when the Hermes instance/profile is bound to one user.

A shared multi-user Hermes gateway must not use one shared RAG token.

---

## Configuration

Main state files:

```text
%S/state/environment
%S/state/secrets.env
%S/state/tokens/users.json
```

`environment` contains admin-controlled settings, such as sync interval, embedding model, parser limits and enabled source instances.

`secrets.env` contains module secrets and database credentials.

`tokens/users.json` contains clear per-user RAG tokens and must be protected with `0600` permissions.

---

## NS8 actions

Administrative operations are implemented through NS8 actions.

Important actions:

```text
create-module
configure-module
get-configuration
get-defaults
start-sync
get-sync-status
get-user-token
regenerate-user-token
backup-module
restore-module
destroy-module
```

The UI talks only to these actions.

There is no custom UI backend and no public admin HTTP API.

---

## API

Only `rag-api` exposes HTTP, and only internally.

Endpoints:

```text
POST /api/query
GET  /api/status
GET  /health
```

There is no public token API and no public source-management API.

Example query response:

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

## Sync model

Sync is timer-driven and job-based.

```text
rag-sync.timer
  -> rag-sync.service
    -> start-sync action
      -> INSERT ingest_job

rag-worker
  -> consumes queued ingest_job rows
```

The worker consumes queued jobs. It must not independently schedule periodic syncs if the timer already does.

---

## Backup and restore

PostgreSQL is the authoritative backup target.

Qdrant is optional and rebuildable.

Backup includes:

```text
- %S/state/environment
- %S/state/secrets.env
- %S/state/tokens/
- PostgreSQL dump
- optional Qdrant snapshot
```

Restore must not fail only because Qdrant restore failed. If Qdrant is missing or inconsistent, the module must mark the index as `rebuild_required` and enqueue `rebuild_vectors`.

---

## Documentation

Repository documentation:

```text
README.md     human overview
AGENTS.md     short guide for coding agents
STRUCTURE.md  authoritative architecture and implementation structure
```

For implementation details, start from [`STRUCTURE.md`](./STRUCTURE.md).

---

## Nextcloud adapter

`ns8-rag` ships a Nextcloud adapter that ingests files from a per-user folder
("personal files" mode). The worker authenticates against Nextcloud as each
configured user, walks one root path under their personal storage, downloads
new/updated files, parses them with Apache Tika, chunks the text, embeds the
chunks with `BAAI/bge-m3`, and writes:

- one `source_object` row per file (Postgres)
- one `source_acl` row per file pinned to the user's `principal_id`
- one or more `chunk` + `chunk_vector` rows (Postgres)
- the corresponding points in Qdrant (`principal_ids` payload used as a
  retrieval prefilter; Postgres ACL is the authoritative check)

### Ingesting Nextcloud files

1. Choose a Nextcloud instance reachable from the rag-pod, e.g.
   `https://nextcloud.example.org`.
2. In Nextcloud, create the per-user folder you want to expose to RAG, e.g.
   `nethvoice-docs`, and put the files inside it.
3. For every user you want to index, collect:
   - `principal_id` — the NS8 principal id (e.g. `user:openldap1:alice`)
   - `username` — the Nextcloud login name
   - `root_path` — folder under the user's personal storage (no leading `/`)
   - `password` — the Nextcloud password used for WebDAV/OCS authentication
     (an app password is recommended)
4. Call `configure-module` with a payload like:

   ```json
   {
     "users": [
       {"principal_id": "user:openldap1:alice", "username": "alice"}
     ],
     "sources": {
       "nextcloud": {
         "enabled": true,
         "instance": "nextcloud1",
         "mode": "personal_files",
         "base_url": "https://nextcloud.example.org",
         "tls_verify": true,
         "users": [
           {
             "principal_id": "user:openldap1:alice",
             "username": "alice",
             "root_path": "nethvoice-docs",
             "password": "<app-password>"
           }
         ]
       }
     }
   }
   ```

   Run from the leader node:

   ```bash
   cat payload.json | api-cli run module/<module_id>/configure-module --data -
   ```

   `configure-module` writes Nextcloud public settings to `state/environment`
   (`NEXTCLOUD_ENABLED`, `NEXTCLOUD_BASE_URL`, `NEXTCLOUD_USERS_JSON`, …) and
   stores per-user passwords in `state/secrets.env` as
   `NEXTCLOUD_USER_PASSWORDS_JSON` (mode `0600`, never logged, never returned
   by `get-configuration`).

5. Launch an ingestion run:

   ```bash
   echo '{}' | api-cli run module/<module_id>/start-sync --data -
   ```

   The action returns a queued `ingest_job`. The worker picks it up within a
   few seconds, walks each user's `root_path` via WebDAV, and pushes parsed
   chunks through the embedder and Qdrant.

### Testing the ingestion

Verify Postgres state on the leader node:

```bash
runagent -m <module_id> podman exec <module_id>-postgres \
  psql -U rag -d rag -c "SELECT status, error FROM ingest_job ORDER BY created_at DESC LIMIT 5"

runagent -m <module_id> podman exec <module_id>-postgres \
  psql -U rag -d rag -c "SELECT title, uri FROM source_object ORDER BY title"

runagent -m <module_id> podman exec <module_id>-postgres \
  psql -U rag -d rag -c "SELECT COUNT(*) FROM chunk; SELECT COUNT(*) FROM source_acl"
```

You should see one `source_object` per file under the configured `root_path`,
one `source_acl` row per file pinned to the owner's `principal_id`, and one
or more chunks per object.

Retrieve the user's RAG token and run a query:

```bash
echo '{"principal_id":"user:openldap1:alice"}' \
  | api-cli run module/<module_id>/get-user-token --data -

curl -sS -X POST \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  http://127.0.0.1:<TCP_PORT>/api/query \
  -d '{"query":"Provisioning Methods"}'
```

A successful end-to-end smoke test for the bundled `nethvoice-docs` fixture
returns the `provisioning.md` chunk as the top hit and the content contains
`"RPS, DHCP, and manual provisioning URLs"`.

### Troubleshooting

- `ingest_job.error` containing `Connection refused` on port `8090` means the
  embedder container is not ready yet (first `BAAI/bge-m3` load takes a few
  minutes on a cold start). Re-run `start-sync` after `GET /health` on the
  embedder returns `{"model_loaded":true}`.
- `ingest_job.error` containing `SSL` errors against `127.0.0.1` is a Qdrant
  client misconfiguration. The bundled `qdrant_ops.client()` pins
  `https=False` so the HTTP REST API is used even when `QDRANT_API_KEY` is
  set.
- `ingest_job.error` containing `Connection refused` against the Nextcloud
  hostname from inside the pod means rootless networking cannot reach the
  host. The pod is created with
  `--network slirp4netns:allow_host_loopback=true`, which lets containers
  reach services that the host can reach. Verify with:

  ```bash
  runagent -m <module_id> podman exec <module_id>-rag-worker \
    python -c "import requests; print(requests.get('https://<nextcloud-host>/status.php', timeout=10).status_code)"
  ```

- `sync done: objects=0 chunks=0` with no Nextcloud rows usually means
  `NEXTCLOUD_ENABLED=false` or `NEXTCLOUD_USERS_JSON=[]` in
  `state/environment`. Re-run `configure-module` with the payload above and
  restart the worker:

  ```bash
  runagent -m <module_id> podman restart <module_id>-rag-worker
  ```

- The Tika container needs ~700 MB of RAM and the embedder needs ~2 GB. On
---
