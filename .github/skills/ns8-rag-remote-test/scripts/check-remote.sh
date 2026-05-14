#!/usr/bin/env bash

set -euo pipefail

host="${1:-${RAG_REMOTE_HOST:-root@makako.sf.nethserver.net}}"
module_id="${2:-${RAG_MODULE_ID:-}}"

discover_module_id() {
    ssh "${host}" "api-cli run list-modules" | python3 -c 'import json,sys; data=json.load(sys.stdin); ids=[inst["id"] for app in data if app.get("id")=="ns8-rag" for inst in app.get("installed", [])]; print(ids[-1] if ids else "")'
}

extract_internal_url() {
    python3 -c 'import json,sys; print(json.load(sys.stdin)["configuration"]["internal_url"])'
}

if [[ -z "${module_id}" ]]; then
    module_id="$(discover_module_id)"
fi

if [[ -z "${module_id}" ]]; then
    echo "No installed ns8-rag module found on ${host}" >&2
    exit 1
fi

config_json="$(ssh "${host}" "api-cli run module/${module_id}/get-configuration")"
internal_url="$(printf '%s' "${config_json}" | extract_internal_url)"
health_url="${internal_url%/api}/health"
status_url="${internal_url}/status"

echo "Host: ${host}"
echo "Module: ${module_id}"
echo "Internal URL: ${internal_url}"
echo
echo "[get-configuration]"
printf '%s\n' "${config_json}"
echo
echo "[health]"
ssh "${host}" "curl -fsS '${health_url}'"
echo
echo "[status]"
ssh "${host}" "curl -fsS '${status_url}'"
echo
echo "[rag.service]"
ssh "${host}" "systemctl --user --machine ${module_id}@ status rag.service --no-pager || true"