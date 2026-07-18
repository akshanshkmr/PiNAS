"""On-demand thumbnails for the Files grid view.

Two source types:

- **Images** — Pillow reads the file, downscales the long edge, writes JPEG.
  HEIC/HEIF go through pillow-heif (already registered by files.py).
- **Videos** — ffmpeg extracts a frame from ~10% into the clip, downscales
  it, and writes JPEG. `-frames:v 1 -f mjpeg` keeps the call cheap.

Cached under `data/thumbs/` keyed by (path, mtime, size), so a file that
hasn't changed is served from disk instantly; a re-encoded file rebuilds
its thumb automatically the next time it's requested.
"""

from __future__ import annotations

import hashlib
import io
import os
import subprocess
from pathlib import Path

from . import files

try:
    from PIL import Image, ImageOps

    _PIL_OK = True
except Exception:  # pragma: no cover
    _PIL_OK = False


IMAGE_EXTS = frozenset(files.IMAGE_EXT) - {".svg"}  # svg is served raw
VIDEO_EXTS = frozenset(files.VIDEO_EXT)
ALLOWED_SIZES = frozenset({120, 240, 480, 720})
DEFAULT_SIZE = 240

_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "thumbs"


def _cache_path(src: Path, mtime: float, size: int) -> Path:
    key = f"{src}\x00{int(mtime)}\x00{size}".encode()
    h = hashlib.sha256(key).hexdigest()[:24]
    return _CACHE_DIR / f"{h}.jpg"


def _generate_image_thumb(src: Path, dst: Path, size: int) -> None:
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)   # honour EXIF rotation for photos
        im = im.convert("RGB")
        im.thumbnail((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=82, optimize=True)
    dst.write_bytes(buf.getvalue())


def _generate_video_thumb(src: Path, dst: Path, size: int) -> None:
    """Grab a frame ~10% into the video (skips black opening frames).
    Falls back to the very first frame if seeking fails."""
    dur = _video_duration(src)
    seek = max(1.0, dur * 0.1) if dur > 0 else 0.0

    def _try(offset: float) -> bool:
        args = [
            "ffmpeg", "-nostdin", "-loglevel", "error",
            "-ss", f"{offset:.2f}",
            "-i", str(src),
            "-frames:v", "1",
            "-vf", f"scale='min({size},iw)':'min({size},ih)':force_original_aspect_ratio=decrease",
            "-q:v", "3",
            "-f", "mjpeg",
            "-y", str(dst),
        ]
        r = subprocess.run(args, capture_output=True, timeout=30)
        return r.returncode == 0 and dst.exists() and dst.stat().st_size > 0

    if not _try(seek) and not _try(0.0):
        raise RuntimeError("ffmpeg failed to extract a frame")


def _video_duration(src: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(src)],
        capture_output=True, text=True, timeout=10,
    )
    try:
        return float(r.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


def thumb(path: str, size: int = DEFAULT_SIZE) -> tuple[bytes, str] | None:
    """Return (bytes, mime) for the cached / freshly-generated thumbnail, or
    None if the file isn't thumbnail-able. `path` must already be sandboxed
    by `files.resolve`.
    """
    if not _PIL_OK:
        return None
    if size not in ALLOWED_SIZES:
        size = DEFAULT_SIZE
    src = files.resolve(path)
    if not src.is_file():
        return None

    ext = src.suffix.lower()
    if ext in IMAGE_EXTS:
        gen = _generate_image_thumb
    elif ext in VIDEO_EXTS:
        gen = _generate_video_thumb
    else:
        return None

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    mtime = src.stat().st_mtime
    cached = _cache_path(src, mtime, size)
    if not cached.is_file():
        try:
            gen(src, cached, size)
        except Exception:
            # remove partial file so a retry has a clean slate
            try:
                if cached.exists() and cached.stat().st_size == 0:
                    cached.unlink()
            except OSError:
                pass
            return None
    try:
        return cached.read_bytes(), "image/jpeg"
    except OSError:
        return None
