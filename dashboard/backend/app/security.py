"""PAM authentication and HMAC-signed session cookies."""

import hashlib
import hmac
import json
import pwd
import secrets
import time
from pathlib import Path

import pam
from fastapi import HTTPException, Request

SESSION_COOKIE = "pi_auth_session"
SESSION_MAX_AGE = 7 * 24 * 3600  # 7 days

_KEY_PATH = Path(__file__).resolve().parent.parent / "data" / ".session_secret"


def _load_secret_key() -> str:
    try:
        key = _KEY_PATH.read_text().strip()
        if len(key) >= 64:
            return key
    except OSError:
        pass
    _KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(32)
    _KEY_PATH.write_text(key)
    _KEY_PATH.chmod(0o600)
    return key


_SECRET_KEY = _load_secret_key()


def linux_user_options() -> list[str]:
    """Eligible Linux usernames (uid >= 1000, valid login shell)."""
    users = {
        entry.pw_name
        for entry in pwd.getpwall()
        if entry.pw_uid >= 1000 and entry.pw_shell not in ("/usr/sbin/nologin", "/bin/false")
    }
    return sorted(users)


def authenticate(username: str, password: str) -> tuple[bool, str | None]:
    """Verify credentials against PAM. Returns (ok, display_name)."""
    try:
        if pam.pam().authenticate(username, password, service="login"):
            try:
                name = pwd.getpwnam(username).pw_gecos.split(",")[0] or username
            except KeyError:
                name = username
            return True, name
    except Exception:
        pass
    return False, None


def sign_session(username: str, name: str) -> str:
    expires = int(time.time()) + SESSION_MAX_AGE
    payload = json.dumps({"u": username, "n": name, "exp": expires}, separators=(",", ":"))
    sig = hmac.new(_SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_session(token: str | None) -> tuple[str, str] | None:
    """Returns (username, display_name) for a valid unexpired token, else None."""
    if not token or "." not in token:
        return None
    payload, _, sig = token.rpartition(".")
    expected = hmac.new(_SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return None
    if data.get("exp", 0) < int(time.time()):
        return None
    username = data.get("u")
    if not username:
        return None
    return username, data.get("n") or username


def require_auth(request: Request) -> dict:
    """FastAPI dependency: resolve the session cookie or raise 401."""
    result = verify_session(request.cookies.get(SESSION_COOKIE))
    if not result:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"username": result[0], "name": result[1]}
