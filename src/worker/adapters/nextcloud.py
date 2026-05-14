"""Nextcloud personal-files adapter using WebDAV.

For each configured personal-files user this adapter:
  1. resolves the user's UID (Nextcloud uses UUID storage paths for LDAP users);
  2. walks `<root_path>` under that user's files namespace with PROPFIND;
  3. downloads each file as that same user;
  4. yields (path, etag, size, mtime, content_type, principal_id, bytes).

The adapter authenticates as the same Nextcloud user whose folder is being
indexed, so the worker never holds admin credentials and ACL is implicit:
if WebDAV grants access, that user can read the file.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterator
from urllib.parse import quote, unquote
from xml.etree import ElementTree as ET

import requests
from requests.auth import HTTPBasicAuth


DAV_NS = {"d": "DAV:", "oc": "http://owncloud.org/ns"}
OCS_HDR = {"OCS-APIRequest": "true", "Accept": "application/json"}


@dataclass
class NCFile:
    principal_id: str
    username: str
    uid: str  # storage identifier under /remote.php/dav/files/<uid>/
    path: str  # decoded relative path under the user's root_path
    href: str  # full DAV href (encoded)
    etag: str
    size: int
    mtime: str
    content_type: str


class NextcloudClient:
    def __init__(self, base_url: str, tls_verify: bool = True, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.verify = tls_verify

    def _ocs_user_uid(self, username: str, password: str) -> str:
        """Resolve the storage UID for a user by authenticating as them.

        The /ocs/v1.php/cloud/user endpoint returns the caller's own record,
        whose <id> field is the storage identifier we need under /remote.php/dav/files/.
        """
        url = f"{self.base_url}/ocs/v1.php/cloud/user?format=json"
        resp = self.session.get(
            url, auth=HTTPBasicAuth(username, password), headers=OCS_HDR, timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["ocs"]["data"]["id"]

    def list_folder(
        self, username: str, password: str, uid: str, root_path: str,
    ) -> list[NCFile]:
        principal_id = ""  # filled by caller
        encoded = "/".join(quote(p) for p in root_path.split("/") if p)
        url = f"{self.base_url}/remote.php/dav/files/{quote(uid)}/{encoded}/"
        body = (
            '<?xml version="1.0"?>'
            '<d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">'
            "<d:prop>"
            "<d:getetag/><d:getcontentlength/><d:getlastmodified/>"
            "<d:getcontenttype/><d:resourcetype/>"
            "</d:prop></d:propfind>"
        )
        resp = self.session.request(
            "PROPFIND", url,
            auth=HTTPBasicAuth(username, password),
            headers={"Depth": "infinity", "Content-Type": "application/xml"},
            data=body, timeout=self.timeout,
        )
        resp.raise_for_status()
        return self._parse_propfind(resp.text, uid, root_path, principal_id, username)

    def _parse_propfind(
        self, xml_text: str, uid: str, root_path: str, principal_id: str, username: str,
    ) -> list[NCFile]:
        tree = ET.fromstring(xml_text)
        results: list[NCFile] = []
        base_prefix = f"/remote.php/dav/files/{uid}/"
        for resp in tree.findall("d:response", DAV_NS):
            href_el = resp.find("d:href", DAV_NS)
            if href_el is None or not href_el.text:
                continue
            href = href_el.text
            propstat = resp.find("d:propstat/d:prop", DAV_NS)
            if propstat is None:
                continue
            rtype = propstat.find("d:resourcetype", DAV_NS)
            if rtype is not None and rtype.find("d:collection", DAV_NS) is not None:
                continue  # skip folders
            etag = (propstat.findtext("d:getetag", default="", namespaces=DAV_NS) or "").strip('"')
            size_txt = propstat.findtext("d:getcontentlength", default="0", namespaces=DAV_NS) or "0"
            mtime = propstat.findtext("d:getlastmodified", default="", namespaces=DAV_NS) or ""
            ctype = propstat.findtext("d:getcontenttype", default="", namespaces=DAV_NS) or ""
            decoded_href = unquote(href)
            if not decoded_href.startswith(base_prefix):
                continue
            rel = decoded_href[len(base_prefix):]
            results.append(NCFile(
                principal_id=principal_id, username=username, uid=uid,
                path=rel, href=href, etag=etag,
                size=int(size_txt or 0), mtime=mtime, content_type=ctype,
            ))
        return results

    def download(self, username: str, password: str, href: str) -> bytes:
        url = f"{self.base_url}{href}" if href.startswith("/") else href
        resp = self.session.get(
            url, auth=HTTPBasicAuth(username, password), timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.content


def iter_personal_files(
    users: list[dict], passwords: dict, client: NextcloudClient,
) -> Iterator[NCFile]:
    """Yield NCFile entries for every configured personal root.

    Skips users whose password is not in `passwords` or whose UID cannot be resolved.
    """
    max_mb = int(os.environ.get("MAX_FILE_SIZE_MB", "100"))
    max_bytes = max_mb * 1024 * 1024
    for u in users:
        password = passwords.get(u["username"])
        if not password:
            print(f"[nextcloud] no password for {u['username']}, skipping", flush=True)
            continue
        try:
            uid = client._ocs_user_uid(u["username"], password)
        except Exception as exc:  # noqa: BLE001
            print(f"[nextcloud] cannot resolve uid for {u['username']}: {exc}", flush=True)
            continue
        try:
            entries = client.list_folder(u["username"], password, uid, u["root_path"])
        except Exception as exc:  # noqa: BLE001
            print(f"[nextcloud] propfind failed for {u['username']}: {exc}", flush=True)
            continue
        for entry in entries:
            entry.principal_id = u["principal_id"]
            if entry.size > max_bytes:
                continue
            yield entry
