# AGENTS.md

# ns8-rag Agent Guide

This file is the short operating guide for coding agents working on `ns8-rag`.

Read [`STRUCTURE.md`](./STRUCTURE.md) before changing architecture, runtime layout, security behavior, token handling, source adapters, database schema, backup/restore, systemd units, or NS8 actions.

`STRUCTURE.md` is the authoritative technical contract for this module.

Read [`NS_RESOURCE_MAP.md`](./NS_RESOURCE_MAP.md) for information on where to find NethServer 8 documentation and resources related to module development.

---

## Mission

`ns8-rag` is a NethServer 8 module that indexes selected data sources and exposes an internal-only, ACL-enforced RAG API for same-node consumers such as Hermes.

The module provides:

```text
- one Podman pod
- internal rag-api
- ingestion worker
- local embedder
- PostgreSQL state database
- disposable Qdrant vector index
- parser service
- NS8 actions as admin backend
- NS8 UI without custom backend
- generated per-user RAG tokens
```

---

## Non-negotiable rules

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

# Agent Coding Rules

## Think before coding
Do not make silent assumptions. State assumptions explicitly. If the task is ambiguous, surface the ambiguity. If multiple interpretations exist, present them. If a simpler approach exists, say so. If confused, stop and ask.

## Simplicity first
Write the minimum code that solves the requested problem. Do not add features, abstractions, configurability, or defensive handling that was not requested. If the solution is larger than necessary, simplify it.

## Surgical changes
Touch only the files and lines required for the task. Do not refactor unrelated code. Do not reformat or “improve” adjacent code. Match the existing style. Remove only unused code introduced by your own change.

## Goal-driven execution
Translate the task into verifiable success criteria. Prefer tests or concrete commands. For bugs, reproduce first, then fix. For multi-step tasks, write a short plan where each step has a verification check.

---

## Security invariants

Always preserve these behaviors:

```text
- No public Traefik route.
- No Let's Encrypt route.
- No public firewall opening.
- Only rag-api is exposed, and only on 127.0.0.1:${TCP_PORT}:8080.
- PostgreSQL is never exposed.
- Qdrant is never exposed.
- Parser is never exposed.
- Worker is never exposed.
- Embedder is never exposed.
- Source credentials stay inside ns8-rag.
- Hermes receives only a user RAG token.
- Hermes never receives downstream source credentials.
- Clear RAG tokens exist only in %S/state/tokens/users.json.
- PostgreSQL stores token hashes only.
- Qdrant is never trusted for ACL decisions.
- Parser receives file bytes only.
- Parser does not mount source credentials.
- Authorization headers are never logged.
```

---

## Runtime shape

```text
pod: rag-pod

containers:
  rag-api
  rag-worker
  rag-embedder
  postgres
  qdrant
  parser
```

Same-pod communication uses loopback:

```text
postgres: 127.0.0.1:5432
qdrant:   127.0.0.1:6333
parser:   127.0.0.1:9998
embedder: 127.0.0.1:8090
rag-api:  127.0.0.1:8080
```

Do not assume container hostnames resolve inside the pod.

---

## NS8 exposure model

Use one TCP port only.

Required image label:

```ini
org.nethserver.tcp-ports-demand = 1
```

Allowed host binding:

```bash
-p 127.0.0.1:${TCP_PORT}:8080
```

Internal consumer URL:

```env
NS8_RAG_URL=http://127.0.0.1:${TCP_PORT}/api
```

`127.0.0.1` means same node only.

`get-configuration` must always disclose:

```json
{
  "internal_url": "http://127.0.0.1:20073/api",
  "same_node_only": true,
  "node_id": "node1"
}
```

---

## Configuration files

Use these files:

```text
%S/state/environment
%S/state/secrets.env
%S/state/generated.env
%S/state/tokens/users.json
```

Meaning:

```text
environment   = admin-controlled configuration
secrets.env   = module secrets and database credentials
generated.env = generated runtime metadata
tokens/       = clear generated user token file
```

Do not store clear tokens in PostgreSQL.

Do not return clear tokens from `get-configuration`.

Do not generate `hermes.env`.

---

## Token model

Token format:

```text
rag_ut_<token_id>_<secret>
```

Validation:

```text
1. Parse token_id and secret.
2. Lookup user_token.id in PostgreSQL.
3. Compute HMAC-SHA256(RAG_TOKEN_PEPPER, token_id || "." || secret).
4. Constant-time compare.
5. Check enabled=true.
6. Check revoked_at IS NULL.
7. Resolve principal_id and groups.
8. Apply PostgreSQL ACL checks.
```

