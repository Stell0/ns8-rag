#!/usr/bin/env bash

set -euo pipefail

host="${1:-${RAG_REMOTE_HOST:-root@makako.sf.nethserver.net}}"
module_id="${2:-${RAG_MODULE_ID:-}}"
principal_id="${3:-${RAG_TEST_PRINCIPAL_ID:-user:openldap1:alice}}"
username="${4:-${RAG_TEST_USERNAME:-alice}}"

discover_module_id() {
    ssh "${host}" "api-cli run list-modules" | python3 -c 'import json,sys; data=json.load(sys.stdin); ids=[inst["id"] for app in data if app.get("id")=="ns8-rag" for inst in app.get("installed", [])]; print(ids[-1] if ids else "")'
}

extract_internal_url() {
    python3 -c 'import json,sys; print(json.load(sys.stdin)["configuration"]["internal_url"])'
}

extract_token() {
    python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])'
}

if [[ -z "${module_id}" ]]; then
    module_id="$(discover_module_id)"
fi

if [[ -z "${module_id}" ]]; then
    echo "No installed ns8-rag module found on ${host}" >&2
    exit 1
fi

configure_payload="$(python3 -c 'import json,sys; print(json.dumps({"users":[{"principal_id":sys.argv[1],"username":sys.argv[2]}]}))' "${principal_id}" "${username}")"
token_payload="$(python3 -c 'import json,sys; print(json.dumps({"principal_id":sys.argv[1]}))' "${principal_id}")"

echo "Host: ${host}"
echo "Module: ${module_id}"
echo "Principal: ${principal_id}"
echo "Username: ${username}"
echo
echo "[configure-module]"
ssh "${host}" "api-cli run module/${module_id}/configure-module --data '${configure_payload}'"

config_json="$(ssh "${host}" "api-cli run module/${module_id}/get-configuration")"
internal_url="$(printf '%s' "${config_json}" | extract_internal_url)"
health_url="${internal_url%/api}/health"
query_url="${internal_url}/query"

echo
echo "[health]"
ssh "${host}" "curl -fsS '${health_url}'"

token_json="$(ssh "${host}" "api-cli run module/${module_id}/get-user-token --data '${token_payload}'")"
token="$(printf '%s' "${token_json}" | extract_token)"

echo
echo "[query] ${query_url}"
ssh "${host}" "curl -fsS -X POST '${query_url}' -H 'Authorization: Bearer ${token}' -H 'Content-Type: application/json' --data '{\"query\":\"company policy\"}'"