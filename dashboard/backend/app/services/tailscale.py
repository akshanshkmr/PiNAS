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


def _serve_url(res):
    r = run("tailscale", "serve", "status", timeout=10)
    if not r.ok:
        r = sudo("tailscale", "serve", "status", timeout=10)
    if not r.ok or not r.output or "no serve config" in r.output.lower():
        return None
    return True  # serving something; URL is derived from the node's DNS name


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


def _funnel_status():
    """Return (enabled, published_paths). Funnel exposes serve to the public
    internet, so a running Funnel means share links work off-tailnet.

    We prefer `tailscale serve status --json` because it always includes
    both Web (serve) and Funnel state as structured data. Text parsing
    of `tailscale funnel status` was fragile — the CLI's phrasing has
    varied ("no funnel", "not currently serving", empty output on newer
    builds), and the socket is often root-only so the non-sudo probe
    silently reports "off"."""
    r = run("tailscale", "serve", "status", "--json", timeout=8)
    if not r.ok:
        r = sudo("tailscale", "serve", "status", "--json", timeout=8)
    if not r.ok or not r.output:
        return False, []
    try:
        cfg = json.loads(r.output)
    except json.JSONDecodeError:
        return False, []

    # Funnel is keyed by "<host>:<port>" → true. Any true entry means on.
    allow = cfg.get("AllowFunnel") or {}
    enabled = any(bool(v) for v in allow.values())
    if not enabled:
        return False, []

    paths: list[str] = []
    for host_port, web in (cfg.get("Web") or {}).items():
        for path in (web.get("Handlers") or {}).keys():
            paths.append(f"https://{host_port.split(':', 1)[0]}{path}")
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

    funnel_on, funnel_paths = _funnel_status()

    return {
        "available": True,
        "state": data.get("BackendState", "Unknown"),  # Running | Stopped | NeedsLogin
        "hostname": node.get("HostName"),
        "dns_name": dns_name,
        "ips": node.get("TailscaleIPs", []) or [],
        "serving": bool(_serve_url(res)),
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
    """Publish (or tear down) the admin dashboard at https://<host>.ts.net/.

    Tailscale terminates TLS with a magic-DNS cert — no port forward, no
    Let's Encrypt dance. Setup used to run this from setup.sh; now the
    Network tab drives it."""
    if enabled:
        return sudo("tailscale", "serve", "--bg", "http://localhost:80", timeout=20)
    # Off — clear the root handler; ignore "already gone" errors.
    res = sudo("tailscale", "serve", "--set-path=/", "off", timeout=15)
    if res.ok or _funnel_off_ok(res):
        return CmdResult(True, output="Dashboard is no longer served over Tailscale HTTPS.")
    # Fall back to shutting the entire HTTPS listener if anything else
    # is stuck on it (e.g. Funnel-only /s/ handler on the same host:port).
    fallback = sudo("tailscale", "serve", "--https=443", "off", timeout=15)
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
    """Expose only the /s/* share path to the public internet via Funnel,
    or tear it down. The admin dashboard stays tailnet-only."""
    slug = path.rstrip("/") or "/"

    if enabled:
        # target: proxy to the local dashboard's public share tree
        return sudo("tailscale", "funnel", "--bg", f"--set-path={slug}",
                    "http://localhost:80" + path, timeout=30)

    # Off path: try to remove our /s handler first — that's the one PiNAS owns.
    res = sudo("tailscale", "funnel", f"--set-path={slug}", "off", timeout=15)
    if res.ok or _funnel_off_ok(res):
        # Also clear any Funnel we may have set on the root path in older setups.
        sudo("tailscale", "funnel", "--set-path=/", "off", timeout=15)
        return CmdResult(True, output="Public share links (Funnel) turned off.")

    # If /s wasn't there but Funnel is still on for some other handler
    # (e.g. root from setup.sh), disable Funnel entirely rather than leave
    # a stale/confused state on the toggle.
    fallback = sudo("tailscale", "funnel", "--https=443", "off", timeout=15)
    if fallback.ok or _funnel_off_ok(fallback):
        return CmdResult(True, output="Public share links (Funnel) turned off.")
    return res
