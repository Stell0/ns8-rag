# Remote Troubleshooting

Use these checks when the remote instance fails before the HTTP smoke test works.

## Install Failure

Find the `ns8-rag` task context in Redis:

```bash
ssh root@makako.sf.nethserver.net "for k in \$(redis-cli --scan --pattern 'task/*/context'); do v=\$(redis-cli get \"\$k\" 2>/dev/null || true); if printf '%s' \"\$v\" | grep -q 'ns8-rag'; then echo KEY:\$k; echo \"\$v\"; echo; fi; done"
```

Inspect the module user service:

```bash
ssh root@makako.sf.nethserver.net "systemctl --user --machine ns8-rag4@ status rag.service --no-pager || true"
```

## Rootless Images

- Rootless `create-module/05pullimages` only sees images in the module user's Podman store.
- Loading images into root's store is not enough for custom local builds.
- On makako, loading one multi-image archive collapsed the `ns8-rag-*` tags to the main image ID.
- Loading `ns8-rag-api`, `ns8-rag-worker`, and `ns8-rag-embedder` as separate archives preserved distinct image IDs.

## Environment Survival

- `state/environment` must retain `NS8_RAG_API_IMAGE`, `NS8_RAG_WORKER_IMAGE`, `NS8_RAG_EMBEDDER_IMAGE`, and `TCP_PORT` after `configure-module`.
- `generated.env` should keep `RAG_MODULE_ID` aligned with the installed module id so container names match the instance.

## Cleanup Verification

```bash
ssh root@makako.sf.nethserver.net "remove-module --no-preserve ns8-rag4"
ssh root@makako.sf.nethserver.net "api-cli run list-modules | grep ns8-rag4 || true"
ssh root@makako.sf.nethserver.net "id ns8-rag4 || true"
ssh root@makako.sf.nethserver.net "test -d /home/ns8-rag4 && echo HOME_EXISTS || echo HOME_GONE"
```