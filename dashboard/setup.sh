# --- Setup Python environment for dashboard ---
echo "🐍 Setting up Python virtual environment for dashboard..."

sudo apt install -y python3-venv

DASHBOARD_DIR=~/homeserver/dashboard
VENV_DIR=$DASHBOARD_DIR/venv

# Create venv only if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

# Install dependencies in the venv
"$VENV_DIR/bin/pip" install -r $DASHBOARD_DIR/requirements.txt --upgrade

# --- Run dashboard as service ---
echo "🚀 Running dashboard as service..."
sudo cp ./dashboard/dashboard.service /etc/systemd/system/dashboard.service
sudo systemctl daemon-reload
sudo systemctl enable dashboard
sudo systemctl restart dashboard
echo "✅ Dashboard service created and started."