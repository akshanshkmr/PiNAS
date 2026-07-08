# Design: Public share links + local AI photo tagging

Status: **proposal / awaiting approval** · Author: dashboard maintainers · 2026-07-05

Two Google-Drive/Photos–style features for the **Files** tab:

1. **Share links** — hand someone a link to a file or folder that is public for a
   fixed time, optionally reaching the open internet via Tailscale Funnel.
2. **AI auto-tagging** — caption and tag photos/videos with a **local** vision
   model, then search the library by what's *in* the pictures.

Both stay true to the project's ethos: self-hosted, private, tailnet-first.

---

## 1. Share links with expiry

### Principle
Expiry and access control live **in the app**, not in Tailscale. Tailscale only
decides *who can reach the box*; it has no notion of "this link dies in 24h."

### Data model
A tiny SQLite DB at `dashboard/backend/data/shares.db` (gitignored, like the
session secret):

```
share(
  token       TEXT PRIMARY KEY,   -- secrets.token_urlsafe(24) → ~192 bits
  path        TEXT NOT NULL,      -- absolute NAS path, re-validated on every hit
  mode        TEXT NOT NULL,      -- 'view' | 'download'
  password    TEXT,               -- optional; stored as a hash
  public      INTEGER NOT NULL,   -- 0 = LAN/tailnet only, 1 = internet (Funnel)
  created_at  INTEGER NOT NULL,
  expires_at  INTEGER,            -- NULL = no expiry
  hits        INTEGER NOT NULL DEFAULT 0,
  last_seen   INTEGER
)
```

### Endpoints
Authenticated (managing shares — behind the normal session cookie):

