# --- Setting up Pironman 5 MAX service ---
echo "🚀 Setting up Pironman 5 MAX service..."
cd ~
git clone -b max https://github.com/sunfounder/pironman5.git --depth 1
cd ~/pironman5

sudo python3 install.py --skip-reboot
sudo systemctl restart pironman5.service

echo "✅ Pironman service created and started. Please restart"