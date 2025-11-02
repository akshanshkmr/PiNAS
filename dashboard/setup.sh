# --- Setup Python environment for dashboard ---
echo "🐍 Setting up Python virtual environment for dashboard..."

sudo apt install -y python3-venv

DASHBOARD_DIR=~/homeserver/dashboard
VENV_DIR=$DASHBOARD_DIR/venv

mkdir -p "$DASHBOARD_DIR"

# Create venv only if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

# Install dependencies in the venv
"$VENV_DIR/bin/pip" install -r $DASHBOARD_DIR/requirements.txt --upgrade

echo "✅ Dashboard environment set up."
