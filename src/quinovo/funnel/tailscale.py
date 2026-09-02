"""Pack connectors. Homelab Tailscale reads a fixture in CI, never the live tailnet."""

from __future__ import annotations

import json
from pathlib import Path

from quinovo.engine.store import ObjectStore


def ingest_tailscale_fixture(store: ObjectStore, path: str | Path) -> int:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    peers = data.get("Peer") or data.get("peers") or []
    if isinstance(peers, dict):
        peers = list(peers.values())
    count = 0
    self_node = data.get("Self")
    if isinstance(self_node, dict):
        peers = [self_node, *peers]
    for peer in peers:
        if not isinstance(peer, dict):
            continue
        node_id = str(peer.get("ID") or peer.get("id") or "")
        if not node_id:
            continue
        hostname = str(peer.get("HostName") or peer.get("hostname") or node_id)
        online = bool(peer.get("Online", peer.get("online", False)))
        os_name = str(peer.get("OS") or peer.get("os") or "unknown")
        device_class = str(peer.get("class") or "unknown")
        store.upsert_object(
            "Device",
            {
                "id": node_id,
                "hostname": hostname,
                "os": os_name,
                "presence": "online" if online else "offline",
                "class": device_class,
                "status": "open",
            },
        )
        count += 1
    return count
