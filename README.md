# 🧠 Raspberry Pi Homeserver

Turns a Raspberry Pi (in a Pironman 5 case) into a homeserver with:

- **Admin dashboard** — React + FastAPI app at `http://pi.local/status`
  - **System** — live CPU, RAM, temperature, disk, network, and processes,
    streamed over Server-Sent Events (updates every 2s)
  - **Storage** — RAID create/assemble/mount/repair, Samba shares and users,
    and per-drive SMART health
  - **Files** — browse the NAS, upload and download files, and preview photos,
    video, audio, and text in the browser, with a keyboard-driven media viewer
    (← → between items, space play/pause, ↑ ↓ volume, esc close)
  - **Services** — start/stop/restart systemd units with live log tailing, and
    a Tailscale panel (status, devices, copy-ready remote URLs)
  - **Terminal** — a full bash login shell in the browser (xterm.js over a
    WebSocket-backed PTY), running as your Linux user
  - **Controls** — reboot/shutdown, check *and apply* apt updates, Pironman
    RGB/OLED/case-fan settings, and CPU fan
- **Apache** — reverse proxy on port 80 (HTTP, SSE, and WebSocket)
- **Tailscale** — remote access over your tailnet (HTTPS + SMB)

The UI is a dark instrument-panel design that works down to mobile.

## Layout

```
setup.sh               ← one script that installs/updates everything
apache2/               ← reverse proxy config
dashboard/
  backend/             ← FastAPI app (PAM auth, system/NAS/services/controls API)
  frontend/            ← React + Vite SPA
```

## Install

On a fresh Raspberry Pi OS install:

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/akshanshkmr/homeserver.git
cd homeserver
./setup.sh
```

`setup.sh` is idempotent — re-run it after every `git pull` to rebuild the
frontend, sync backend dependencies, and restart services.

The dashboard signs you in with your **Linux user and password** (PAM). The
service account needs passwordless sudo (default on Raspberry Pi OS) for
RAID/Samba/power/systemctl/SMART operations. Note that the Terminal tab and
passwordless sudo together give the same power as an SSH login — keep the
dashboard on the LAN or your tailnet, not the public internet.

The **Files** tab browses your Samba share paths, mounted array mountpoints,
and `/mnt/nas` — every request is sandboxed to those roots (no `..` or symlink
escapes). Uploads and deletes run as the dashboard's Linux user, so that user
needs write access to the folder. Media serving supports HTTP range requests,
so video scrubs and seeks in the preview player.

## Dashboard development

Backend (serves API + built frontend on port 8501):

```bash
cd dashboard/backend
uv run uvicorn app.main:app --reload --port 8501
```

Frontend dev server with hot reload (proxies API calls to :8501):

```bash
cd dashboard/frontend
npm install
npm run dev
```

## Services

| Service     | What it does                              |
| ----------- | ----------------------------------------- |
| `dashboard` | FastAPI backend + SPA on `127.0.0.1:8501` |
| `fan`       | Turns the CPU fan on at boot (one-shot)   |
| `apache2`   | Reverse proxy on port 80                  |

These are managed from the dashboard's **Services** tab, or with
`journalctl -u dashboard -f`.

## Tailscale

`setup.sh` installs Tailscale. First-time connection is interactive:

```bash
sudo tailscale up --ssh --advertise-routes=192.168.1.0/24
sudo tailscale serve --bg http://localhost:80
```

Once connected, the dashboard's **Services** tab shows the tailnet status,
connected devices, and the ready-to-copy remote URLs:

- Dashboard over HTTPS: `https://<node>.<tailnet>.ts.net/status/`
- NAS over SMB: `smb://<node>.<tailnet>.ts.net/<share>`

The trailing slash on the dashboard URL matters — it hits the app directly
instead of an Apache redirect. Apache also rewrites the bare-domain redirect
based on the `Host` header so the tailnet URL stays on `https://`.

## Troubleshooting

**SSH host key warning** after reflashing the Pi — on your computer:

```bash
ssh-keygen -R pi.local
```

**Find the Pi's IP** — in the TP-Link Deco app: Network → Devices → `pi`,
or `ping pi.local`.
