"""NAS file browsing, upload/download, and media preview.

Every access is confined to a set of allowed roots (Samba share paths and
mounted array mountpoints). Paths are realpath-resolved and checked against
those roots, so requests can't escape via `..` or symlinks.
"""

import io
import os
import shutil
import zipfile
from pathlib import Path

from . import nas

# HEIC/HEIF can't be decoded by browsers, so we transcode to JPEG on the fly.
try:
    import pillow_heif
    from PIL import Image

    pillow_heif.register_heif_opener()
    _HEIF_OK = True
except Exception:  # pragma: no cover - optional dependency / platform wheel
    _HEIF_OK = False

HEIF_EXT = {".heic", ".heif"}
PREVIEW_MAX_DIM = 2560  # downscale long edge for a snappy, screen-sized preview

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".avif", ".ico", ".heic", ".heif"}
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


def dir_size(path: str) -> dict:
    """Recursive size and file count of a folder. Skips symlinks (no loops)."""
    target = resolve(path)
    if not target.is_dir():
        raise NotADirectoryError("Not a folder.")
    total = 0
    files = 0
    stack = [str(target)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                            files += 1
                    except OSError:
                        continue
        except OSError:
            continue
    return {"path": str(target), "size": total, "files": files}


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


class _ZipBuffer:
    """A minimal writable that hands the ZipFile's output to the streamer."""

    def __init__(self):
        self._chunks = []

    def write(self, data):
        self._chunks.append(bytes(data))
        return len(data)

    def flush(self):
        pass

    def drain(self) -> bytes:
        if not self._chunks:
            return b""
        data = b"".join(self._chunks)
        self._chunks.clear()
        return data


def zip_dir_stream(target: Path):
    """Yield a zip archive of `target` incrementally — no temp file, so large
    folders start downloading immediately and use bounded memory. Stored (no
    compression), which is fastest and ideal for already-compressed media.
    Symlinks are skipped so the archive can't reach outside the folder.
    """
    buf = _ZipBuffer()
    base = target.parent
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
        for dirpath, dirnames, filenames in os.walk(target):  # followlinks=False
            for name in sorted(dirnames):
                full = os.path.join(dirpath, name)
                if os.path.islink(full):
                    continue
                zf.writestr(os.path.relpath(full, base) + "/", b"")  # keep empty dirs
                data = buf.drain()
                if data:
                    yield data
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                if os.path.islink(full):
                    continue
                try:
                    info = zipfile.ZipInfo.from_file(full, os.path.relpath(full, base))
                    info.compress_type = zipfile.ZIP_STORED
                    with zf.open(info, "w") as dest, open(full, "rb") as src:
                        while True:
                            chunk = src.read(1024 * 1024)
                            if not chunk:
                                break
                            dest.write(chunk)
                            data = buf.drain()
                            if data:
                                yield data
                except OSError:
                    continue
                data = buf.drain()
                if data:
                    yield data
    data = buf.drain()
    if data:
        yield data


def heif_supported() -> bool:
    return _HEIF_OK


def heic_to_jpeg(path: str) -> bytes:
    """Transcode a HEIC/HEIF file to a screen-sized JPEG for browser preview."""
    if not _HEIF_OK:
        raise RuntimeError("HEIC preview needs pillow-heif on the server.")
    target = resolve(path)
    if not target.is_file():
        raise FileNotFoundError("Not a file.")
    try:
        with Image.open(target) as im:
            im = im.convert("RGB")
            im.thumbnail((PREVIEW_MAX_DIM, PREVIEW_MAX_DIM))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=88)
            return buf.getvalue()
    except OSError:
        raise
    except Exception as exc:  # Pillow decode errors aren't OSError
        raise ValueError(f"Could not decode image: {exc}")


def read_text(path: str) -> str:
    target = resolve(path)
    if not target.is_file():
        raise FileNotFoundError("Not a file.")
    if target.stat().st_size > TEXT_PREVIEW_MAX:
        raise ValueError("File is too large to preview as text.")
    return target.read_text(errors="replace")
