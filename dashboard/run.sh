#!/bin/bash
# Activate the dashboard virtual environment and start Streamlit

DASHBOARD_DIR=~/homeserver/dashboard
source "$DASHBOARD_DIR/venv/bin/activate"
exec streamlit run $DASHBOARD_DIR/app.py
