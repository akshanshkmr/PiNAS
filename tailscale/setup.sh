# --- Run tailscale as service ---
sudo cp ./tailscale/tailscale.service /etc/systemd/system/tailscale.service
sudo systemctl daemon-reload
sudo systemctl enable tailscale
sudo systemctl restart tailscale
echo "✅ Tailscale service created and started."