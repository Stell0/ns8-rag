---
name: ns8-rag-remote-test
description: 'Test ns8-rag on a remote NS8 host over SSH. Use for makako remote deployment checks, add-module verification, rag.service status, get-configuration, health/status checks, token retrieval, authenticated query smoke tests, remove-module cleanup, and remote install failure diagnosis.'
argument-hint: '[host] [module-id]'
user-invocable: true
---

# ns8-rag Remote Test

Use this skill when you need to verify ns8-rag on a remote NS8 node such as `root@makako.sf.nethserver.net`.

## When to Use

- Verify a fresh remote install after `add-module`
- Run a read-only remote health check on an existing module
- Run a functional smoke test that configures a test user, retrieves a token, and sends an authenticated query
- Diagnose remote install failures around `create-module`, `rag.service`, or rootless image loading
- Confirm cleanup after `remove-module --no-preserve`

## Defaults

- Default host: `root@makako.sf.nethserver.net`
- Default module discovery: latest installed `ns8-rag` instance from `api-cli run list-modules`
- Default smoke-test user: `user:openldap1:alice` / `alice`

## Procedure

1. For a read-only verification, run [check-remote.sh](./scripts/check-remote.sh).
2. For a full functional smoke test that may update module configuration, run [smoke-query.sh](./scripts/smoke-query.sh).
3. If the install is broken before the module becomes usable, use [troubleshooting.md](./references/troubleshooting.md) to inspect task context, `rag.service`, and rootless image state.

## Command Patterns

Read-only check:

```bash
bash .github/skills/ns8-rag-remote-test/scripts/check-remote.sh
bash .github/skills/ns8-rag-remote-test/scripts/check-remote.sh root@makako.sf.nethserver.net ns8-rag4
```

Functional smoke test:

```bash
bash .github/skills/ns8-rag-remote-test/scripts/smoke-query.sh
bash .github/skills/ns8-rag-remote-test/scripts/smoke-query.sh root@makako.sf.nethserver.net ns8-rag4
```

## Notes

- The smoke test calls `configure-module`, so it can restart `rag.service` and mutate the configured user list.
- Remote dev installs on makako have required loading custom runtime images into the module user's rootless Podman store, not only root's store.
- `org.nethserver.images` entries must always include a tag or digest.