- `POST /files/share` `{ path, ttl_seconds, mode, password?, public }` → `{ token, url }`
- `GET  /files/shares` → list active shares (path, expiry, hits, public)
- `DELETE /files/shares/{token}` → revoke (the thing stateless signed tokens can't do)

**Public** (no auth — this is the whole point), mounted at the app root, *not*
under `/api`, so it can be Funnel-scoped cleanly:

- `GET /s/{token}` → a minimal viewer page (single file inline, or a folder
  gallery) styled like the app
- `GET /s/{token}/raw?path=…` → the file bytes (HEIC transcoded, range-supported),
  where `path` must be the shared path or a child of a shared folder
- `GET /s/{token}/zip` → folder as a streamed `.zip` (reuses `zip_dir_stream`)
- `POST /s/{token}/unlock` `{ password }` → sets a short-lived cookie if the
  share is password-protected

### Security (the part that matters)
- **Tokens:** `secrets.token_urlsafe(24)`; unguessable, single-purpose. Never
  reveal the absolute path in the URL.
- **Scope:** a token unlocks exactly its `path` (and children if it's a folder).
  Every request re-runs the existing `resolve()` sandbox check **and** verifies
  the requested path is within the shared subtree. No `..`, no sibling access.
- **Expiry:** enforced server-side against `expires_at`; expired tokens 404.
- **Revocation & kill-switch:** per-token delete, plus a global "disable all
  public shares" toggle in Controls.
- **Abuse:** rate-limit `/s/*` (per-IP), constant-time token compare, optional
  password (hashed), access logging (`hits`, `last_seen`).
- **No auth bleed:** `/s/*` must never accept or require the admin session
  cookie, and the admin API must never be reachable through the public path.

### Reaching the internet — Tailscale Funnel
`tailscale serve` = tailnet-only (private). To let someone *not* on your tailnet
open a link, you need **Funnel** (public HTTPS).

- Scope Funnel to **only the `/s/` path**, leaving the admin UI tailnet-only:
  - tailnet-only:  `tailscale serve --bg http://localhost:80`  (existing)
  - public shares: `tailscale funnel --bg --set-path /s http://localhost:80/s`
  - (exact flags finalized during implementation; the intent is: only `/s/*`
    is world-reachable.)
- **One-time manual setup** (I can't do this non-interactively):
  - Enable HTTPS certs (already done) and add the **Funnel node attribute** in
    the tailnet ACL policy (`nodeAttrs` → `funnel`).
  - Funnel only serves ports **443 / 8443 / 10000**.
- **UX:** creating a share defaults to LAN/tailnet. A "make public" checkbox
  flips `public=1`; only then is the link handed out as the Funnel URL, and only
  then does the app ensure Funnel is serving `/s`.

### Files-tab UX
- Row/preview action **Share** → duration (1h / 24h / 7d / custom), view vs
  download, optional password, and a "public (internet)" checkbox → copyable link.
- A **Shared links** panel: active links with expiry countdown, hit count, and
  Revoke. Expired rows auto-clear.

---

## 2. Local AI auto-tagging

### Where the model runs — on the Pi
LM Studio has no Raspberry Pi build, but the engine does. Recommended:

- **Ollama** (native aarch64, OpenAI-compatible API on `:11434`) running a small
  vision model — **`moondream`** (~1.8B, built for lightweight captioning) is the
  best Pi fit; `qwen2-vl:2b` / `smolvlm` are alternatives.
- Expect **~10–60 s/image on the Pi 5 CPU**, ~2 GB RAM for the model → great for
  background batch tagging, not for instant results.
- **RAM caveat:** this Pi is the 4 GB model and already runs a lot; a 2 GB model
  is tight. Options: run tagging as a low-priority background job, or point the
  same config at a beefier box (see below).

### Backend-agnostic by design
The tagger only speaks the **OpenAI-compatible** `/v1/chat/completions` vision
API, so the "engine" is just config:

```
AI_BASE_URL   e.g. http://localhost:11434/v1     (Ollama on the Pi)
              or   http://oracle:1234/v1          (LM Studio on the tailnet)
AI_MODEL      e.g. moondream  |  qwen2-vl:2b  |  llava
```

Set in Controls; tagging is disabled and clearly greyed out until the endpoint
answers a health check.

### Pipeline
- **Images:** read → (HEIC→JPEG via the transcoder already in `files.py`) →
  downscale (~768px) → base64 → prompt:
  *"Caption this image in one sentence and list 5–10 lowercase tags. Reply as
  JSON: {caption, tags}."* → parse.
- **Videos:** `ffmpeg` extracts a few keyframes → caption those → merge tags.
  (Adds `ffmpeg` to `setup.sh`.)
- **Caching & index:** results in `dashboard/backend/data/tags.db`, keyed by
  `path + mtime`, so nothing re-runs unless a file changes.
- **Queue:** a single background worker with a job queue and progress, so the Pi
  isn't overwhelmed; "Tag this folder" enqueues its images.

### UX
- Files tab: a small tag/caption line under media; a per-folder **"Tag folder"**
  action with a progress indicator.
- **Search** extends the existing filter box to match captions + tags — type
  "birthday cake" or "beach" and matching photos surface. This is the payoff.
- Everything is **fully local** — no image ever leaves the Pi/tailnet.

---

## Phasing (so it can be approved/shipped in slices)

**A. Share links, tailnet/LAN only** — DB, `POST/GET/DELETE /files/share(s)`,
public `/s/{token}` viewer + raw + zip, expiry, revoke, Share UX. *No internet.*

**B. Public shares via Funnel** — `public` flag, Funnel-scoped `/s`, global
kill-switch, docs for the one-time ACL enablement. *Opt-in per link.*

**C. AI tagging — images** — Ollama/`moondream` on the Pi, config + health check,
caption/tags with cache, background worker, search integration.

**D. AI tagging — video** — `ffmpeg` keyframes feeding the same pipeline.

Suggested order: **A → C → B → D** (safe value first; defer internet exposure
and video until the core proves out).

## Open decisions
- Default share TTL and the max allowed (cap runaway public links?).
- Password-protect public shares by default, or leave optional?
- Tagging model: start with `moondream` on the Pi, or point at an external
  OpenAI-compatible endpoint from day one?
- Where to surface tags: inline in the list, in the preview, or a dedicated
  "Library" view with a tag cloud?