Allowed token actions:

```text
get-user-token
regenerate-user-token
```

Removed or forbidden in MVP:

```text
create-user-token
revoke-user-token
list-user-tokens
public token API
public admin API
```

---

## API surface

Only these endpoints exist:

```text
POST /api/query
GET  /api/status
GET  /health
```

Do not add public admin endpoints.

Do not add `/api/tokens`.

Do not add `/api/sources`.

---

## Query authorization rule

Qdrant filters are optimization only.

Required query flow:

```text
1. Validate bearer token.
2. Resolve user principal and group principals.
3. Embed query.
4. Search Qdrant active collection.
5. Overfetch candidates.
6. Recheck every candidate in PostgreSQL.
7. Reject unknown/stale/failed/unmapped ACLs.
8. Load chunk text from PostgreSQL.
9. Return only authorized chunks.
10. Write audit log.
```

Hard rule:

```text
Never return chunk content based only on Qdrant payload.
```

---

## Source adapter rules

MVP supports one active instance per source type.

### Nextcloud

Allowed:

```text
- group folders
- explicitly supported shared folders
- safely mapped LDAP user/group ACLs
```

Forbidden:

```text
- raw filesystem ingestion from Nextcloud storage
- personal folders
- public links
- unresolved external storage permissions
- unmapped share recipients
```

### Samba

MVP ACL model:

```text
share -> allowed LDAP groups
```

File-level ACLs are ignored in MVP. Be explicit about this limitation.

### WebTop

Allowed:

```text
- shared contacts
- shared calendars
```

Forbidden in MVP:

```text
- mail
- private user data with unresolved ACL
```

### NethVoice

Allowed:

```text
- phonebook contacts
- existing transcriptions
```

Forbidden:

```text
- recordings
```

Do not ingest recordings.

### Mattermost

Allowed:

```text
- teams
- channels
- posts
- threads
- attached files
```

Forbidden in MVP:

```text
- direct messages
- private channels unless membership mapping is exact
```

---

## Actions are the admin backend

UI and operators must use NS8 actions.

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

Do not add a custom UI backend.

Do not add public HTTP admin APIs.

---

## Systemd and scheduling

Main service:

```text
rag.service
```

Startup order:

```text
postgres -> migrations -> qdrant -> parser -> embedder -> rag-api -> rag-worker
```

Shutdown order:

```text
rag-worker -> rag-api -> embedder -> parser -> qdrant -> postgres
```

Sync scheduling:

```text
rag-sync.timer
  -> rag-sync.service
    -> start-sync action
      -> INSERT ingest_job

rag-worker
  -> consumes queued ingest_job rows
```

Do not let both the worker and timer independently schedule sync.

---

## Backup and restore

Backup PostgreSQL as authoritative state.

Qdrant snapshot is optional.

Restore must not fail only because Qdrant restore failed.

If Qdrant is missing or inconsistent after restore:

```text
- keep PostgreSQL
- mark index_status=rebuild_required
- enqueue rebuild_vectors
```

---

## Before changing code

Check the relevant section in [`STRUCTURE.md`](./STRUCTURE.md):

| Change type | Read first |
|---|---|
| Runtime containers | Runtime architecture, Pod networking, Systemd structure |
| Ports/exposure | Host exposure, Port allocation |
| Actions | Action contracts |
| UI | NS8 UI model |
| Tokens | Token files, API authentication model, Hermes integration |
| DB schema | Database role, Database schema |
| Retrieval | Query flow, Qdrant role |
| Sources | Source adapters |
| Parser | Parser stack |
| Backup/restore | Backup and restore |
| Security | Hard architecture rules, Security invariants |

---

## Acceptance checklist for changes

A change is not acceptable if it breaks any of these:

```text
- No public route is created.
- Only one NS8 TCP port is requested.
- Host binding remains 127.0.0.1:${TCP_PORT}:8080.
- get-configuration does not return clear tokens.
- get-user-token returns only one existing configured user token.
- PostgreSQL stores token hashes only.
- Qdrant can be deleted and rebuilt.
- PostgreSQL ACL check is mandatory before returning chunks.
- Unknown ACL means deny.
- Stale ACL means deny.
- NethVoice recordings are not ingested.
- Parser has no source credentials.
- UI talks only to NS8 actions.
- Admin/config does not move to public HTTP APIs.
```
