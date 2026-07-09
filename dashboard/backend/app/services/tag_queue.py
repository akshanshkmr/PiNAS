"""Background queue that runs the vision model one photo at a time.

Only one job runs at a time — the Pi is CPU-bound on a small vision model, and
piling on parallel calls just thrashes the CPU. Progress is exposed via a
simple snapshot the UI polls.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from . import ai, tags
from .files import IMAGE_EXT, resolve


@dataclass
class QueueState:
    pending: list[str] = field(default_factory=list)
    processing: str | None = None
    processing_started: float | None = None
    done: int = 0
    failed: int = 0
    last_error: str = ""
    last_caption: str = ""


_state = QueueState()
_lock = asyncio.Lock()
_wake = asyncio.Event()
_worker_task: asyncio.Task | None = None


def _is_taggable(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXT and path.suffix.lower() != ".svg"


async def enqueue_paths(paths: Iterable[str]) -> int:
    added = 0
    async with _lock:
        for p in paths:
            if p not in _state.pending and p != _state.processing:
                _state.pending.append(p)
                added += 1
    if added:
        _wake.set()
    return added


async def enqueue_folder(path: str, recursive: bool = False) -> int:
    """Enqueue every image inside `path` that isn't already tagged (fresh mtime)."""
    target = resolve(path)
    if not target.is_dir():
        return 0
    to_add: list[str] = []
    if recursive:
        walker = target.rglob("*")
    else:
        walker = target.iterdir()
    for p in walker:
        if not _is_taggable(p):
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        cached = tags.get(str(p), st.st_mtime)
        if cached is None:
            to_add.append(str(p))
    return await enqueue_paths(to_add)


async def snapshot() -> dict:
    async with _lock:
        return {
            "pending": len(_state.pending),
            "processing": _state.processing,
            "processing_since": _state.processing_started,
            "done": _state.done,
            "failed": _state.failed,
            "last_error": _state.last_error,
            "last_caption": _state.last_caption,
        }


async def clear() -> None:
    async with _lock:
        _state.pending.clear()
        _state.done = 0
        _state.failed = 0
        _state.last_error = ""
        _state.last_caption = ""


async def _worker() -> None:
    while True:
        # take next job
        async with _lock:
            job = _state.pending.pop(0) if _state.pending else None
            if job:
                _state.processing = job
                _state.processing_started = time.time()
        if job is None:
            _wake.clear()
            await _wake.wait()
            continue

        try:
            st = os.stat(job)
            result = await ai.describe_image(job)
            tags.put(job, st.st_mtime, result["caption"], result["tags"])
            async with _lock:
                _state.done += 1
                _state.last_caption = result["caption"]
                _state.processing = None
                _state.processing_started = None
        except Exception as exc:  # noqa: BLE001 - keep worker alive
            async with _lock:
                _state.failed += 1
                _state.last_error = f"{Path(job).name}: {exc}"
                _state.processing = None
                _state.processing_started = None


def start(loop: asyncio.AbstractEventLoop | None = None) -> None:
    global _worker_task
    if _worker_task is not None and not _worker_task.done():
        return
    loop = loop or asyncio.get_event_loop()
    _worker_task = loop.create_task(_worker())
