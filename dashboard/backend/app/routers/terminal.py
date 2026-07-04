"""Interactive shell over a WebSocket, backed by a real PTY.

Runs as the dashboard's service user (the logged-in Linux account). This is a
full login shell — powerful by design — so the socket is gated on the same
signed session cookie as the rest of the API.
"""

import asyncio
import fcntl
import json
import os
import pty
import signal
import struct
import termios

from fastapi import APIRouter, WebSocket

from ..security import SESSION_COOKIE, verify_session

router = APIRouter(tags=["terminal"])


def _set_winsize(fd, rows, cols):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


@router.websocket("/terminal")
async def terminal(ws: WebSocket):
    if not verify_session(ws.cookies.get(SESSION_COOKIE)):
        await ws.close(code=1008)  # policy violation
        return
    await ws.accept()

    # fork a child whose stdio is a new PTY; the child execs immediately so the
    # inherited event loop in the forked image is never touched.
    pid, master_fd = pty.fork()
    if pid == 0:
        try:
            os.chdir(os.path.expanduser("~"))
        except OSError:
            pass
        os.environ["TERM"] = "xterm-256color"
        os.execvp("/bin/bash", ["/bin/bash", "-l"])
        os._exit(1)  # only reached if exec fails

    _set_winsize(master_fd, 24, 80)
    os.set_blocking(master_fd, False)
    loop = asyncio.get_running_loop()
    out_q: asyncio.Queue = asyncio.Queue()

    def on_readable():
        try:
            data = os.read(master_fd, 8192)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            data = b""
        out_q.put_nowait(data)

    loop.add_reader(master_fd, on_readable)

    async def sender():
        while True:
            data = await out_q.get()
            if not data:  # EOF: shell exited
                return
            await ws.send_bytes(data)

    async def receiver():
        while True:
            msg = json.loads(await ws.receive_text())
            kind = msg.get("type")
            if kind == "input":
                os.write(master_fd, msg["data"].encode())
            elif kind == "resize":
                _set_winsize(master_fd, int(msg.get("rows", 24)), int(msg.get("cols", 80)))

    async def waiter():
        await loop.run_in_executor(None, os.waitpid, pid, 0)

    tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver()), asyncio.create_task(waiter())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        loop.remove_reader(master_fd)
        for t in tasks:
            t.cancel()
        try:
            os.close(master_fd)
        except OSError:
            pass
        try:
            os.kill(pid, signal.SIGKILL)
            await loop.run_in_executor(None, os.waitpid, pid, 0)
        except (ProcessLookupError, ChildProcessError):
            pass
        try:
            await ws.close()
        except RuntimeError:
            pass
