"""NAS file browsing, upload/download, and media preview.

Every access is confined to a set of allowed roots (Samba share paths and
mounted array mountpoints). Paths are realpath-resolved and checked against
those roots, so requests can't escape via `..` or symlinks.
"""

import os
import shutil
from pathlib import Path

from . import nas

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".avif", ".ico"}
VIDEO_EXT = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v", ".ogv"}
AUDIO_EXT = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus"}
TEXT_EXT = {
    ".txt", ".md", ".log", ".json", ".yaml", ".yml", ".conf", ".ini", ".cfg",
    ".csv", ".sh", ".py", ".js", ".jsx", ".ts", ".html", ".css", ".xml", ".toml",
}
TEXT_PREVIEW_MAX = 512 * 1024  # 512 KB


def _kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in TEXT_EXT:
        return "text"
    return "file"


def allowed_roots() -> list[dict]:
    """Browseable roots: Samba shares + mounted arrays + the default mount."""
    seen: dict[str, str] = {}

    def add(label: str, path: str):
        try:
            real = os.path.realpath(path)
        except OSError:
            return
        if os.path.isdir(real) and real not in seen:
            seen[real] = label

    for share in nas.load_shares():
        add(share["name"], share["path"])
    for array in nas.list_arrays():
        if array.get("mountpoint"):
            add(array["name"], array["mountpoint"])
    add("nas", nas.DEFAULT_MOUNTPOINT)

    return [{"label": label, "path": path} for path, label in seen.items()]


def _roots() -> list[str]:
    return [r["path"] for r in allowed_roots()]


def resolve(path: str) -> Path:
    """Resolve `path` and confirm it stays inside an allowed root."""
    roots = _roots()
    if not roots:
        raise PermissionError("No NAS location is configured yet. Add a Samba share or mount an array first.")
    real = os.path.realpath(path)
    for root in roots:
        if real == root or real.startswith(root + os.sep):
            return Path(real)
    raise PermissionError("That path is outside the NAS.")


def list_dir(path: str) -> dict:
    target = resolve(path)
    if not target.is_dir():
        raise NotADirectoryError("Not a folder.")
    entries = []
    with os.scandir(target) as it:
        for entry in it:
            try:
                is_dir = entry.is_dir()
                st = entry.stat()
            except OSError:
                continue
            entries.append(
                {
                    "name": entry.name,
                    "path": str(target / entry.name),
                    "is_dir": is_dir,
                    "size": 0 if is_dir else st.st_size,
                    "mtime": st.st_mtime,
                    "kind": "dir" if is_dir else _kind(Path(entry.name)),
                }
            )
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
    return {"path": str(target), "entries": entries}


def make_dir(parent: str, name: str) -> None:
    if not name or "/" in name or name in (".", ".."):
        raise ValueError("Invalid folder name.")
    parent_dir = resolve(parent)
    target = resolve(str(parent_dir / name))  # re-check the new path is in-root
    target.mkdir(parents=False, exist_ok=False)


def delete(path: str) -> None:
    target = resolve(path)
    if str(target) in _roots():
        raise PermissionError("Refusing to delete a NAS root.")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()


def read_text(path: str) -> str:
    target = resolve(path)
    if not target.is_file():
        raise FileNotFoundError("Not a file.")
    if target.stat().st_size > TEXT_PREVIEW_MAX:
        raise ValueError("File is too large to preview as text.")
    return target.read_text(errors="replace")
