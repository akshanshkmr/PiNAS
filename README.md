<div align="center">

# 🖥️ Pi Admin

**A self-hosted admin dashboard + NAS for a Raspberry Pi in a Pironman 5 case.**

Live telemetry, RAID & Samba, a file explorer, an in-browser terminal, and case
controls — behind one clean instrument-panel UI.

![Raspberry Pi](https://img.shields.io/badge/Raspberry_Pi-5-A22846?style=flat-square&logo=raspberrypi&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688?style=flat-square&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-60A5FA?style=flat-square&logo=react&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-build-646CFF?style=flat-square&logo=vite&logoColor=white)
![Tailscale](https://img.shields.io/badge/Tailscale-remote_access-242424?style=flat-square&logo=tailscale&logoColor=white)

</div>

<p align="center">
  <img src="docs/dashboard.png" alt="Pi Admin dashboard — System tab" width="920">
</p>

---

## What's inside

| Tab | What it does |
| --- | --- |
| **System** | Live CPU, RAM, temperature, disk, network and processes, streamed over Server-Sent Events (every 2s) |
| **Storage** | RAID create / assemble / mount / repair, Samba shares & users, and per-drive **SMART** health |
| **Files** | Browse the NAS; upload, download (files *and* folders as a streamed `.zip`), preview photos / video / audio / text; sort columns and filter by name |
| **Services** | Start / stop / restart systemd units with live `journalctl` tailing, plus a **Tailscale** panel (status, devices, copy-ready URLs) |
| **Terminal** | A real bash login shell in the browser — xterm.js over a WebSocket-backed PTY |
| **Controls** | Reboot / shutdown, check *and apply* apt updates, Pironman RGB / OLED / case-fan, and the CPU fan |

Fronted by **Apache** (HTTP + SSE + WebSocket) and reachable over **Tailscale**
(HTTPS + SMB). The UI is a dark instrument-panel design that scales down to
mobile. The **Files** media viewer is keyboard-driven — `← →` between items,
`space` play/pause, `↑ ↓` volume, `esc` to close.

## Quick start

On a fresh Raspberry Pi OS install:

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/akshanshkmr/homeserver.git
cd homeserver
./setup.sh
```

`setup.sh` is **idempotent** — re-run it after every `git pull` to rebuild the
frontend, sync backend dependencies, and restart services. Then open
**http://pi.local/status** and sign in with your Linux account.

## Project layout

```text
setup.sh               ← one script that installs / updates everything
apache2/               ← reverse-proxy config
dashboard/
  backend/             ← FastAPI app (PAM auth; system / storage / files /
  │                       services / terminal / controls APIs)
  frontend/            ← React + Vite SPA (dark instrument-panel UI)
```

## Development

```bash
# backend — serves the API + built frontend on :8501
cd dashboard/backend
uv run uvicorn app.main:app --reload --port 8501

# frontend — hot-reload dev server, proxies API calls to :8501
cd dashboard/frontend
npm install
npm run dev
```

## Managed services

| Service     | What it does                              |
| ----------- | ----------------------------------------- |
| `dashboard` | FastAPI backend + SPA on `127.0.0.1:8501` |
| `fan`       | Turns the CPU fan on at boot (one-shot)   |
| `apache2`   | Reverse proxy on port 80                  |

Manage them from the **Services** tab, or with `journalctl -u dashboard -f`.

## Remote access (Tailscale)

`setup.sh` installs Tailscale; the first connection is interactive:

```bash
sudo tailscale up --ssh --advertise-routes=192.168.1.0/24
sudo tailscale serve --bg http://localhost:80
```

Once connected, the **Services** tab shows tailnet status, connected devices,
and ready-to-copy URLs:

- **Dashboard (HTTPS):** `https://<node>.<tailnet>.ts.net/status/`
- **NAS (SMB):** `smb://<node>.<tailnet>.ts.net/<share>`

> The trailing slash on the dashboard URL matters — it hits the app directly
> instead of an Apache redirect. Apache branches the bare-domain redirect on the
> `Host` header so the tailnet URL stays on `https://`.

## Security notes

- Sign-in uses your **Linux user + password** (PAM). The service account needs
  passwordless sudo (default on Raspberry Pi OS) for RAID / Samba / power /
  systemctl / SMART actions.
- The **Terminal** tab plus passwordless sudo is equivalent to an SSH login —
  keep the dashboard on your **LAN or tailnet**, never the public internet.
- The **Files** API is sandboxed to your Samba share paths, mounted array
  mountpoints, and `/mnt/nas`; every path is resolved and checked so `..` and
  symlink escapes are rejected. Uploads / deletes run as the dashboard user.

## Troubleshooting

**SSH host-key warning** after reflashing the Pi — run on *your* computer:

```bash
ssh-keygen -R pi.local
```

**Find the Pi's IP** — in the TP-Link Deco app: Network → Devices → `pi`, or
`ping pi.local`.
