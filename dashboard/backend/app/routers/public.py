"""Public (unauthenticated) share viewer at /s/{token}.

Mounted at the app root (not under /api) so it can be Funnel-scoped
independently of the admin surface. Every request re-checks expiry, scope,
and (if set) password.
"""

import asyncio
import hashlib
import hmac
import html
import json as jsonlib
import mimetypes
import os
import time
from urllib.parse import quote

from fastapi import APIRouter, Cookie, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response, StreamingResponse

from ..services import files as filesvc, shares, thumbs

router = APIRouter(prefix="/s", tags=["public-share"])

# unlock cookies live per-token — hostile browsers can't reuse them cross-share
_UNLOCK_COOKIE = "pinas_share_unlock"
_UNLOCK_TTL = 6 * 60 * 60  # 6 hours


# ------------------------------------------------------------------ helpers

def _unlock_key(token: str, share_created_at: int) -> str:
    """A per-share HMAC key derived from the (secret) creation timestamp and
    server-side session secret. Revoking + recreating the share resets it."""
    from ..security import _SECRET_KEY  # imported lazily to avoid a cycle
    return hmac.new(
        _SECRET_KEY.encode(),
        f"{token}:{share_created_at}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _is_unlocked(share, cookie_val: str | None) -> bool:
    if not share.has_password:
        return True
    if not cookie_val:
        return False
    parts = cookie_val.split(".")
    if len(parts) != 3:
        return False
    tok, ts, sig = parts
    if tok != share.token:
        return False
    try:
        issued = int(ts)
    except ValueError:
        return False
    if issued + _UNLOCK_TTL < int(time.time()):
        return False
    expected = hmac.new(
        _unlock_key(share.token, share.created_at).encode(),
        f"{tok}.{ts}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, sig)


def _new_unlock_cookie(share) -> str:
    ts = str(int(time.time()))
    key = _unlock_key(share.token, share.created_at)
    sig = hmac.new(key.encode(), f"{share.token}.{ts}".encode(), hashlib.sha256).hexdigest()
    return f"{share.token}.{ts}.{sig}"


def _load(token: str):
    s = shares.get(token)
    if not s or shares.is_expired(s):
        raise HTTPException(status_code=404, detail="Share not found or expired.")
    return s


def _viewer_url(token: str, path: str, slideshow: bool = False) -> str:
    qs = f"?p={quote(path)}"
    if slideshow:
        qs += "&slideshow=1"
    return f"/s/{token}{qs}"


def _gallery_context(share, target, slideshow: bool):
    """When a media file is opened inside a folder-share, describe its
    siblings so the viewer can render Back / Prev / Next / Slideshow.

    Returns a dict with rendered URLs and the current index, or None when
    the share is a single file (nothing to navigate)."""
    if not share.is_dir:
        return None
    parent = target.parent
    try:
        shares.scope_check(share, str(parent))
    except PermissionError:
        return None
    try:
        listing = filesvc.list_dir(str(parent))
    except Exception:
        return None
    gallery = [e for e in listing["entries"] if e["kind"] in ("image", "video")]
    if not gallery:
        return None
    paths = [e["path"] for e in gallery]
    try:
        idx = paths.index(str(target))
    except ValueError:
        return None
    items = [
        {
            "path": e["path"],
            "name": e["name"],
            "kind": e["kind"],
            "raw": f"/s/{share.token}/raw?p={quote(e['path'])}",
            "download": f"/s/{share.token}/download?p={quote(e['path'])}",
            "viewer": _viewer_url(share.token, e["path"]),
        }
        for e in gallery
    ]
    return {
        "token": share.token,
        "back": _viewer_url(share.token, str(parent)),
        "index": idx,
        "total": len(items),
        "items": items,
        "slideshow": slideshow,
    }


# ------------------------------------------------------------------ viewer

_PAGE_CSS = """
    :root { color-scheme: dark; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; background:
      radial-gradient(60% 55% at 20% 15%, #0e2542, transparent 65%),
      radial-gradient(45% 45% at 85% 90%, #082226, transparent 70%), #080d17;
      color: #dbe4f2; font-family: 'Space Mono', ui-monospace, monospace; padding: 40px 24px; }
    .wrap { max-width: 1080px; margin: 0 auto; }
    h1 { font-family: 'Space Grotesk', system-ui, sans-serif;
      font-size: clamp(28px, 4vw, 42px); margin: 0 0 4px;
      text-shadow: 0 0 22px rgba(96,165,250,0.28); }
    .sub { color: #6b7d9e; font-size: 11px; letter-spacing: 0.2em; text-transform: uppercase; margin-bottom: 26px; }
    .card { background: #0d1626; border: 1px solid #182338; padding: 22px; border-radius: 3px; }
    .action { display: inline-block; padding: 10px 18px; background: rgba(96,165,250,0.14);
      color: #dbeafe; border: 1px solid rgba(96,165,250,0.55); border-radius: 2px;
      text-decoration: none; margin: 6px 8px 0 0; font-family: 'Space Mono', monospace; }
    .action:hover { color: #fff; box-shadow: 0 0 10px rgba(96,165,250,0.35); }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 14px; margin-top: 18px; }
    .tile { display: block; text-decoration: none; color: inherit; border: 1px solid #182338;
      border-radius: 3px; overflow: hidden; background: #0d1626; transition: border-color 0.14s; }
    .tile:hover { border-color: #60a5fa; }
    .th { aspect-ratio: 1/1; background: #060a12; display: grid; place-items: center; overflow: hidden; }
    .th img { width: 100%; height: 100%; object-fit: cover; display: block; }
    .th-fallback { color: #6b7d9e; font-size: 26px; opacity: 0.6; }
    .th-folder { width: 44%; height: 44%; color: #60a5fa; opacity: 0.85; }
    .meta { padding: 8px 10px; font-size: 12px; }
    .meta .n { color: #dbe4f2; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .meta .s { color: #6b7d9e; font-size: 10px; margin-top: 2px; letter-spacing: 0.04em; }
    input[type=password] { font-family: inherit; padding: 10px 12px; background: #060a12;
      border: 1px solid #182338; color: #dbe4f2; border-radius: 2px; }
    form { display: inline-flex; gap: 10px; align-items: center; }
    .footer { color: #3d4c66; font-size: 11px; letter-spacing: 0.16em;
      text-transform: uppercase; margin-top: 30px; text-align: center; }
    img.hero { max-width: 100%; max-height: 78vh; border-radius: 3px; display: block; margin: 0 auto; }
    video, audio { max-width: 100%; display: block; margin: 0 auto; }
    .navbar { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 0 0 18px; }
    .navbar .action { margin: 0; padding: 8px 14px; font-size: 12px; }
    .navbar .action.is-off { opacity: 0.35; pointer-events: none; cursor: not-allowed; }
    .navbar .counter { color: #6b7d9e; font-size: 11px; letter-spacing: 0.12em;
      text-transform: uppercase; margin-left: auto; font-family: 'Space Mono', monospace; }
    .navbar .spacer { width: 8px; }
    .kbdhint { color: #3d4c66; font-size: 10px; letter-spacing: 0.16em;
      text-transform: uppercase; margin-top: 10px; text-align: center; }
    .kbdhint kbd { display: inline-block; padding: 1px 6px; margin: 0 2px;
      border: 1px solid #263248; border-radius: 2px; color: #6b7d9e; font-size: 10px; }
    /* Fullscreen paints the whole viewport black so images sit centered. */
    body:fullscreen, body:-webkit-full-screen { background: #000; padding: 0; }
    body:fullscreen .wrap, body:-webkit-full-screen .wrap {
      max-width: none; height: 100vh; display: grid; grid-template-rows: auto 1fr auto; }
    body:fullscreen h1, body:fullscreen .sub, body:fullscreen .footer,
    body:fullscreen .kbdhint, body:-webkit-full-screen h1, body:-webkit-full-screen .sub,
    body:-webkit-full-screen .footer, body:-webkit-full-screen .kbdhint { display: none; }
    body:fullscreen .card, body:-webkit-full-screen .card {
      background: transparent; border: none; padding: 0; display: grid; place-items: center; }
    body:fullscreen img.hero, body:-webkit-full-screen img.hero,
    body:fullscreen video, body:-webkit-full-screen video {
      max-width: 100vw; max-height: 100vh; }
    body:fullscreen .navbar, body:-webkit-full-screen .navbar {
      position: fixed; top: 14px; right: 14px; z-index: 10; margin: 0;
      background: rgba(8,13,23,0.72); backdrop-filter: blur(6px);
      padding: 6px; border-radius: 3px; opacity: 0.15; transition: opacity 0.2s; }
    body:fullscreen .navbar:hover, body:-webkit-full-screen .navbar:hover { opacity: 1; }
    body:fullscreen .card > div:last-child, body:-webkit-full-screen .card > div:last-child { display: none; }
"""


def _pretty_bytes(n: int) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {u}" if u != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} PB"


def _page_shell(title: str, body: str, extra_css: str = "") -> HTMLResponse:
    html_body = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{html.escape(title)} — PiNAS</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg"/>
<style>{_PAGE_CSS}{extra_css}</style>
</head><body><div class="wrap">{body}
<div class="footer">shared via pinas</div>
</div></body></html>"""
    return HTMLResponse(html_body)


def _password_prompt(share, error: str = "") -> HTMLResponse:
    err = f'<div style="color:#ff6b6b;margin:6px 0 14px;font-size:13px">{html.escape(error)}</div>' if error else ""
    body = f"""
      <h1>Protected</h1>
      <div class="sub">This share is password-protected</div>
      <div class="card">
        <p style="margin:0 0 14px;color:#6b7d9e;">Enter the password to view.</p>
        {err}
        <form method="post" action="/s/{html.escape(share.token)}/unlock">
          <input type="password" name="password" autocomplete="off" autofocus placeholder="Password"/>
          <button class="action" type="submit">Unlock →</button>
        </form>
      </div>
    """
    return _page_shell("Protected share", body)


@router.get("/{token}", response_class=HTMLResponse)
async def viewer(token: str, request: Request, subpath: str | None = Query(default=None, alias="p"),
                 slideshow: int = Query(default=0),
                 unlock: str | None = Cookie(default=None, alias=_UNLOCK_COOKIE)):
    s = _load(token)
    if not _is_unlocked(s, unlock):
        return _password_prompt(s)

    scope_path = s.path
    target_path = subpath or scope_path
    try:
        target = shares.scope_check(s, target_path)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Path not in share.")

    await asyncio.to_thread(shares.bump_hit, s.token)

    # Folder view
    if target.is_dir():
        try:
            listing = await asyncio.to_thread(filesvc.list_dir, str(target))
        except Exception:
            raise HTTPException(status_code=500, detail="Could not read folder.")
        entries = listing["entries"]
        # crumbs relative to scope root
        scope = os.path.realpath(scope_path)
        rel = os.path.relpath(str(target), scope) if str(target) != scope else ""
        crumbs = [(scope.split("/")[-1] or "share", "")]
        if rel and rel != ".":
            parts = rel.split(os.sep)
            for i, part in enumerate(parts):
                crumbs.append((part, os.path.join(*parts[: i + 1])))

        crumb_html = " / ".join(
            f'<a class="action" style="padding:4px 10px;font-size:12px" href="/s/{s.token}?p={quote(os.path.join(scope, sub) if sub else scope)}">{html.escape(name)}</a>'
            for name, sub in crumbs
        )

        tile_html_parts = []
        for e in entries:
            name = html.escape(e["name"])
            href = f'/s/{s.token}?p={quote(e["path"])}'
            if e["is_dir"]:
                thumb = (
                    '<svg class="th-folder" viewBox="0 0 24 24" fill="none" '
                    'stroke="currentColor" stroke-width="1.5" stroke-linejoin="round">'
                    '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4.6l2 2h8.4A1.5 1.5 0 0 1 21 8.5v9A1.5 1.5 0 0 1 19.5 19h-15A1.5 1.5 0 0 1 3 17.5z"/>'
                    '</svg>'
                )
                meta = "folder"
            elif e["kind"] in ("image", "video"):
                thumb = f'<img loading="lazy" src="/s/{s.token}/thumb?p={quote(e["path"])}&size=240" alt=""/>'
                meta = _pretty_bytes(e["size"])
            else:
                glyph = {"audio": "♪", "text": "≡", "file": "·"}.get(e["kind"], "·")
                thumb = f'<div class="th-fallback">{glyph}</div>'
                meta = _pretty_bytes(e["size"])
            tile_html_parts.append(
                f'<a class="tile" href="{href}">'
                f'<div class="th">{thumb}</div>'
                f'<div class="meta"><div class="n">{name}</div><div class="s">{meta}</div></div>'
                f'</a>'
            )
        actions = f'<a class="action" href="/s/{s.token}/zip">Download all as .zip</a>' if s.mode == "download" or True else ""
        body = f"""
          <h1>{html.escape(s.label or os.path.basename(scope) or "Shared folder")}</h1>
          <div class="sub">{len(entries)} items · {crumb_html}</div>
          {actions}
          <div class="grid">{"".join(tile_html_parts) or '<div class="card">This folder is empty.</div>'}</div>
        """
        return _page_shell(os.path.basename(scope) or "share", body)

    # Single-file preview
    kind = filesvc._kind(target)
    raw_url = f"/s/{s.token}/raw?p={quote(str(target))}"
    dl_url = f"/s/{s.token}/download?p={quote(str(target))}"

    ctx = _gallery_context(s, target, bool(slideshow))

    # Non-gallery media (audio, plain files) still gets the simple, non-JS view.
    if not ctx:
        if kind == "image":
            preview = f'<img class="hero" src="{raw_url}" alt=""/>'
        elif kind == "video":
            preview = f'<video src="{raw_url}" controls autoplay style="max-height:78vh"></video>'
        elif kind == "audio":
            preview = f'<audio src="{raw_url}" controls autoplay></audio>'
        else:
            preview = '<div class="card">Preview not available. Download the file to open it.</div>'
        body = f"""
          <h1>{html.escape(target.name)}</h1>
          <div class="sub">{_pretty_bytes(target.stat().st_size)}</div>
          <div class="card">{preview}
            <div style="margin-top:14px">
              <a class="action" href="{dl_url}">Download</a>
            </div>
          </div>
        """
        return _page_shell(target.name, body)

    # Gallery view — client-side navigation keeps fullscreen intact and
    # avoids a full-page reload between slideshow frames.
    ss_label = "⏸ Pause" if ctx["slideshow"] else "▶ Slideshow"
    navbar = f"""
      <div class="navbar">
        <a class="action" href="{ctx['back']}">← Folder</a>
        <span class="spacer"></span>
        <a class="action" href="#" id="prevBtn">← Prev</a>
        <a class="action" href="#" id="nextBtn">Next →</a>
        <a class="action" href="#" id="ssBtn">{ss_label}</a>
        <a class="action" href="#" id="fsBtn">⛶ Fullscreen</a>
        <span class="counter"><span id="counter">{ctx['index'] + 1} / {ctx['total']}</span></span>
      </div>
    """
    js_ctx = jsonlib.dumps({
        "token": ctx["token"],
        "back": ctx["back"],
        "items": ctx["items"],
        "index": ctx["index"],
        "slideshow": ctx["slideshow"],
    }).replace("</", "<\\/")
    body = f"""
      {navbar}
      <h1 id="heroName">{html.escape(target.name)}</h1>
      <div class="sub" id="heroMeta">{_pretty_bytes(target.stat().st_size)}</div>
      <div class="card" id="heroCard">
        <img id="heroImg" class="hero" alt="" style="display:none"/>
        <video id="heroVid" controls style="max-height:78vh;display:none"></video>
        <div style="margin-top:14px">
          <a class="action" id="dlBtn" href="{dl_url}">Download</a>
        </div>
      </div>
      <div class="kbdhint"><kbd>←</kbd> <kbd>→</kbd> navigate · <kbd>F</kbd> fullscreen · <kbd>Space</kbd> play/pause · <kbd>Esc</kbd> back</div>
      <script>
        (function() {{
          const g = {js_ctx};
          let cur = g.index;
          const items = g.items;
          const heroImg = document.getElementById('heroImg');
          const heroVid = document.getElementById('heroVid');
          const heroName = document.getElementById('heroName');
          const dlBtn = document.getElementById('dlBtn');
          const counter = document.getElementById('counter');
          const ssBtn = document.getElementById('ssBtn');
          const fsBtn = document.getElementById('fsBtn');
          let slideshow = !!g.slideshow;
          let ssTimer = null;

          function preload(i) {{
            const it = items[(i + items.length) % items.length];
            if (it.kind === 'image') {{ const img = new Image(); img.src = it.raw; }}
          }}
          function render() {{
            const it = items[cur];
            heroName.textContent = it.name;
            dlBtn.href = it.download;
            counter.textContent = (cur + 1) + ' / ' + items.length;
            // Reflect the current item in the URL so refresh + link-copy still work.
            const qs = new URLSearchParams(location.search);
            qs.set('p', it.path);
            if (slideshow) qs.set('slideshow', '1'); else qs.delete('slideshow');
            history.replaceState(null, '', location.pathname + '?' + qs.toString());
            document.title = it.name + ' — PiNAS';
            if (it.kind === 'image') {{
              heroVid.pause();
              heroVid.removeAttribute('src');
              heroVid.style.display = 'none';
              heroImg.style.display = '';
              heroImg.src = it.raw;
            }} else {{
              heroImg.removeAttribute('src');
              heroImg.style.display = 'none';
              heroVid.style.display = '';
              heroVid.src = it.raw;
              heroVid.play().catch(() => {{}});
            }}
            preload(cur + 1);
          }}
          function go(delta) {{ cur = (cur + delta + items.length) % items.length; render(); scheduleSs(); }}

          function scheduleSs() {{
            if (ssTimer) {{ clearTimeout(ssTimer); ssTimer = null; }}
            if (!slideshow) return;
            const it = items[cur];
            if (it.kind === 'image') {{
              ssTimer = setTimeout(() => go(1), 4000);
            }}
            // videos advance on 'ended' (wired once below)
          }}
          heroVid.addEventListener('ended', () => {{ if (slideshow) go(1); }});

          function setSlideshow(on) {{
            slideshow = on;
            ssBtn.textContent = on ? '⏸ Pause' : '▶ Slideshow';
            const qs = new URLSearchParams(location.search);
            if (on) qs.set('slideshow', '1'); else qs.delete('slideshow');
            history.replaceState(null, '', location.pathname + '?' + qs.toString());
            scheduleSs();
          }}

          document.getElementById('prevBtn').addEventListener('click', e => {{ e.preventDefault(); go(-1); }});
          document.getElementById('nextBtn').addEventListener('click', e => {{ e.preventDefault(); go(1); }});
          ssBtn.addEventListener('click', e => {{ e.preventDefault(); setSlideshow(!slideshow); }});

          const isFs = () => !!(document.fullscreenElement || document.webkitFullscreenElement);
          const enterFs = () => {{ const el = document.body; (el.requestFullscreen || el.webkitRequestFullscreen || function(){{}}).call(el); }};
          const exitFs = () => {{ (document.exitFullscreen || document.webkitExitFullscreen || function(){{}}).call(document); }};
          fsBtn.addEventListener('click', e => {{ e.preventDefault(); if (isFs()) exitFs(); else enterFs(); }});
          document.addEventListener('fullscreenchange', () => {{ fsBtn.textContent = isFs() ? '⛶ Exit' : '⛶ Fullscreen'; }});

          window.addEventListener('keydown', e => {{
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
            if (e.key === 'ArrowLeft') {{ e.preventDefault(); go(-1); }}
            else if (e.key === 'ArrowRight') {{ e.preventDefault(); go(1); }}
            else if (e.key === 'Escape' && !isFs()) {{ e.preventDefault(); location.href = g.back; }}
            else if (e.key === 'f' || e.key === 'F') {{ e.preventDefault(); fsBtn.click(); }}
            else if (e.key === ' ') {{ e.preventDefault(); setSlideshow(!slideshow); }}
          }});

          render();
          scheduleSs();
        }})();
      </script>
    """
    return _page_shell(target.name, body)


class UnlockForm(dict):
    password: str


@router.post("/{token}/unlock")
async def unlock(token: str, password: str = Form(...)):
    s = _load(token)
    if not s.has_password:
        return RedirectResponse(f"/s/{token}", status_code=303)
    if not await asyncio.to_thread(shares.check_password, s, password):
        return _password_prompt(s, "Incorrect password.")
    resp = RedirectResponse(f"/s/{token}", status_code=303)
    resp.set_cookie(
        _UNLOCK_COOKIE, _new_unlock_cookie(s),
        max_age=_UNLOCK_TTL, httponly=True, samesite="lax", path=f"/s/{token}",
    )
    return resp


@router.get("/{token}/thumb")
async def public_thumb(token: str, p: str = Query(...), size: int = 240,
                       unlock: str | None = Cookie(default=None, alias=_UNLOCK_COOKIE)):
    s = _load(token)
    if not _is_unlocked(s, unlock):
        raise HTTPException(status_code=401, detail="Locked.")
    try:
        target = shares.scope_check(s, p)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Out of scope.")
    result = await asyncio.to_thread(thumbs.thumb, str(target), size)
    if not result:
        raise HTTPException(status_code=404)
    data, media = result
    return Response(content=data, media_type=media,
                    headers={"Cache-Control": "private, max-age=3600"})


@router.get("/{token}/raw")
async def public_raw(token: str, p: str = Query(...),
                     unlock: str | None = Cookie(default=None, alias=_UNLOCK_COOKIE)):
    s = _load(token)
    if not _is_unlocked(s, unlock):
        raise HTTPException(status_code=401, detail="Locked.")
    try:
        target = shares.scope_check(s, p)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Out of scope.")
    if not target.is_file():
        raise HTTPException(status_code=404)
    # HEIC transcode for browser preview parity
    if target.suffix.lower() in filesvc.HEIF_EXT and filesvc.heif_supported():
        data = await asyncio.to_thread(filesvc.heic_to_jpeg, str(target))
        return Response(content=data, media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=3600"})
    media = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(target, media_type=media)


@router.get("/{token}/download")
async def public_download(token: str, p: str | None = Query(default=None),
                          unlock: str | None = Cookie(default=None, alias=_UNLOCK_COOKIE)):
    s = _load(token)
    if not _is_unlocked(s, unlock):
        raise HTTPException(status_code=401, detail="Locked.")
    try:
        target = shares.scope_check(s, p or s.path)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Out of scope.")
    if target.is_dir():
        # zip a folder inside the share
        name = (target.name or "share").replace('"', "")
        disposition = f'attachment; filename="{name}.zip"; filename*=UTF-8\'\'{quote(name)}.zip'
        return StreamingResponse(
            filesvc.zip_dir_stream(target),
            media_type="application/zip",
            headers={"Content-Disposition": disposition},
        )
    if not target.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(target, filename=target.name)


@router.get("/{token}/zip")
async def public_zip(token: str, unlock: str | None = Cookie(default=None, alias=_UNLOCK_COOKIE)):
    """Convenience alias: /zip streams the whole shared folder."""
    s = _load(token)
    if not _is_unlocked(s, unlock):
        raise HTTPException(status_code=401, detail="Locked.")
    if not s.is_dir:
        raise HTTPException(status_code=400, detail="Share is a single file — use /download.")
    return await public_download(token, s.path, unlock)
