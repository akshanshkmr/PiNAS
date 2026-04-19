# --- Run fan as service ---
sudo cp ./fan/fan.service /etc/systemd/system/fan.service
sudo systemctl daemon-reload
sudo systemctl enable fan
sudo systemctl restart fan
echo "✅ Fan service created and started."