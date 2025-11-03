#!/bin/bash
set -e

# === Raspberry Pi HomeServer Setup ===
# This script installs and configures:
# - Docker
# - Python & Streamlit (for dashboard)
# - Apache (reverse proxy)
# - Pi-hole container
# - Health Dashboard (runs locally)
# ----------------------------------------

echo "🚀 Starting Raspberry Pi HomeServer setup..."

# --- Update system ---
sudo apt update && sudo apt upgrade -y

# --- Install dependencies ---
echo "📦 Installing dependencies..."
sudo apt install -y curl git python3 python3-pip apache2

# --- Setup Docker ---
if ! command -v docker &> /dev/null; then
    echo "🐳 Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
fi

sudo docker compose up -d

# --- Setup Apache ---
echo "🔧 Setting up Apache..."
apache2/setup.sh

# --- Setup dashboard ---
echo "🐍 Setting up dashboard..."
dashboard/setup.sh

echo "🎉 Setup complete!"
echo ""
echo "You can now access your apps at:"
echo "  🌐 http://pi.local         → Home Page"
echo "  🌐 http://pi.local/status  → Status Dashboard"
echo "  🌐 http://pi.local/phihole → Pi-hole"
echo "  🌐 http://pi.local/omv     → OpenMediaVault (Phase 2)"
echo ""
