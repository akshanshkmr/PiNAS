"""Tailscale status and connect/disconnect."""

import json

from .shell import CmdResult, run, sudo


def _status_json():
    # `tailscale status` works for a non-root user on most setups; fall back to
    # sudo where the socket is root-only.
    res = run("tailscale", "status", "--json", timeout=15)
    if not res.ok:
        res = sudo("tailscale", "status", "--json", timeout=15)
    return res


def _serve_url(res):
    res_json = run("tailscale", "serve", "status", timeout=10)
    if not res_json.ok or not res_json.output or "no serve config" in res_json.output.lower():
        return None
    return True  # serving something; URL is derived from the node's DNS name


def status():
    res = _status_json()
    if not res.ok:
        return {"available": False, "error": res.error or "tailscale is not installed or reachable"}
    try:
        data = json.loads(res.output)
    except json.JSONDecodeError:
        return {"available": False, "error": "unreadable tailscale output"}

    node = data.get("Self", {}) or {}
    dns_name = (node.get("DNSName") or "").rstrip(".")
    peers = []
    for peer in (data.get("Peer") or {}).values():
        peers.append(
            {
                "name": (peer.get("DNSName") or peer.get("HostName") or "").rstrip("."),
                "hostname": peer.get("HostName"),
                "os": peer.get("OS"),
                "online": bool(peer.get("Online")),
                "ip": (peer.get("TailscaleIPs") or [None])[0],
            }
        )
    peers.sort(key=lambda p: (not p["online"], p["name"]))

    return {
        "available": True,
        "state": data.get("BackendState", "Unknown"),  # Running | Stopped | NeedsLogin
        "hostname": node.get("HostName"),
        "dns_name": dns_name,
        "ips": node.get("TailscaleIPs", []) or [],
        "serving": bool(_serve_url(res)),
        "peers": peers,
    }


def set_connection(connect: bool) -> CmdResult:
    if connect:
        # Re-establish using the saved login/preferences from first setup.
        return sudo("tailscale", "up", timeout=60)
    return sudo("tailscale", "down", timeout=30)
