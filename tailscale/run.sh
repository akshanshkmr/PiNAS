#!/bin/bash
# Exit on errors so systemd logs show failures clearly.
set -e

# --- Run tailscale as service ---
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --ssh --advertise-routes=192.168.1.0/24
sudo tailscale serve --bg http://localhost:80