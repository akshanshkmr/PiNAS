"""Tailscale status and connect/serve/exit-node control.

There is intentionally no Funnel (public-internet) exposure here — it
was removed after we found `tailscale funnel --set-path=/s/` doesn't
actually scope AllowFunnel per path, and any unauthenticated public
surface on a home server is a bad trade. Sharing over the tailnet uses
the regular authenticated Files tab.
"""

import json
import subprocess
import time

from .shell import CmdResult, run, sudo


# The admin dashboard is served on 8443 (never 443) so an old install that
# still has AllowFunnel on port 443 for any reason can't leak the admin UI.
ADMIN_PORT = 8443


def _status_json():
    # `tailscale status` works for a non-root user on most setups; fall back
    # to sudo where the socket is root-only.
    res = run("tailscale", "status", "--json", timeout=15)
    if not res.ok:
        res = sudo("tailscale", "status", "--json", timeout=15)
    return res


def _serve_config() -> dict:
    r = run("tailscale", "serve", "status", "--json", timeout=10)
    if not r.ok:
        r = sudo("tailscale", "serve", "status", "--json", timeout=10)
    if not r.ok or not r.output:
        return {}
    try:
        return json.loads(r.output) or {}
    except json.JSONDecodeError:
        return {}


def _admin_serving(cfg: dict | None = None) -> bool:
    """True when there's a handler at `/` on the admin port."""
    cfg = _serve_config() if cfg is None else cfg
    for host_port, web in (cfg.get("Web") or {}).items():
        try:
            port = int(host_port.rsplit(":", 1)[1])
        except (ValueError, IndexError):
            continue
        if port == ADMIN_PORT and "/" in (web.get("Handlers") or {}):
            return True
    return False


def _funnel_exposed(cfg: dict | None = None) -> bool:
    """True if any host:port has AllowFunnel — used to warn on old installs."""
    cfg = _serve_config() if cfg is None else cfg
    allow = cfg.get("AllowFunnel") or {}
    return any(bool(v) for v in allow.values())


def _exit_node_advertised() -> bool:
    """Read `tailscale debug prefs` and check whether the node has 0.0.0.0/0
    (or ::/0) in AdvertiseRoutes — that's what --advertise-exit-node actually
    sets. `Self.ExitNodeOption` from `tailscale status` only becomes true
    after the tailnet admin console approves the node."""
    r = sudo("tailscale", "debug", "prefs", timeout=8)
    if not r.ok or not r.output:
        return False
    try:
        prefs = json.loads(r.output)
    except json.JSONDecodeError:
        return False
    routes = prefs.get("AdvertiseRoutes") or []
    return "0.0.0.0/0" in routes or "::/0" in routes


def _off_ok(res: CmdResult) -> bool:
    """Tailscale returns nonzero when we ask it to remove a handler that
    isn't there — that's the state we're trying to reach anyway."""
    err = (res.error or res.output or "").lower()
    return "does not exist" in err or "no such" in err or "no funnel" in err


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

    exit_node = _exit_node_advertised()
    exit_node_approved = bool(node.get("ExitNodeOption"))

    cfg = _serve_config()
    serving = _admin_serving(cfg)
    admin_url = f"https://{dns_name}:{ADMIN_PORT}/" if (dns_name and serving) else None

    return {
        "available": True,
        "state": data.get("BackendState", "Unknown"),  # Running | Stopped | NeedsLogin
        "hostname": node.get("HostName"),
        "dns_name": dns_name,
        "ips": node.get("TailscaleIPs", []) or [],
        "serving": serving,
        "admin_url": admin_url,
        "admin_port": ADMIN_PORT,
        "exit_node": exit_node,
        "exit_node_approved": exit_node_approved,
        # Surfaced only as a warning if an old install still has Funnel on
        # somewhere — there's no toggle to turn it back on from the UI.
        "funnel_exposed": _funnel_exposed(cfg),
        "peers": peers,
    }


def set_connection(connect: bool) -> CmdResult:
    if connect:
        return sudo("tailscale", "up", timeout=60)
    return sudo("tailscale", "down", timeout=30)


def start_login(timeout_s: float = 15.0) -> tuple[str | None, str | None]:
    """Trigger an interactive login and return the auth URL to show the user.

    `tailscale up` blocks until the browser flow completes, so we detach it
    and poll status until `AuthURL` is populated (or the node comes up on
    its own if it was already logged in but stopped). Returns (url, error).
    """
    res = _status_json()
    if res.ok:
        try:
            data = json.loads(res.output)
        except json.JSONDecodeError:
            data = {}
        if data.get("AuthURL"):
            return data["AuthURL"], None
        if data.get("BackendState") == "Running":
            return None, None

    try:
        subprocess.Popen(
            ["sudo", "-n", "tailscale", "up"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as e:
        return None, str(e)

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        time.sleep(0.4)
        res = _status_json()
        if not res.ok:
            continue
        try:
            data = json.loads(res.output)
        except json.JSONDecodeError:
            continue
        if data.get("AuthURL"):
            return data["AuthURL"], None
        if data.get("BackendState") == "Running":
            return None, None
    return None, "Timed out waiting for an auth URL. Try again in a moment."


def set_serve(enabled: bool) -> CmdResult:
    """Publish the admin dashboard at https://<host>.ts.net:8443/ (tailnet
    only). Also aggressively tears down anything on port 443 so an older
    install with a Serve or Funnel handler there can't stay exposed."""
    # Clear any legacy port-443 handlers — with the share feature gone, we
    # never want anything served or funnel'd on 443 by this backend.
    sudo("tailscale", "serve",  "--https=443", "--set-path=/", "off", timeout=15)
    sudo("tailscale", "serve",  "--https=443", "off", timeout=15)
    sudo("tailscale", "funnel", "--https=443", "off", timeout=15)

    if enabled:
        return sudo("tailscale", "serve",
                    f"--https={ADMIN_PORT}", "--bg",
                    "http://localhost:80", timeout=20)
    res = sudo("tailscale", "serve",
               f"--https={ADMIN_PORT}", "--set-path=/", "off", timeout=15)
    if res.ok or _off_ok(res):
        return CmdResult(True, output="Dashboard is no longer served over Tailscale HTTPS.")
    fallback = sudo("tailscale", "serve", f"--https={ADMIN_PORT}", "off", timeout=15)
    if fallback.ok or _off_ok(fallback):
        return CmdResult(True, output="Dashboard is no longer served over Tailscale HTTPS.")
    return res


def set_exit_node(advertise: bool) -> CmdResult:
    """Advertise this node as a tailnet exit node (VPN gateway) or stop."""
    flag = "--advertise-exit-node" if advertise else "--advertise-exit-node=false"
    return sudo("tailscale", "set", flag, timeout=30)
