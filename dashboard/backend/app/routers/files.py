import asyncio
import mimetypes
import os
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from ..security import require_auth
from ..services import files as filesvc, thumbs

router = APIRouter(prefix="/files", tags=["files"], dependencies=[Depends(require_auth)])


def _guard(fn, *args):
    try:
        return fn(*args)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Not found.")
    except (NotADirectoryError, IsADirectoryError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileExistsError:
        raise HTTPException(status_code=409, detail="A file or folder with that name already exists.")
    except OSError as e:
        raise HTTPException(status_code=500, detail=e.strerror or str(e))


class PathBody(BaseModel):
    path: str


class MkdirBody(BaseModel):
    path: str
    name: str


@router.get("/roots")
async def roots():
    return {"roots": await asyncio.to_thread(filesvc.allowed_roots)}


@router.get("/list")
async def list_dir(path: str = Query(...)):
    return await asyncio.to_thread(_guard, filesvc.list_dir, path)


@router.get("/dirsize")
async def dirsize(path: str = Query(...)):
    return await asyncio.to_thread(_guard, filesvc.dir_size, path)


@router.get("/text")
async def text(path: str = Query(...)):
    return {"text": await asyncio.to_thread(_guard, filesvc.read_text, path)}


@router.get("/download")
async def download(path: str = Query(...)):
    target = await asyncio.to_thread(_guard, filesvc.resolve, path)
    if target.is_dir():
        # stream the folder as a zip generated on the fly
        name = (target.name or "nas").replace('"', "")
        disposition = f"attachment; filename=\"{name}.zip\"; filename*=UTF-8''{quote(name)}.zip"
        return StreamingResponse(
            filesvc.zip_dir_stream(target),
            media_type="application/zip",
            headers={"Content-Disposition": disposition},
        )
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Not found.")
    return FileResponse(target, filename=target.name)


@router.get("/thumb")
async def thumb(path: str = Query(...), size: int = Query(240)):
    result = await asyncio.to_thread(_guard, thumbs.thumb, path, size)
    if result is None:
        raise HTTPException(status_code=404, detail="No thumbnail for this file.")
    data, media = result
    # cache aggressively — cached filename embeds mtime so a re-encode busts it
    return Response(content=data, media_type=media, headers={"Cache-Control": "private, max-age=86400"})


@router.get("/raw")
async def raw(path: str = Query(...)):
    # Inline serving for previews. FileResponse honours Range, so <video> seeks.
    target = await asyncio.to_thread(_guard, filesvc.resolve, path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Not a file.")
    if target.suffix.lower() in filesvc.HEIF_EXT:
        # browsers can't decode HEIC — transcode to JPEG for the preview
        if not filesvc.heif_supported():
            raise HTTPException(status_code=415, detail="HEIC preview isn't available (pillow-heif not installed).")
        data = await asyncio.to_thread(_guard, filesvc.heic_to_jpeg, path)
        return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})
    media = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(target, media_type=media)


@router.post("/mkdir")
async def mkdir(body: MkdirBody):
    await asyncio.to_thread(_guard, filesvc.make_dir, body.path, body.name)
    return {"ok": True, "message": f"Created “{body.name}”."}


@router.post("/delete")
async def delete(body: PathBody):
    await asyncio.to_thread(_guard, filesvc.delete, body.path)
    return {"ok": True, "message": "Deleted."}


@router.post("/upload")
async def upload(path: str = Form(...), files: list[UploadFile] = File(...)):
    target_dir = await asyncio.to_thread(_guard, filesvc.resolve, path)
    if not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="Upload target is not a folder.")
    saved = []
    for uf in files:
        name = os.path.basename(uf.filename or "")
        if not name or name in (".", ".."):
            continue
        dest = target_dir / name
        await asyncio.to_thread(_guard, filesvc.resolve, str(dest))  # keep it in-root
        try:
            with open(dest, "wb") as out:
                while chunk := await uf.read(1024 * 1024):
                    out.write(chunk)
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Could not write {name}: {e.strerror or e}")
        saved.append(name)
    if not saved:
        raise HTTPException(status_code=400, detail="No valid files in the upload.")
    return {"ok": True, "saved": saved, "message": f"Uploaded {len(saved)} file(s)."}
