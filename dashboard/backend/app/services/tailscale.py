"""Tailscale status and connect/disconnect."""

import json
import subprocess
import time

from .shell import CmdResult, run, sudo


def _status_json():
    # `tailscale status` works for a non-root user on most setups; fall back to
    # sudo where the socket is root-only.
    res = run("tailscale", "status", "--json", timeout=15)
    if not res.ok:
        res = sudo("tailscale", "status", "--json", timeout=15)
    return res


# Tailscale's Funnel exposure is per-host:port, not per-path — enabling
# Funnel on `<host>:443` for `/s/*` also exposes any Serve handler sharing
# that port. So we host the admin dashboard on a Funnel-safe port (never
# AllowFunnel'd) and keep public /s/ on 443.
ADMIN_PORT = 8443
FUNNEL_PORT = 443


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
    """True when there is a handler at `/` on the admin port — the shape
    Serve creates for the dashboard."""
    cfg = _serve_config() if cfg is None else cfg
    for host_port, web in (cfg.get("Web") or {}).items():
        try:
            port = int(host_port.rsplit(":", 1)[1])
        except (ValueError, IndexError):
            continue
        if port == ADMIN_PORT and "/" in (web.get("Handlers") or {}):
            return True
    return False


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


def _funnel_status(cfg: dict | None = None):
    """Return (enabled, published_paths). We derive both from
    `tailscale serve status --json` — the pretty-printed CLI has changed
    phrasing over versions and its non-sudo socket often fails silently."""
    cfg = _serve_config() if cfg is None else cfg
    allow = cfg.get("AllowFunnel") or {}
    enabled = any(bool(v) for v in allow.values())
    if not enabled:
        return False, []

    paths: list[str] = []
    for host_port, web in (cfg.get("Web") or {}).items():
        if not allow.get(host_port):
            continue
        host = host_port.rsplit(":", 1)[0]
        for path in (web.get("Handlers") or {}).keys():
            paths.append(f"https://{host}{path}")
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

    # advertisement state is the source of truth; ExitNodeOption only becomes
    # true after the tailnet admin console approves the node.
    exit_node = _exit_node_advertised()
    exit_node_approved = bool(node.get("ExitNodeOption"))

    cfg = _serve_config()
    funnel_on, funnel_paths = _funnel_status(cfg)
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
        "funnel": {"enabled": funnel_on, "paths": funnel_paths},
        "peers": peers,
    }


def set_connection(connect: bool) -> CmdResult:
    if connect:
        # Re-establish using the saved login/preferences from first setup.
        return sudo("tailscale", "up", timeout=60)
    return sudo("tailscale", "down", timeout=30)


def start_login(timeout_s: float = 15.0) -> tuple[str | None, str | None]:
    """Trigger an interactive login and return the auth URL to show the user.

    `tailscale up` blocks until the browser flow completes, so we detach it
    and poll status until `AuthURL` is populated (or the node comes up on
    its own if it was already logged in but stopped). Returns (url, error).
    """
    # Fast path: an AuthURL from an earlier attempt is still live.
    res = _status_json()
    if res.ok:
        try:
            data = json.loads(res.output)
        except json.JSONDecodeError:
            data = {}
        if data.get("AuthURL"):
            return data["AuthURL"], None
        if data.get("BackendState") == "Running":
            return None, None  # already logged in and up

    # Detach: `tailscale up` blocks until the user completes the login
    # in the browser; we only care that it publishes the AuthURL first.
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
    only). The port is deliberately non-default and NOT the same as Funnel's
    — Tailscale's Funnel is per-host:port, so keeping admin on its own port
    is what actually keeps it off the public internet."""
    # Legacy port-443 handler from older versions of PiNAS: sweep it away so
    # it can't outlive an upgrade and stay exposed once Funnel is on.
    sudo("tailscale", "serve", f"--https={FUNNEL_PORT}", "--set-path=/", "off", timeout=15)

    if enabled:
        return sudo("tailscale", "serve",
                    f"--https={ADMIN_PORT}", "--bg",
                    "http://localhost:80", timeout=20)
    res = sudo("tailscale", "serve",
               f"--https={ADMIN_PORT}", "--set-path=/", "off", timeout=15)
    if res.ok or _funnel_off_ok(res):
        return CmdResult(True, output="Dashboard is no longer served over Tailscale HTTPS.")
    fallback = sudo("tailscale", "serve", f"--https={ADMIN_PORT}", "off", timeout=15)
    if fallback.ok or _funnel_off_ok(fallback):
        return CmdResult(True, output="Dashboard is no longer served over Tailscale HTTPS.")
    return res


def set_exit_node(advertise: bool) -> CmdResult:
    """Advertise this node as a tailnet exit node (VPN gateway) or stop."""
    flag = "--advertise-exit-node" if advertise else "--advertise-exit-node=false"
    # `tailscale set` avoids re-negotiating auth (unlike `tailscale up`)
    return sudo("tailscale", "set", flag, timeout=30)


def _funnel_off_ok(res: CmdResult) -> bool:
    """Tailscale returns nonzero when we ask it to remove a handler that
    isn't there — that's the state we're trying to reach anyway."""
    err = (res.error or res.output or "").lower()
    return "does not exist" in err or "no such" in err or "no funnel" in err


def set_funnel(enabled: bool, path: str = "/s/") -> CmdResult:
    """Expose only /s/* on the public internet via Funnel.

    Because AllowFunnel is set per host:port (not per path), we must not
    let any other handler live on the same port. On every enable we first
    strip anything at `/` on the Funnel port — a leftover admin handler
    from older setups would otherwise be leaked to the public internet.
    """
    slug = path.rstrip("/") or "/"

    if enabled:
        # Clear any stray root handler from older setups before flipping
        # AllowFunnel on for the port.
        sudo("tailscale", "serve", f"--https={FUNNEL_PORT}", "--set-path=/", "off", timeout=15)
        return sudo("tailscale", "funnel", "--bg", f"--set-path={slug}",
                    "http://localhost:80" + path, timeout=30)

    # Off: remove our /s handler, then also make sure nothing else is
    # holding the port open with AllowFunnel=true.
    res = sudo("tailscale", "funnel", f"--set-path={slug}", "off", timeout=15)
    if res.ok or _funnel_off_ok(res):
        sudo("tailscale", "funnel", "--set-path=/", "off", timeout=15)
        return CmdResult(True, output="Public share links (Funnel) turned off.")
    fallback = sudo("tailscale", "funnel", f"--https={FUNNEL_PORT}", "off", timeout=15)
    if fallback.ok or _funnel_off_ok(fallback):
        return CmdResult(True, output="Public share links (Funnel) turned off.")
    return res
