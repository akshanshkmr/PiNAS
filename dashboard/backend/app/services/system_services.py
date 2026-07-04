"""systemd unit control and log tailing, restricted to a managed allowlist.

Only the units this project owns can be controlled or read, so the endpoint
can't be turned into arbitrary root command execution.
"""

from .shell import CmdResult, run, sudo

# unit -> human description. The allowlist IS the security boundary.
MANAGED_UNITS = {
    "dashboard": "Admin dashboard (this app)",
    "smbd": "Samba file sharing",
    "pironman5": "Pironman case controller",
    "tailscaled": "Tailscale",
    "apache2": "Web server / reverse proxy",
    "fan": "CPU fan at boot",
}

ACTIONS = ("start", "stop", "restart")


def _status(unit):
    res = run("systemctl", "show", unit, "-p", "ActiveState,SubState,UnitFileState,ActiveEnterTimestamp")
    data = {}
    if res.ok:
        for line in res.output.splitlines():
            key, _, val = line.partition("=")
            data[key] = val
    return {
        "active": data.get("ActiveState", "unknown"),
        "sub": data.get("SubState", ""),
        "enabled": data.get("UnitFileState", "unknown"),
        "since": data.get("ActiveEnterTimestamp", ""),
    }


def list_services():
    return [{"unit": unit, "description": desc, **_status(unit)} for unit, desc in MANAGED_UNITS.items()]


def control(unit, action):
    if unit not in MANAGED_UNITS:
        return CmdResult(False, error="Unknown unit.")
    if action not in ACTIONS:
        return CmdResult(False, error="Invalid action.")
    return sudo("systemctl", action, unit, timeout=60)


def logs(unit, lines=200):
    if unit not in MANAGED_UNITS:
        return CmdResult(False, error="Unknown unit.")
    lines = max(10, min(1000, int(lines)))
    return sudo("journalctl", "-u", unit, "-n", str(lines), "--no-pager", "-o", "short-iso", timeout=30)
