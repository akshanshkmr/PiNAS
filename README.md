# 🧠 Raspberry Pi Homeserver Setup Guide

This repo sets up Docker, Apache reverse proxy, Pi-hole, and a local Streamlit health dashboard on Raspberry Pi.
---

## 🌐 1. Find Your Raspberry Pi IP Address

If your Pi is connected to a **TP-Link Deco network**, you can:

1. Open the **Deco app** on your phone.  
2. Go to **Network → Devices**.  
3. Look for a host named **`pi`** (or similar).  
4. Note the IP address shown (e.g., `192.168.68.50`).

You can then SSH into it:
```bash
ssh akshansh@pi.local
```

---

## 🧩 2. Reset SSH Key Warning (Host Identification Changed)

If you ever see this error when connecting to your Pi:

```
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@    WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!     @
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
```

Run this command **on your computer (not on the Pi)** to remove the old SSH fingerprint:

```bash
ssh-keygen -R pi.local
```

Then reconnect:

```bash
ssh akshansh@pi.local
```


If your Pi has a new IP, replace it accordingly.

---

## ⚙️ 3. Install Git

On your Raspberry Pi:

```bash
sudo apt update
sudo apt install git -y
```

Check installation:
```bash
git --version
```

Configure your identity:
```bash
git config --global user.name "Akshansh"
git config --global user.email "akshanshkmr821@gmail.com"
```

---

## 🧩 4. Install GitHub CLI and Login

GitHub CLI makes login simple — you can log in through your browser.

### Install GitHub CLI
```bash
sudo apt install gh -y
```

### Log in to GitHub
```bash
gh auth login
```

Then follow the prompts:

- Choose **GitHub.com**  
- Choose **HTTPS** for Git operations  
- Select **“Login with a web browser”**  
- Copy the code it shows  
- Visit [https://github.com/login/device](https://github.com/login/device)  
- Paste the code and authorize the login  

✅ Once done, your Pi is now linked to your GitHub account.

You can verify with:
```bash
gh auth status
```

---

## 📦 5. Clone This Repository

Once authenticated, you can clone this repository easily:

```bash
git clone https://github.com/akshanshkmr/homeserver.git
```

---

## ⚙️ 6. Run The Setup

Once authenticated, you can clone this repository easily:

```bash
./setup.sh
```

---

## 🕳️ 7. PiHole Setup

Once authenticated, you can clone this repository easily:

To Set Pi-hole Password:
```sh
sudo docker exec -it pihole pihole setpassword 'your_new_password'
```

To allow iCloudPrivateRelay, set this in `/etc/pihole/pihole.toml` :
```toml
    # Should Pi-hole always reply with NXDOMAIN to A and AAAA queries of mask.icloud.com
    # and mask-h2.icloud.com to disable Apple's iCloud Private Relay to prevent Apple
    # devices from bypassing Pi-hole?
    #
    # This follows the recommendation on
    # https://developer.apple.com/support/prepare-your-network-for-icloud-private-relay
    #
    # Allowed values are:
    #     true or false
    iCloudPrivateRelay = false ### CHANGED, default = true
```

---