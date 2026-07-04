"""RAID array and Samba share management.

Completes the NAS lifecycle: create/assemble/mount arrays with persistence
across reboots (mdadm.conf + fstab), monitor sync progress, and manage
Samba shares/users without loosening permissions on system config files.
"""

import configparser
import io
import json
import re
from pathlib import Path

from .shell import CmdResult, run, sudo, sudo_write_file

DEVICE_RE = re.compile(r"^/dev/(sd[a-z]+\d*|nvme\d+n\d+(p\d+)?|md\d+)$")
MD_NAME_RE = re.compile(r"^md\d+$")
SHARE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
MOUNTPOINT_RE = re.compile(r"^/(mnt|srv|media)(/[A-Za-z0-9._-]+)+$")
USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
RAID_LEVELS = {"0", "1", "5", "10"}

SMB_CONF = "/etc/samba/smb.conf"
MDADM_CONF = "/etc/mdadm/mdadm.conf"
DEFAULT_MOUNTPOINT = "/mnt/nas"

_SHARES_STORE = Path(__file__).resolve().parent.parent.parent / "data" / "smb_shares.json"


def _fail(message: str) -> CmdResult:
    return CmdResult(False, error=message)


# -------------------- Disks --------------------

def list_disks() -> list[dict]:
    res = run("lsblk", "-J", "-b", "-o", "NAME,MODEL,SIZE,TYPE,MOUNTPOINT,FSTYPE")
    if not res.ok:
        return []
    try:
        devices = json.loads(res.output).get("blockdevices", [])
    except json.JSONDecodeError:
        return []
    disks = []
    for d in devices:
        name = d.get("name") or ""
        # skip the boot SD card and virtual block devices
        if d.get("type") != "disk" or name.startswith(("mmcblk", "zram", "loop", "ram")):
            continue
        children = d.get("children") or []
        in_raid = any((c.get("fstype") or "") == "linux_raid_member" for c in children) or (
            d.get("fstype") == "linux_raid_member"
        )
        mounted = d.get("mountpoint") or next((c.get("mountpoint") for c in children if c.get("mountpoint")), None)
        disks.append(
            {
                "device": f"/dev/{d['name']}",
                "model": (d.get("model") or "Unknown").strip(),
                "size": int(d.get("size") or 0),
                "in_raid": in_raid,
                "mountpoint": mounted,
                "fstype": d.get("fstype"),
            }
        )
    return disks


# -------------------- RAID --------------------

def _mounts() -> dict[str, str]:
    """device -> mountpoint for active mounts."""
    res = run("findmnt", "-rn", "-o", "SOURCE,TARGET")
    mounts = {}
    if res.ok:
        for line in res.output.splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2:
                mounts[parts[0]] = parts[1]
    return mounts


def list_arrays() -> list[dict]:
    """All md arrays with state, members, sync progress, and mountpoint."""
    arrays = []
    mounts = _mounts()
    res = run("lsblk", "-J", "-b", "-o", "NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE")
    md_sizes = {}
    if res.ok:
        try:
            def walk(nodes):
                for n in nodes:
                    if (n.get("type") or "").startswith("raid"):
                        md_sizes[n["name"]] = int(n.get("size") or 0)
                    walk(n.get("children") or [])
            walk(json.loads(res.output).get("blockdevices", []))
        except json.JSONDecodeError:
            pass

    mdstat = run("cat", "/proc/mdstat")
    if not mdstat.ok:
        return arrays
    current = None
    for line in mdstat.output.splitlines():
        m = re.match(
            r"^(md\d+)\s*:\s*(\w+)(?:\s+\(auto-read-only\))?\s+(raid\d+|linear|multipath)\s+(.*)$", line
        )
        if not m:
            # inactive arrays list members without a RAID level
            im = re.match(r"^(md\d+)\s*:\s*(inactive)\s+(.*)$", line)
            m = im and (im.group(1), im.group(2), "unknown", im.group(3))
        if m:
            name, state, level, members_raw = m if isinstance(m, tuple) else m.groups()
            members = []
            for token in members_raw.split():
                dm = re.match(r"^([a-zA-Z0-9]+)\[\d+\](\([A-Z]\))?$", token)
                if dm:
                    members.append({"device": f"/dev/{dm.group(1)}", "faulty": dm.group(2) == "(F)"})
            current = {
                "name": name,
                "device": f"/dev/{name}",
                "state": state,
                "level": level,
                "members": members,
                "size": md_sizes.get(name, 0),
                "sync": None,
                "mountpoint": mounts.get(f"/dev/{name}"),
            }
            arrays.append(current)
        elif current and ("recovery" in line or "resync" in line or "check" in line or "reshape" in line):
            sm = re.search(r"(recovery|resync|check|reshape)\s*=\s*([\d.]+)%(?:.*finish=([\w.]+min))?", line)
            if sm:
                current["sync"] = {"action": sm.group(1), "percent": float(sm.group(2)), "finish": sm.group(3)}
    return arrays


