"""Thin subprocess wrapper: consistent results, timeouts, no shell interpolation."""

import subprocess

DEFAULT_TIMEOUT = 30


class CmdResult:
    def __init__(self, ok: bool, output: str = "", error: str = "", exit_code: int = 0):
        self.ok = ok
        self.output = output
        self.error = error
        self.exit_code = exit_code

    def to_dict(self) -> dict:
        return {"ok": self.ok, "output": self.output, "error": self.error}


def run(*cmd: str, input_text: str | None = None, timeout: int = DEFAULT_TIMEOUT) -> CmdResult:
    try:
        proc = subprocess.run(
            list(cmd),
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return CmdResult(False, error=f"'{cmd[0]}' timed out after {timeout}s", exit_code=-1)
    except OSError as e:
        return CmdResult(False, error=str(e), exit_code=-1)
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return CmdResult(False, output=out, error=err or f"exit code {proc.returncode}", exit_code=proc.returncode)
    return CmdResult(True, output=out, error=err)


def sudo(*cmd: str, input_text: str | None = None, timeout: int = DEFAULT_TIMEOUT) -> CmdResult:
    return run("sudo", "-n", *cmd, input_text=input_text, timeout=timeout)


def sudo_write_file(path: str, content: str, timeout: int = DEFAULT_TIMEOUT) -> CmdResult:
    """Write a root-owned file without loosening its permissions."""
    return sudo("tee", path, input_text=content, timeout=timeout)
