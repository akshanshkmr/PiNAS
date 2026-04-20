import psutil
import socket
import time
import json
import subprocess
from pathlib import Path
import configparser
import humanize
import datetime


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
        return humanize.naturaldelta(datetime.timedelta(seconds=seconds))   

    def _get_temp(self, name):
        try:
            readings = psutil.sensors_temperatures().get(name, [])
            if readings and hasattr(readings[0], "current"):
                return readings[0].current
            return 0.0
        except Exception:
            return 0.0

    def _get_top_processes(self, n):
        plist = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            plist.append(p.info)
        return sorted(plist, key=lambda x: x['cpu_percent'], reverse=True)[:n]

    def _get_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except OSError:
            return "N/A"
        finally:
            s.close()

class PiController:
    @staticmethod
    def _result(ok, message, details=None):
        return ok, message, details or {}

    def reboot(self):
        proc = subprocess.run(["sudo", "reboot"], capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            return self._result(False, "Failed to trigger reboot.", {"stderr": (proc.stderr or "").strip()})
        return self._result(True, "Reboot command issued.")

    def shutdown(self):
        proc = subprocess.run(["sudo", "shutdown", "now"], capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            return self._result(False, "Failed to trigger shutdown.", {"stderr": (proc.stderr or "").strip()})
        return self._result(True, "Shutdown command issued.")

    def check_updates(self):
        proc = subprocess.run(
            ["apt", "list", "--upgradable"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or "").strip() or "unknown error"
            return self._result(False, "Failed to check updates.", {"stderr": err})
        lines = proc.stdout.splitlines()
        payload = "\n".join(lines[1:]).strip()
        return self._result(True, payload or "System is up-to-date.")

    def get_pironman5_config(self):
        """Get current pironman5 configuration."""
        try:
            output = subprocess.run(
                ["sudo", "pironman5", "-c"],
                capture_output=True,
                text=True,
                check=False,
            )
            if output.returncode != 0:
                return {"error": (output.stderr or "").strip() or "failed to read pironman5 config"}
            return json.loads(output.stdout or "{}")
        except Exception as e:
            return {"error": str(e)}

    def restart_pironman5_service(self):
        """Restart pironman5 service to apply changes."""
        proc = subprocess.run(
            ["sudo", "systemctl", "restart", "pironman5.service"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return self._result(False, "Failed to restart pironman5 service.", {"stderr": (proc.stderr or "").strip()})
        return self._result(True, "Pironman5 service restarted.")

    def apply_pironman5_config(self, config_dict):
        """Apply all pironman5 settings from a config dictionary using a single command."""
        # Build a single command with all flags
        cmd_parts = ["sudo", "pironman5"]

        if "rgb_enable" in config_dict:
            value = "True" if config_dict["rgb_enable"] else "False"
            cmd_parts.extend(["-re", value])
        if "rgb_color" in config_dict:
            cmd_parts.extend(["-rc", str(config_dict["rgb_color"])])
        if "rgb_brightness" in config_dict:
            cmd_parts.extend(["-rb", str(config_dict["rgb_brightness"])])
        if "rgb_style" in config_dict:
            cmd_parts.extend(["-rs", str(config_dict["rgb_style"])])
        if "rgb_speed" in config_dict:
            cmd_parts.extend(["-rp", str(config_dict["rgb_speed"])])
        if "rgb_led_count" in config_dict:
            cmd_parts.extend(["-rl", str(config_dict["rgb_led_count"])])
        if "gpio_fan_mode" in config_dict:
            cmd_parts.extend(["-gm", str(config_dict["gpio_fan_mode"])])
        if "oled_enable" in config_dict:
            value = "True" if config_dict["oled_enable"] else "False"
            cmd_parts.extend(["-oe", value])
        if "oled_rotation" in config_dict:
            cmd_parts.extend(["-or", str(config_dict["oled_rotation"])])
        if "oled_disk" in config_dict:
            cmd_parts.extend(["-od", str(config_dict["oled_disk"])])
        if "oled_network_interface" in config_dict:
            cmd_parts.extend(["-oi", str(config_dict["oled_network_interface"])])
        if "oled_sleep_timeout" in config_dict:
            cmd_parts.extend(["-os", str(config_dict["oled_sleep_timeout"])])

        # Execute single command with all settings
        if len(cmd_parts) > 2: # More than just "sudo pironman5"
            proc = subprocess.run(cmd_parts, capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                return self._result(False, "Failed to apply pironman5 config.", {"stderr": (proc.stderr or "").strip()})

        # Restart service
        ok, msg, details = self.restart_pironman5_service()
        if not ok:
            return self._result(False, msg, details)
        return self._result(True, "Configuration applied and service restarted.")


class PiNAS:
    def __init__(self):
        self.smb_conf = Path("/etc/samba/smb.conf")
        self.exports = Path("/etc/exports")
        self.smb_shares_store = Path("/etc/pinas_smb_shares.json")
        self.smb_shares = self._load_samba_shares()

    # -------------------- Internal helpers --------------------
    @staticmethod
    def _result(ok, message, details=None):
        return ok, message, details or {}

    def run(self, *cmd):
        try:
            proc = subprocess.run(list(cmd), capture_output=True, text=True, check=False)
            out = (proc.stdout or "").strip()
            err = (proc.stderr or "").strip()
            if proc.returncode != 0:
                return self._result(False, f"{' '.join(cmd)} failed.", {"stderr": err, "exit_code": proc.returncode})
            return self._result(True, out)
        except Exception as e:
            return self._result(False, "Command execution failed.", {"stderr": str(e)})

    def _load_samba_shares(self):
        if self.smb_shares_store.exists():
            try:
                shares = json.loads(self.smb_shares_store.read_text())
                for share in shares:
                    share.setdefault("allow_guest", False)
                    share.setdefault("read_only", False)
                return shares
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _save_samba_shares(self):
        try:
            self.smb_shares_store.write_text(json.dumps(self.smb_shares, indent=2))
        except OSError:
            pass

    # -------------------- Disk Discovery --------------------
    def list_disks(self):
        ok, output, _ = self.run("lsblk", "-J", "-o", "NAME,MODEL,SIZE,TYPE,MOUNTPOINT")
        if not ok:
            return []
        try:
            return json.loads(output).get("blockdevices", [])
        except Exception:
            return []

    def get_available_disks(self):
        filtered = []
        for d in self.list_disks():
            name = d.get("name") or ""
            if d.get("type") == "disk" and not name.startswith("mmcblk0"):
                filtered.append({
                    "device": f"/dev/{name}",
                    "model": d.get("model", "Unknown"),
                    "size": d.get("size", "?")
                })
        return filtered

    # -------------------- RAID Management --------------------
    def raid_status(self):
        ok1, mdstat, d1 = self.run("cat", "/proc/mdstat")
        ok2, scan, d2 = self.run("sudo", "mdadm", "--detail", "--scan")
        if not ok1 and not ok2:
            return self._result(False, "Failed to read RAID status.", {"stderr": f"{d1.get('stderr', '')}\n{d2.get('stderr', '')}".strip()})
        return self._result(True, f"{mdstat}\n{scan}".strip())

    def detect_arrays(self):
        return self.run("sudo", "mdadm", "--detail", "--scan")

    def restore_detected_arrays(self):
        return self.run("sudo", "mdadm", "--assemble", "--scan")

    def create_raid(self, disks, level="1", md="/dev/md0"):
        for d in disks:
            ok, _, details = self.run("sudo", "wipefs", "-a", d)
            if not ok:
                return self._result(False, f"Failed wiping filesystem signatures on {d}.", details)
        ok, _, details = self.run(
            "sudo", "mdadm",
            "--create",
            md,
            "--level",
            level,
            f"--raid-devices={len(disks)}",
            *disks,
            "--force",
            "--run",
        )
        if not ok:
            return self._result(False, "Failed creating RAID array.", details)
        ok, _, details = self.run("sudo", "mkfs.ext4", "-F", md)
        if not ok:
            return self._result(False, f"Failed formatting {md}.", details)
        ok, _, details = self.run("sudo", "mkdir", "-p", "/mnt/nas")
        if not ok:
            return self._result(False, "Failed preparing /mnt/nas mountpoint.", details)
        ok, _, details = self.run("sudo", "mount", md, "/mnt/nas")
        if not ok:
            return self._result(False, f"Failed mounting {md} to /mnt/nas.", details)
        ok, scan, details = self.run("sudo", "mdadm", "--detail", "--scan")
        if not ok:
            return self._result(False, "Failed scanning mdadm arrays.", details)
        try:
            with open("/etc/mdadm/mdadm.conf", "a", encoding="utf-8") as fh:
                fh.write(scan + "\n")
        except Exception as e:
            return self._result(False, "Failed writing mdadm config.", {"stderr": str(e)})
        return self._result(True, f"RAID created at {md}.")

    def rebuild_progress(self):
        ok, msg, details = self.run("grep", "recovery", "/proc/mdstat")
        if not ok:
            return self._result(True, "Idle")
        return self._result(True, msg or "Idle", details)

    def resync_array(self, md="/dev/md0", action="repair"):
        md_name = Path(md).name
        try:
            proc = subprocess.run(
                ["sudo", "tee", f"/sys/block/{md_name}/md/sync_action"],
                input=f"{action}\n",
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                err = (proc.stderr or "").strip() or "unknown error"
                return self._result(False, "Failed to set RAID sync action.", {"stderr": err})
            return self._result(True, (proc.stdout or "").strip() or f"Requested '{action}' on /dev/{md_name}")
        except Exception as e:
            return self._result(False, "Failed to issue RAID sync command.", {"stderr": str(e)})

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
        return self.run("smbclient", "-L", "localhost", "-N")

    def _apply_samba_changes(self):
        self._save_samba_shares()
        conf = self.generate_samba_conf()
        ok, msg, details = self.samba_restart()
        if not ok:
            return self._result(False, "Saved share config but failed to restart Samba.", details)
        return self._result(True, "Shares updated and Samba restarted.", {"config": conf})

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

    def samba_service_status(self):
        return self.run("systemctl", "is-active", "smbd")

    def add_samba_user(self, username, password):
        if not (username and password):
            return self._result(False, "Username and password required.")
        try:
            proc = subprocess.run(
                ["sudo", "smbpasswd", "-s", "-a", username],
                input=f"{password}\n{password}\n",
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                err = (proc.stderr or "").strip() or "unknown error"
                return self._result(False, "Failed to add Samba user.", {"stderr": err})
            return self._result(True, "Samba user added successfully.")
        except Exception as e:
            return self._result(False, "Failed to add Samba user.", {"stderr": str(e)})

    def disable_samba_user(self, username):
        if not username:
            return self._result(False, "Username required.")
        proc = subprocess.run(["sudo", "smbpasswd", "-d", username], capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            return self._result(True, f"Samba user '{username}' disabled.")
        return self._result(False, f"Failed to disable Samba user '{username}'.", {"stderr": (proc.stderr or "").strip()})
