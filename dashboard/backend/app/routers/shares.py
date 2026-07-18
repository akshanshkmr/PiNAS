"""Authenticated share-management endpoints.

The public consumer of shares lives at /s/{token} (see routers/public.py)
and does NOT go through require_auth.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..security import require_auth
from ..services import shares

router = APIRouter(prefix="/shares", tags=["shares"], dependencies=[Depends(require_auth)])


class CreateShareBody(BaseModel):
    path: str
    ttl_seconds: int | None = 86400  # default 24h
    mode: str = "view"                # "view" | "download"
    public: bool = False              # exposes to internet via Funnel
    password: str | None = None
    label: str | None = None


@router.get("")
async def list_shares(user: dict = Depends(require_auth)):
    return {"shares": [
        {
            **s.__dict__,
            "url_path": f"/s/{s.token}",
        }
        for s in await asyncio.to_thread(shares.list_all, user["username"])
    ]}


@router.post("")
async def create_share(body: CreateShareBody, user: dict = Depends(require_auth)):
    try:
        s = await asyncio.to_thread(
            shares.create,
            body.path,
            body.ttl_seconds,
            body.mode,
            body.public,
            user["username"],
            body.password,
            body.label,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "share": {**s.__dict__, "url_path": f"/s/{s.token}"}}


@router.delete("/{token}")
async def revoke(token: str):
    ok = await asyncio.to_thread(shares.delete, token)
    if not ok:
        raise HTTPException(status_code=404, detail="Share not found.")
    return {"ok": True}
