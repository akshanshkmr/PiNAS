import asyncio

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from ..security import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    authenticate,
    linux_user_options,
    require_auth,
    sign_session,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.get("/users")
def users():
    return {"users": linux_user_options()}


@router.post("/login")
async def login(body: LoginRequest, response: Response):
    ok, name = await asyncio.to_thread(authenticate, body.username, body.password)
    if not ok:
        await asyncio.sleep(1)  # soften brute-force attempts
        raise HTTPException(status_code=401, detail="Invalid username or password")
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
