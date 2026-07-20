import asyncio
import math

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from ..security import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    authenticate,
    linux_user_options,
    require_auth,
    sign_session,
)
from ..services.ratelimit import login_ip, login_user

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


def _client_ip(request: Request) -> str:
    """First IP from X-Forwarded-For (Apache reverse proxy sets this)
    falling back to the socket peer. `.strip()` because XFF can have spaces."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",", 1)[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


@router.get("/users")
def users():
    return {"users": linux_user_options()}


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response):
    ip = _client_ip(request)
    # Preflight check on BOTH counters — either lockout is enough to refuse.
    for key, counter in ((ip, login_ip), (body.username, login_user)):
        wait = counter.retry_after(key)
        if wait > 0:
            minutes = max(1, math.ceil(wait / 60))
            raise HTTPException(
                status_code=429,
                detail=f"Too many failed logins. Try again in about {minutes} minute{'s' if minutes != 1 else ''}.",
                headers={"Retry-After": str(int(wait) + 1)},
            )

    ok, name = await asyncio.to_thread(authenticate, body.username, body.password)
    if not ok:
        login_ip.record_failure(ip)
        login_user.record_failure(body.username)
        # Constant slowdown still helps against fast parallel guessing.
        await asyncio.sleep(1)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Success wipes both counters — one right password shouldn't leave a
    # legitimate user paying for a typo storm.
    login_ip.clear(ip)
    login_user.clear(body.username)

    response.set_cookie(
        SESSION_COOKIE,
        sign_session(body.username, name),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return {"username": body.username, "name": name}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(require_auth)):
    return user