def raid_detail(md_name: str) -> CmdResult:
    if not MD_NAME_RE.match(md_name):
        return _fail("Invalid array name.")
    return sudo("mdadm", "--detail", f"/dev/{md_name}")


def _next_md_device() -> str:
    used = {a["name"] for a in list_arrays()}
    n = 0
    while f"md{n}" in used:
        n += 1
    return f"/dev/md{n}"


def _persist_mdadm_conf() -> CmdResult:
    """Rewrite mdadm.conf ARRAY lines from a fresh scan (no duplicate appends)."""
    scan = sudo("mdadm", "--detail", "--scan")
    if not scan.ok:
        return scan
    existing = run("cat", MDADM_CONF)
    kept = [
        line
        for line in (existing.output.splitlines() if existing.ok else [])
        if not line.strip().startswith("ARRAY ")
    ]
    content = "\n".join(kept).rstrip() + "\n\n" + scan.output + "\n"
    res = sudo_write_file(MDADM_CONF, content)
    if not res.ok:
        return res
    # Bake the new array into the boot image so it assembles on reboot.
    return sudo("update-initramfs", "-u", timeout=600)


def _fstab_lines() -> list[str]:
    res = run("cat", "/etc/fstab")
    return res.output.splitlines() if res.ok else []


def _persist_fstab(device: str, mountpoint: str) -> CmdResult:
    blkid = sudo("blkid", "-s", "UUID", "-o", "value", device)
    if not blkid.ok or not blkid.output:
        return _fail(f"Could not read UUID for {device}: {blkid.error}")
    uuid = blkid.output.strip()
    lines = [
        line
        for line in _fstab_lines()
        if uuid not in line and f" {mountpoint} " not in f"{line} "
    ]
    lines.append(f"UUID={uuid} {mountpoint} ext4 defaults,nofail 0 2")
    return sudo_write_file("/etc/fstab", "\n".join(lines) + "\n")


def _remove_from_fstab(mountpoint: str) -> CmdResult:
    lines = [line for line in _fstab_lines() if f" {mountpoint} " not in f"{line} "]
    return sudo_write_file("/etc/fstab", "\n".join(lines) + "\n")


