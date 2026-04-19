#!/bin/bash
# Exit on errors so systemd logs show failures clearly.
set -e

# --- Start CPU FAN ---
sudo pinctrl FAN_PWM op dl
