#!/bin/bash
# Exit on errors so systemd logs show failures clearly.
set -e

# Run Streamlit from the uv project environment

DASHBOARD_DIR=~/homeserver/dashboard
export PATH="$HOME/.local/bin:$PATH"
if [ -f "$HOME/.local/bin/env" ]; then
    # Ensure uv install path is loaded for non-interactive service shells.
    source "$HOME/.local/bin/env"
fi
exec uv run --project "$DASHBOARD_DIR" streamlit run "$DASHBOARD_DIR/app.py"