def create_raid(disks: list[str], level: str, mountpoint: str = DEFAULT_MOUNTPOINT) -> CmdResult:
    if level not in RAID_LEVELS:
        return _fail(f"Unsupported RAID level '{level}'.")
    if not disks:
        return _fail("Select at least one disk.")
    min_disks = {"0": 2, "1": 2, "5": 3, "10": 4}[level]
    if len(disks) < min_disks:
        return _fail(f"RAID {level} needs at least {min_disks} disks.")
    for d in disks:
        if not DEVICE_RE.match(d):
            return _fail(f"Invalid device path: {d}")
    if not MOUNTPOINT_RE.match(mountpoint):
        return _fail("Mountpoint must live under /mnt, /srv or /media.")

    md = _next_md_device()
    for d in disks:
        res = sudo("wipefs", "-a", d, timeout=60)
        if not res.ok:
            return _fail(f"Failed wiping signatures on {d}: {res.error}")
    res = sudo(
        "mdadm", "--create", md,
        "--level", level,
        f"--raid-devices={len(disks)}",
        *disks,
        "--force", "--run",
        timeout=120,
    )
    if not res.ok:
        return _fail(f"mdadm create failed: {res.error}")
    res = sudo("mkfs.ext4", "-F", md, timeout=600)
    if not res.ok:
        return _fail(f"Formatting {md} failed: {res.error}")
    res = mount_array(Path(md).name, mountpoint)
    if not res.ok:
        return res
    res = _persist_mdadm_conf()
    if not res.ok:
        return _fail(f"Array created and mounted, but persisting mdadm.conf failed: {res.error}")
    return CmdResult(True, output=f"RAID {level} created at {md}, mounted at {mountpoint}, persistent across reboots.")


def assemble_arrays() -> CmdResult:
    res = sudo("mdadm", "--assemble", "--scan", timeout=60)
    # mdadm exits 1 when there is nothing new to assemble; treat as informational
    if not res.ok and "No arrays found" not in res.error:
        return res
    return CmdResult(True, output=res.output or "Assemble scan complete.")


def mount_array(md_name: str, mountpoint: str = DEFAULT_MOUNTPOINT, persist: bool = True) -> CmdResult:
    if not MD_NAME_RE.match(md_name):
        return _fail("Invalid array name.")
    if not MOUNTPOINT_RE.match(mountpoint):
        return _fail("Mountpoint must live under /mnt, /srv or /media.")
    device = f"/dev/{md_name}"
    res = sudo("mkdir", "-p", mountpoint)
    if not res.ok:
        return _fail(f"Failed creating {mountpoint}: {res.error}")
    res = sudo("mount", device, mountpoint)
    if not res.ok and "already mounted" not in res.error:
        return _fail(f"Failed mounting {device}: {res.error}")
    if persist:
        res = _persist_fstab(device, mountpoint)
        if not res.ok:
            return _fail(f"Mounted, but fstab persistence failed: {res.error}")
    return CmdResult(True, output=f"{device} mounted at {mountpoint}.")


def unmount_array(md_name: str) -> CmdResult:
    if not MD_NAME_RE.match(md_name):
        return _fail("Invalid array name.")
    device = f"/dev/{md_name}"
    mountpoint = _mounts().get(device)
    if not mountpoint:
        return CmdResult(True, output=f"{device} is not mounted.")
    res = sudo("umount", device)
    if not res.ok:
        return _fail(f"Failed unmounting {device}: {res.error}")
    _remove_from_fstab(mountpoint)
    return CmdResult(True, output=f"{device} unmounted.")


def stop_array(md_name: str) -> CmdResult:
    """Unmount and stop an array. Data on member disks is left intact."""
    if not MD_NAME_RE.match(md_name):
        return _fail("Invalid array name.")
    res = unmount_array(md_name)
    if not res.ok:
        return res
    res = sudo("mdadm", "--stop", f"/dev/{md_name}", timeout=60)
    if not res.ok:
        return _fail(f"Failed stopping array: {res.error}")
    persist = _persist_mdadm_conf()
    if not persist.ok:
        return CmdResult(True, output=f"Array stopped, but mdadm.conf update failed: {persist.error}")
    return CmdResult(True, output=f"/dev/{md_name} stopped.")


def sync_array(md_name: str, action: str = "repair") -> CmdResult:
    if not MD_NAME_RE.match(md_name):
        return _fail("Invalid array name.")
    if action not in ("repair", "check", "idle"):
        return _fail("Sync action must be repair, check, or idle.")
    res = sudo_write_file(f"/sys/block/{md_name}/md/sync_action", f"{action}\n")
    if not res.ok:
        return _fail(f"Failed to set sync action: {res.error}")
    return CmdResult(True, output=f"Requested '{action}' on /dev/{md_name}.")


