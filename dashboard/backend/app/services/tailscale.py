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


def _funnel_status():
    """Return (enabled, published_paths). Funnel exposes serve to the public
    internet, so a running Funnel means share links work off-tailnet."""
    r = run("tailscale", "funnel", "status", timeout=8)
    if not r.ok or not r.output:
        return False, []
    text = r.output
    if "no funnel" in text.lower() or "not enabled" in text.lower():
        return False, []
    # published paths appear as lines like "https://host/ (Funnel on)"
    paths = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("|--"):
            paths.append(line.split("|--", 1)[1].strip())
    return True, paths


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
                "exit_node": bool(peer.get("ExitNode")) or bool(peer.get("ExitNodeOption")),
            }
        )
    peers.sort(key=lambda p: (not p["online"], p["name"]))

    # exit-node advertisement is in Self.ExitNodeOption for Pi 5 / recent tailscale
    exit_node = bool(node.get("ExitNodeOption"))

    funnel_on, funnel_paths = _funnel_status()

    return {
        "available": True,
        "state": data.get("BackendState", "Unknown"),  # Running | Stopped | NeedsLogin
        "hostname": node.get("HostName"),
        "dns_name": dns_name,
        "ips": node.get("TailscaleIPs", []) or [],
        "serving": bool(_serve_url(res)),
        "exit_node": exit_node,
        "funnel": {"enabled": funnel_on, "paths": funnel_paths},
        "peers": peers,
    }


def set_connection(connect: bool) -> CmdResult:
    if connect:
        # Re-establish using the saved login/preferences from first setup.
        return sudo("tailscale", "up", timeout=60)
    return sudo("tailscale", "down", timeout=30)


def set_exit_node(advertise: bool) -> CmdResult:
    """Advertise this node as a tailnet exit node (VPN gateway) or stop."""
    flag = "--advertise-exit-node" if advertise else "--advertise-exit-node=false"
    # `tailscale set` avoids re-negotiating auth (unlike `tailscale up`)
    return sudo("tailscale", "set", flag, timeout=30)


def set_funnel(enabled: bool, path: str = "/s/") -> CmdResult:
    """Expose only the /s/* share path to the public internet via Funnel,
    or tear it down. The admin dashboard stays tailnet-only."""
    if enabled:
        # target: proxy to the local dashboard's public share tree
        return sudo("tailscale", "funnel", "--bg", f"--set-path={path.rstrip('/')}",
                    "http://localhost:80" + path, timeout=30)
    return sudo("tailscale", "funnel", f"--set-path={path.rstrip('/')}", "off", timeout=15)
