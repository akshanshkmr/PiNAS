# --- Enable Apache proxy modules ---
echo "🔧 Enabling Apache modules..."
sudo a2enmod proxy proxy_http proxy_html headers rewrite
sudo systemctl reload apache2

# --- Copy Apache configuration from repo ---
echo "⚙️ Setting up Apache reverse proxy..."
if [ -f "./apache2/000-default.conf" ]; then
    sudo cp ./apache2/000-default.conf /etc/apache2/sites-available/000-default.conf
else
    echo "❌ ERROR: apache2/000-default.conf not found in repo!"
    exit 1
fi

# --- Restart Apache to apply new config ---
sudo systemctl restart apache2
echo "✅ Apache reverse proxy configured."