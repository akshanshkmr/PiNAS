# --- Setup Python environment for dashboard ---
echo "🐍 Setting up Python virtual environment for dashboard..."
sudo apt install -y python3-venv curl

# --- Setup Samba for NAS ---
echo "Setting up Samba for NAS..."
sudo apt install -y samba samba-common smbclient
sudo chmod 777 /etc/samba/smb.conf # DANGEROUS - RE THINK!

DASHBOARD_DIR=~/homeserver/dashboard

# Install uv if missing
if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Create/update project environment and dependencies from pyproject.toml
uv sync --project "$DASHBOARD_DIR" 

# --- Run dashboard as service ---
echo "🚀 Running dashboard as service..."
sudo cp ./dashboard/dashboard.service /etc/systemd/system/dashboard.service
sudo systemctl daemon-reload
sudo systemctl enable dashboard
sudo systemctl restart dashboard
echo "✅ Dashboard service created and started."