# -------------------- Samba --------------------

def load_shares() -> list[dict]:
    if _SHARES_STORE.exists():
        try:
            shares = json.loads(_SHARES_STORE.read_text())
            for s in shares:
                s.setdefault("allow_guest", False)
                s.setdefault("read_only", False)
            return shares
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save_shares(shares: list[dict]) -> None:
    _SHARES_STORE.parent.mkdir(parents=True, exist_ok=True)
    _SHARES_STORE.write_text(json.dumps(shares, indent=2))


def _render_smb_conf(shares: list[dict]) -> str:
    config = configparser.ConfigParser()
    config["global"] = {
        "workgroup": "WORKGROUP",
        "server string": "PiNAS",
        "map to guest": "Bad User",
        "dns proxy": "no",
        "server min protocol": "SMB2",
        "server max protocol": "SMB3",
    }
    for s in shares:
        config[s["name"]] = {
            "path": s["path"],
            "browseable": "yes",
            "read only": "yes" if s.get("read_only") else "no",
            "guest ok": "yes" if s.get("allow_guest") else "no",
            "create mask": "0775",
            "directory mask": "0775",
        }
    buf = io.StringIO()
    config.write(buf)
    return buf.getvalue()


def configure_shares(shares: list[dict]) -> CmdResult:
    seen = set()
    clean = []
    for s in shares:
        name = (s.get("name") or "").strip()
        path = (s.get("path") or "").strip()
        if not SHARE_NAME_RE.match(name):
            return _fail(f"Invalid share name '{name}'. Use letters, digits, dot, dash, underscore.")
        if name.lower() in seen:
            return _fail(f"Duplicate share name '{name}'.")
        if not path.startswith("/") or ".." in path:
            return _fail(f"Share path for '{name}' must be an absolute path.")
        seen.add(name.lower())
        clean.append(
            {
                "name": name,
                "path": path,
                "allow_guest": bool(s.get("allow_guest")),
                "read_only": bool(s.get("read_only")),
            }
        )
    res = sudo_write_file(SMB_CONF, _render_smb_conf(clean))
    if not res.ok:
        return _fail(f"Failed writing smb.conf: {res.error}")
    _save_shares(clean)
    res = sudo("systemctl", "restart", "smbd", timeout=60)
    if not res.ok:
        return _fail(f"Config saved but Samba restart failed: {res.error}")
    return CmdResult(True, output="Shares updated and Samba restarted.")


def samba_status() -> dict:
    active = run("systemctl", "is-active", "smbd")
    return {"service": active.output or "unknown", "shares": load_shares(), "users": list_samba_users()}


def list_samba_users() -> list[str]:
    res = sudo("pdbedit", "-L", timeout=15)
    if not res.ok:
        return []
    return sorted(line.split(":")[0] for line in res.output.splitlines() if ":" in line)


def add_samba_user(username: str, password: str) -> CmdResult:
    if not USERNAME_RE.match(username or ""):
        return _fail("Invalid username.")
    if not password:
        return _fail("Password required.")
    res = sudo("smbpasswd", "-s", "-a", username, input_text=f"{password}\n{password}\n")
    if not res.ok:
        return _fail(f"Failed to add Samba user: {res.error}")
    return CmdResult(True, output=f"Samba user '{username}' added/updated.")


def disable_samba_user(username: str) -> CmdResult:
    if not USERNAME_RE.match(username or ""):
        return _fail("Invalid username.")
    res = sudo("smbpasswd", "-d", username)
    if not res.ok:
        return _fail(f"Failed to disable '{username}': {res.error}")
    return CmdResult(True, output=f"Samba user '{username}' disabled.")


def overview() -> dict:
    mdstat = run("cat", "/proc/mdstat")
    return {
        "disks": list_disks(),
        "arrays": list_arrays(),
        "mdstat": mdstat.output if mdstat.ok else "",
        "samba": samba_status(),
    }
