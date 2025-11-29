import psutil
import socket
import time
import os, json, shlex
from pathlib import Path
from textwrap import dedent
import configparser
import streamlit as st

class TempSensors:
    CPU = "cpu_thermal"
    ADC = "rp1_adc"


class PiStats:
    """Collects system metrics for Raspberry Pi."""

    def refresh(self):
        self.cpu = psutil.cpu_percent(interval=None)
        self.ram = psutil.virtual_memory().percent
        self.cpu_temp = self._get_temp(TempSensors.CPU)
        self.adc_temp = self._get_temp(TempSensors.ADC)
        self.disk = psutil.disk_usage('/')
        self.net_io = psutil.net_io_counters()
        self.uptime_val = self._uptime()
        self.processes = self._get_top_processes(10)
        self.ip = self._get_ip()

    def _uptime(self):
        seconds = time.time() - psutil.boot_time()
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        parts = []
        if days: parts.append(f"{days}d")
        if hours: parts.append(f"{hours}h")
        if minutes or not parts: parts.append(f"{minutes}m")
        return " ".join(parts)

    def _get_temp(self, name):
        try:
            return psutil.sensors_temperatures().get(name, [{}])[0].current
        except Exception:
            return 0.0

    def _get_top_processes(self, n):
        plist = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            plist.append(p.info)
        return sorted(plist, key=lambda x: x['cpu_percent'], reverse=True)[:n]

    def _get_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))  # Google DNS (no traffic actually sent)
            return s.getsockname()[0]
        finally:
            s.close()

class PiController:
    def reboot(self):
        os.system("sudo reboot")

    def shutdown(self):
        os.system("sudo shutdown now")

    def check_updates(self):
        return os.popen("apt list --upgradable 2>/dev/null | tail -n +2").read()


class PiNAS:
    def __init__(self):
        self.smb_conf = Path("/etc/samba/smb.conf")
        self.exports = Path("/etc/exports")
        self.smb_shares_store = Path("/etc/pinas_smb_shares.json")
        self.smb_shares = self._load_samba_shares()

    # -------------------- Internal helpers --------------------
    def run(self, *cmd):
        full = " ".join(cmd)
        try:
            return os.popen(full).read()
        except Exception as e:
            return str(e)

    def _load_samba_shares(self):
        if self.smb_shares_store.exists():
            try:
                shares = json.loads(self.smb_shares_store.read_text())
                for share in shares:
                    share.setdefault("allow_guest", False)
                    share.setdefault("read_only", False)
                return shares
            except:
                return []
        return []

    def _save_samba_shares(self):
        try:
            self.smb_shares_store.write_text(json.dumps(self.smb_shares, indent=2))
        except:
            pass

    # -------------------- Disk Discovery --------------------
    def list_disks(self):
        output = self.run("lsblk", "-J", "-o", "NAME,MODEL,SIZE,TYPE,MOUNTPOINT")
        return json.loads(output)["blockdevices"]

    def get_available_disks(self):
        filtered = []
        for d in self.list_disks():
            if d.get("type") == "disk" and not d["name"].startswith("mmcblk0"):
                filtered.append({
                    "device": f"/dev/{d['name']}",
                    "model": d.get("model", "Unknown"),
                    "size": d.get("size", "?")
                })
        return filtered

    # -------------------- RAID Management --------------------
    def raid_status(self):
        return self.run("cat", "/proc/mdstat") + self.run("mdadm", "--detail", "--scan")

    def detect_arrays(self):
        return self.run("mdadm", "--detail", "--scan")

    def restore_detected_arrays(self):
        return self.run("mdadm", "--assemble", "--scan")

    def create_raid(self, disks, level="1", md="/dev/md0"):
        for d in disks:
            self.run("wipefs", "-a", d)
        self.run("mdadm", "--create", md, "--level", level,
                  f"--raid-devices={len(disks)}", *disks, "--force", "--run")
        self.run("mkfs.ext4", "-F", md)
        self.run("mkdir", "-p", "/mnt/nas")
        self.run("mount", md, "/mnt/nas")
        self.run("bash", "-c", "mdadm --detail --scan >> /etc/mdadm/mdadm.conf")
        return f"RAID created at {md}"

    def rebuild_progress(self):
        return self.run("grep", "recovery", "/proc/mdstat")

    def resync_array(self, md="/dev/md0", action="repair"):
        md_name = Path(md).name
        return self.run("bash", "-c", f'echo {action} | sudo tee /sys/block/{md_name}/md/sync_action')

    # -------------------- Dynamic SMB Management --------------------
    def generate_samba_conf(self):
        config = configparser.ConfigParser()

        config["global"] = {
            "workgroup": "WORKGROUP",
            "server string": "PiNAS",
            "map to guest": "Bad User",
            "dns proxy": "no",
            "server min protocol": "SMB2",
            "server max protocol": "SMB3",
        }

        for s in self.smb_shares:
            config[s["name"]] = {
                "path": s["path"],
                "browseable": "yes",
                "read only": "yes" if s.get("read_only") else "no",
                "guest ok": "yes" if s.get("allow_guest") else "no",
                "create mask": "0775",
                "directory mask": "0775",
            }

        with open(self.smb_conf, "w") as f:
            config.write(f)
        with open(self.smb_conf) as f:
            return "".join(f.readlines())

    def show_samba_share_status(self):
        st.code(self.run("smbclient", "-L", "localhost", "-N"))

    def _apply_samba_changes(self):
        self._save_samba_shares()
        conf = self.generate_samba_conf()
        self.samba_restart()
        return conf

    def add_samba_share(self, name, path="/mnt/nas", allow_guest=False, read_only=False):
        self.smb_shares = [s for s in self.smb_shares if s["name"] != name]
        self.smb_shares.append(
            {
                "name": name,
                "path": path,
                "allow_guest": allow_guest,
                "read_only": read_only,
            }
        )
        return self._apply_samba_changes()

    def configure_samba_shares(self, shares):
        self.smb_shares = shares
        return self._apply_samba_changes()

    def remove_samba_share(self, name):
        self.smb_shares = [s for s in self.smb_shares if s['name'] != name]
        return self._apply_samba_changes()

    def samba_restart(self):
        return self.run("sudo", "systemctl", "restart", "smbd")

    def add_samba_user(self, username, password):
        if not (username and password):
            return "Username and password required"
        safe_pass = shlex.quote(password)
        safe_user = shlex.quote(username)
        cmd = (
            f"printf '%s\\n%s\\n' {safe_pass} {safe_pass} | "
            f"sudo smbpasswd -s -a {safe_user}"
        )
        os.system(cmd)
        return "Samba User added successfully"

    def disable_samba_user(self, username):
        if not username:
            return "Username required"
        safe_user = shlex.quote(username)
        exit_code = os.system(f"sudo smbpasswd -d {safe_user}")
        if exit_code == 0:
            return f"Samba user '{username}' disabled."
        return f"Failed to disable Samba user '{username}'."