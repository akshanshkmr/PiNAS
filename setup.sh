#!/bin/bash
set -euo pipefail

# ============================================================
# Raspberry Pi HomeServer — single setup script
#
# Installs and configures everything:
#   - System packages (Apache, Samba, mdadm, smartmontools, ...)
#   - Node.js + builds the React dashboard frontend
#   - uv + Python backend (FastAPI)
#   - systemd services: dashboard, fan
#   - Apache reverse proxy
#   - Pironman 5 case support
#   - Tailscale
#
# Idempotent: safe to re-run after every git pull.
# ============================================================

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USER="${SUDO_USER:-$USER}"
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
NODE_MAJOR_REQUIRED=20

log()  { echo -e "\n\033[1;34m==>\033[0m \033[1m$*\033[0m"; }
ok()   { echo -e "    \033[1;32m✓\033[0m $*"; }

# ------------------------------------------------------------
log "Updating system packages"
sudo apt-get update
sudo apt-get upgrade -y

log "Installing dependencies"
sudo apt-get install -y curl git ca-certificates apache2 \
    mdadm samba samba-common smbclient smartmontools

# ------------------------------------------------------------
log "Setting up Node.js (for the dashboard frontend build)"
node_major() { node -v 2>/dev/null | sed 's/^v\([0-9]*\).*/\1/' || echo 0; }
if ! command -v node >/dev/null 2>&1 || [ "$(node_major)" -lt "$NODE_MAJOR_REQUIRED" ]; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi
ok "node $(node -v)"

log "Setting up uv (for the dashboard backend)"
if ! command -v uv >/dev/null 2>&1 && [ ! -x "$RUN_HOME/.local/bin/uv" ]; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$RUN_HOME/.local/bin:$PATH"
ok "uv $(uv --version | awk '{print $2}')"

# ------------------------------------------------------------
log "Building dashboard frontend"
cd "$REPO_DIR/dashboard/frontend"
if [ -f package-lock.json ]; then
    npm ci --no-audit --no-fund
else
    npm install --no-audit --no-fund
fi
npm run build
ok "Frontend built to dashboard/frontend/dist"

log "Installing dashboard backend"
uv sync --project "$REPO_DIR/dashboard/backend"
ok "Backend environment ready"

# ------------------------------------------------------------
log "Installing systemd services"

sudo tee /etc/systemd/system/dashboard.service >/dev/null <<EOF
[Unit]
Description=HomeServer Admin Dashboard (FastAPI)
After=network.target

[Service]
User=$RUN_USER
WorkingDirectory=$REPO_DIR/dashboard/backend
ExecStart=$RUN_HOME/.local/bin/uv run --project $REPO_DIR/dashboard/backend uvicorn app.main:app --host 127.0.0.1 --port 8501
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=HOME=$RUN_HOME
Environment=PATH=$RUN_HOME/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
EOF

# One-shot: drives the CPU fan pin low (on) at boot. RemainAfterExit stops
# systemd from re-running it in a restart loop.
sudo tee /etc/systemd/system/fan.service >/dev/null <<EOF
[Unit]
Description=CPU fan on at boot
After=multi-user.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/pinctrl FAN_PWM op dl

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable dashboard fan
sudo systemctl restart dashboard fan
ok "dashboard + fan services running"

# ------------------------------------------------------------
log "Configuring Apache reverse proxy"
sudo a2enmod -q proxy proxy_http proxy_wstunnel headers rewrite
sudo cp "$REPO_DIR/apache2/000-default.conf" /etc/apache2/sites-available/000-default.conf
sudo systemctl restart apache2
ok "Apache configured"

# ------------------------------------------------------------
log "Setting up Pironman 5"
if command -v pironman5 >/dev/null 2>&1; then
    ok "Pironman 5 already installed"
else
    if [ ! -d "$RUN_HOME/pironman5" ]; then
        git clone -b max https://github.com/sunfounder/pironman5.git --depth 1 "$RUN_HOME/pironman5"
    fi
    (cd "$RUN_HOME/pironman5" && sudo python3 install.py --skip-reboot)
    sudo systemctl restart pironman5.service
    ok "Pironman 5 installed (reboot recommended)"
fi

# ------------------------------------------------------------
log "Setting up Tailscale"
if ! command -v tailscale >/dev/null 2>&1; then
    curl -fsSL https://tailscale.com/install.sh | sh
fi
if sudo tailscale status >/dev/null 2>&1; then
    sudo tailscale serve --bg http://localhost:80 >/dev/null
    ok "Tailscale connected; serving dashboard over tailnet"
else
    echo "    Tailscale is installed but not connected. To finish:"
    echo "      sudo tailscale up --ssh --advertise-routes=192.168.1.0/24"
    echo "      sudo tailscale serve --bg http://localhost:80"
fi

# ------------------------------------------------------------
echo ""
log "Setup complete!"
echo "  Dashboard : http://pi.local/status"
echo "  SSH       : ssh $RUN_USER@pi.local"
