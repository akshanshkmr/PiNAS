"""Configuration and SD-image backup / restore.

Two related capabilities:

- **Config backup** — periodically snapshot `smb.conf`, samba's user db, and
  `mdadm.conf` (plus the dashboard's own `shares.json`) into
  `<nas>/.pinas-config/`, so a fresh PiNAS install can auto-detect it and
  restore the settings in one click.
- **SD image backup** — stream `dd if=/dev/mmcblk0 | pigz` to a `.img.gz` on
  the NAS. Slow (~15–30 min for a 32 GB card), so only runs on demand.

Both target the first mounted+writable NAS root the dashboard can see. If
there isn't one (e.g. fresh install with no array or share yet), nothing is
written and the caller gets a clear error.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import files


# Files we snapshot. Paths are mirrored inside .pinas-config/ so restore is a
# simple walk that puts each file back where it belongs.
_CONFIG_FILES: tuple[str, ...] = (
    "/etc/samba/smb.conf",
    "/var/lib/samba/private/passdb.tdb",
    "/etc/mdadm/mdadm.conf",
)

# Allowlist for restore — a corrupt or malicious backup can't put a file
# outside this set back onto disk.
_RESTORE_ALLOWED: frozenset[str] = frozenset(p.lstrip("/") for p in _CONFIG_FILES) | {
    "pinas/shares.json",
}

_BACKEND_DATA = Path(__file__).resolve().parents[2] / "data"
_SHARES_JSON = _BACKEND_DATA / "shares.json"
_LAST_STATE = _BACKEND_DATA / "backup_state.json"

# Keep only the newest N SD images to avoid filling the NAS.
_KEEP_SD_IMAGES = 2


# ------------------------------------------------------------------ helpers


def _first_nas_root() -> Path | None:
    """Pick a NAS root that exists, is a real directory, and is writable by us."""
    for root in files.allowed_roots():
        p = Path(root["path"])
        try:
            if p.is_dir() and os.access(p, os.W_OK):
                return p
        except OSError:
            continue
    return None


def _hostname() -> str:
    try:
        return subprocess.run(["hostname"], capture_output=True, text=True, timeout=2).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def _touch_state(update: dict) -> None:
    """Persist a small state file so the UI can show 'last backup at …'."""
    state = {}
    if _LAST_STATE.is_file():
        try:
            state = json.loads(_LAST_STATE.read_text())
        except json.JSONDecodeError:
            state = {}
    state.update(update)
    _BACKEND_DATA.mkdir(parents=True, exist_ok=True)
    _LAST_STATE.write_text(json.dumps(state, indent=2))


def state() -> dict:
    if _LAST_STATE.is_file():
        try:
            return json.loads(_LAST_STATE.read_text())
        except json.JSONDecodeError:
            pass
    return {}


# ------------------------------------------------------------------ config


def find_restore_source() -> dict | None:
    """Look for `.pinas-config/` on any NAS root; return the newest one."""
    candidates: list[tuple[int, Path, dict]] = []
    for root in files.allowed_roots():
        cfg = Path(root["path"]) / ".pinas-config"
        manifest_path = cfg / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        candidates.append((int(manifest.get("timestamp") or 0), cfg, manifest))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    _, cfg, manifest = candidates[0]
    return {"path": str(cfg), "manifest": manifest}


def backup_config() -> dict:
    """Snapshot config files into `<nas>/.pinas-config/`. Idempotent."""
    root = _first_nas_root()
    if not root:
        return {"ok": False, "error": "No writable NAS location is available."}

    target = root / ".pinas-config"
    target.mkdir(exist_ok=True)

    saved: list[str] = []
    skipped: list[dict] = []

    for src in _CONFIG_FILES:
        rel = src.lstrip("/")
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not Path(src).exists():
            skipped.append({"file": src, "error": "not present"})
            continue
        # sudo cp -a preserves ownership/mode; we then chmod so we can read it
        # back later when detecting restore sources.
        r = subprocess.run(
            ["sudo", "-n", "install", "-m", "0644", src, str(dst)],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            saved.append(rel)
        else:
            skipped.append({"file": src, "error": (r.stderr or r.stdout or "cp failed").strip()[:200]})

    # dashboard's own state
    if _SHARES_JSON.is_file():
        rel = "pinas/shares.json"
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_SHARES_JSON, dst)
        saved.append(rel)

    manifest = {
        "timestamp": int(time.time()),
        "iso_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "hostname": _hostname(),
        "files": saved,
        "skipped": skipped,
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2))
    _touch_state({"last_config_backup": manifest})
    return {"ok": True, "path": str(target), **manifest}


def restore_config(source_path: str) -> dict:
    """Copy files from a `.pinas-config/` dir back to their canonical paths,
    then restart Samba."""
    src = Path(source_path).resolve()
    manifest_path = src / "manifest.json"
    if not manifest_path.is_file():
        return {"ok": False, "error": "Not a PiNAS config backup (no manifest)."}
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError:
        return {"ok": False, "error": "Backup manifest is unreadable."}

    restored: list[str] = []
    errors: list[dict] = []

    for rel in manifest.get("files", []):
        if rel not in _RESTORE_ALLOWED:
            errors.append({"file": rel, "error": "not in restore allowlist"})
            continue
        src_file = (src / rel).resolve()
        # extra guard: refuse anything that escapes the backup directory
        try:
            src_file.relative_to(src)
        except ValueError:
            errors.append({"file": rel, "error": "path escapes backup dir"})
            continue
        if not src_file.is_file():
            errors.append({"file": rel, "error": "missing from backup"})
            continue

        if rel == "pinas/shares.json":
            _BACKEND_DATA.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, _SHARES_JSON)
            restored.append(rel)
            continue

        # 600 for the samba secret db, 644 for everything else
        mode = "0600" if rel.endswith("passdb.tdb") else "0644"
        dst_abs = "/" + rel
        r = subprocess.run(
            ["sudo", "-n", "install", "-D", "-o", "root", "-g", "root", "-m", mode,
             str(src_file), dst_abs],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            restored.append(rel)
        else:
            errors.append({"file": rel, "error": (r.stderr or r.stdout or "install failed").strip()[:200]})

    # kick samba so it re-reads
    samba = subprocess.run(
        ["sudo", "-n", "systemctl", "restart", "smbd", "nmbd"], capture_output=True, text=True
    )
    _touch_state({"last_config_restore": {"timestamp": int(time.time()), "source": str(src),
                                          "restored": restored, "errors": errors}})
    return {
        "ok": len(errors) == 0,
        "restored": restored,
        "errors": errors,
        "manifest": manifest,
        "samba_restart_error": (samba.stderr.strip() if samba.returncode != 0 else None),
    }


# ------------------------------------------------------------------ SD image


@dataclass
class SDBackupJob:
    output: Path
    started: float = field(default_factory=time.time)
    bytes_copied: int = 0
    total_bytes: int = 0
    rate_bps: float = 0.0
    done: bool = False
    ok: bool = False
    error: str = ""

    def snapshot(self) -> dict:
        pct = (self.bytes_copied / self.total_bytes * 100) if self.total_bytes else 0
        return {
            "output": str(self.output),
            "started": self.started,
            "elapsed": time.time() - self.started,
            "bytes_copied": self.bytes_copied,
            "total_bytes": self.total_bytes,
            "percent": round(pct, 1),
            "rate_bps": round(self.rate_bps, 0),
            "done": self.done,
            "ok": self.ok,
            "error": self.error,
        }


_current_job: SDBackupJob | None = None
_job_lock = asyncio.Lock()


def current_sd_backup() -> dict | None:
    return _current_job.snapshot() if _current_job else None


def _detect_source_device() -> str:
    """Return the block device backing '/'. Prefers whole-disk name."""
    try:
        # e.g. "/dev/mmcblk0p2" → whole disk "/dev/mmcblk0"
        r = subprocess.run(["findmnt", "-n", "-o", "SOURCE", "/"], capture_output=True, text=True)
        part = r.stdout.strip()
        if not part:
            return "/dev/mmcblk0"
        m = re.match(r"^(/dev/(?:mmcblk\d+|nvme\d+n\d+|sd[a-z]))(?:p?\d+)?$", part)
        return m.group(1) if m else part
    except Exception:  # noqa: BLE001
        return "/dev/mmcblk0"


def _rotate_old_images(dir_: Path, keep: int) -> None:
    imgs = sorted(dir_.glob("sd-*.img.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in imgs[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


# dd 'status=progress' emits lines like:
#   "3145728000 bytes (3.1 GB, 2.9 GiB) copied, 27 s, 116 MB/s"
_DD_PROGRESS_RE = re.compile(r"^\s*(\d+)\s+bytes.*copied,\s*([\d.]+)\s*s,\s*([\d.]+)\s*([kMG])?B/s")


def _parse_dd_progress(line: str) -> tuple[int, float] | None:
    m = _DD_PROGRESS_RE.match(line)
    if not m:
        return None
    bytes_ = int(m.group(1))
    rate_val = float(m.group(3))
    unit = m.group(4) or ""
    scale = {"": 1, "k": 1e3, "M": 1e6, "G": 1e9}[unit]
    return bytes_, rate_val * scale


async def start_sd_backup() -> dict:
    """Kick off an SD → NAS image job. Returns immediately with a job snapshot."""
    global _current_job
    async with _job_lock:
        if _current_job and not _current_job.done:
            return {"ok": False, "error": "Another SD backup is already running.", "job": _current_job.snapshot()}

        root = _first_nas_root()
        if not root:
            return {"ok": False, "error": "No writable NAS location is available."}
        cfg_dir = root / ".pinas-config"
        cfg_dir.mkdir(exist_ok=True)

        device = _detect_source_device()
        try:
            total = int(subprocess.run(
                ["lsblk", "-b", "-d", "-n", "-o", "SIZE", device], capture_output=True, text=True, timeout=5
            ).stdout.strip())
        except Exception:  # noqa: BLE001
            total = 0

        ts = time.strftime("%Y-%m-%d-%H%M")
        out = cfg_dir / f"sd-{ts}.img.gz"
        _current_job = SDBackupJob(output=out, total_bytes=total)

    asyncio.create_task(_run_sd_backup(device, out, cfg_dir))
    return {"ok": True, "job": _current_job.snapshot()}


async def _run_sd_backup(device: str, out: Path, cfg_dir: Path) -> None:
    """Pipe dd → pigz → out. Watch dd's stderr for progress."""
    global _current_job
    assert _current_job is not None
    job = _current_job

    # sync everything to disk first — the image is a crash-consistent snapshot,
    # so at least fsync the FS caches for a cleaner result.
    subprocess.run(["sudo", "-n", "sync"], check=False)

    # Use pigz for parallel compression when available; fall back to gzip.
    gz = "pigz" if shutil.which("pigz") else "gzip"

    # Compose: sudo dd ... | pigz -1 > out
    # We use a shell so the pipeline stays a single process group we can kill.
    cmd = f'sudo -n dd if={device} bs=4M status=progress conv=sync,noerror | {gz} -1 > "{out}"'

    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    # dd writes progress to stderr as \r-terminated lines. Read as chunks so
    # partial lines don't stall us.
    assert proc.stderr is not None
    buf = b""
    try:
        while True:
            chunk = await proc.stderr.read(1024)
            if not chunk:
                break
            buf += chunk
            # split on \r or \n
            while True:
                sep = min((i for i in (buf.find(b"\r"), buf.find(b"\n")) if i >= 0), default=-1)
                if sep < 0:
                    break
                line = buf[:sep].decode(errors="replace")
                buf = buf[sep + 1:]
                parsed = _parse_dd_progress(line)
                if parsed:
                    job.bytes_copied, job.rate_bps = parsed
        await proc.wait()
    except Exception as e:  # noqa: BLE001
        job.error = str(e)

    rc = proc.returncode or 0
    job.done = True
    if rc == 0 and out.exists() and out.stat().st_size > 0:
        job.ok = True
        job.bytes_copied = job.total_bytes or job.bytes_copied
        _rotate_old_images(cfg_dir, _KEEP_SD_IMAGES)
        _touch_state({
            "last_sd_backup": {
                "timestamp": int(time.time()),
                "output": str(out),
                "size": out.stat().st_size,
                "source_bytes": job.total_bytes,
            }
        })
    else:
        if not job.error:
            job.error = f"dd/{gz} exited {rc}"
        # remove a truncated file so we don't waste space
        try:
            if out.exists() and out.stat().st_size < 1024:
                out.unlink()
        except OSError:
            pass


def list_sd_backups() -> list[dict]:
    root = _first_nas_root()
    if not root:
        return []
    cfg_dir = root / ".pinas-config"
    if not cfg_dir.is_dir():
        return []
    return [
        {"path": str(p), "size": p.stat().st_size, "mtime": p.stat().st_mtime}
        for p in sorted(cfg_dir.glob("sd-*.img.gz"), key=lambda x: x.stat().st_mtime, reverse=True)
    ]


# ------------------------------------------------------------------ scheduler


async def daily_config_backup_loop() -> None:
    """Run `backup_config` roughly every 24 h, quietly skipping when there's
    no NAS available. Fires an immediate one 60 s after startup so a
    newly-configured share gets a first snapshot without waiting a day."""
    await asyncio.sleep(60)
    while True:
        try:
            result = await asyncio.to_thread(backup_config)
            # silent success/failure — the UI surfaces the last-backup state
            _ = result
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(24 * 60 * 60)
