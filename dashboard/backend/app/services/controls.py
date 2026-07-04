"""Power, package updates, Pironman case and CPU fan control."""

import json
import os
import subprocess

from .shell import CmdResult, run, sudo

FAN_MODES = ["Always On", "Performance", "Cool", "Balanced", "Quiet"]
RGB_STYLES = ["solid", "breathing", "flow", "flow_reverse", "rainbow", "rainbow_reverse", "hue_cycle"]

# pironman5 CLI flag per config key
_PIRONMAN_FLAGS = {
    "rgb_enable": "-re",
    "rgb_color": "-rc",
    "rgb_brightness": "-rb",
    "rgb_style": "-rs",
    "rgb_speed": "-rp",
    "rgb_led_count": "-rl",
    "gpio_fan_mode": "-gm",
    "oled_enable": "-oe",
    "oled_rotation": "-or",
    "oled_disk": "-od",
    "oled_network_interface": "-oi",
    "oled_sleep_timeout": "-os",
}


def reboot() -> CmdResult:
    return sudo("shutdown", "-r", "+0")


def shutdown() -> CmdResult:
    return sudo("shutdown", "-h", "+0")


def check_updates() -> dict:
    res = run("apt", "list", "--upgradable", timeout=60)
    if not res.ok:
        return {"ok": False, "error": res.error, "packages": []}
    packages = []
    for line in res.output.splitlines():
        if "/" not in line or line.startswith("Listing"):
            continue
        # e.g. "vim/stable 2:9.0.1378-2 arm64 [upgradable from: 2:9.0.1378-1]"
        parts = line.split()
        name = parts[0].split("/")[0]
        new_version = parts[1] if len(parts) > 1 else ""
        current = line.split("upgradable from:")[-1].rstrip("]").strip() if "upgradable from:" in line else ""
        packages.append({"name": name, "new": new_version, "current": current})
    return {"ok": True, "packages": packages}


def apply_updates_stream():
    """Refresh apt lists then upgrade, yielding combined output as it runs.

    A generator so the caller can stream progress to the browser — apt upgrades
    can take minutes and shouldn't block on a single response.
    """
    env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
    phases = [
        ("Refreshing package lists", ["sudo", "-n", "apt-get", "update"]),
        ("Installing upgrades", ["sudo", "-n", "apt-get", "-y", "upgrade"]),
    ]
    for title, cmd in phases:
        yield f"\n=== {title} ===\n"
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env, bufsize=1
            )
        except OSError as e:
            yield f"failed to start apt: {e}\n"
            return
        for line in iter(proc.stdout.readline, ""):
            yield line
        proc.stdout.close()
        code = proc.wait()
        if code != 0:
            yield f"\n[{title} failed with exit code {code}]\n"
            return
    yield "\n[all upgrades applied]\n"


def get_pironman_config() -> dict:
    res = sudo("pironman5", "-c", timeout=15)
    if not res.ok:
        return {"ok": False, "error": res.error or "failed to read pironman5 config"}
    try:
        config = json.loads(res.output or "{}")
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"invalid pironman5 config output: {e}"}
    return {"ok": True, "config": config.get("system", config)}


def apply_pironman_config(settings: dict) -> CmdResult:
    cmd = ["pironman5"]
    for key, flag in _PIRONMAN_FLAGS.items():
        if key in settings:
            value = settings[key]
            if isinstance(value, bool):
                value = "True" if value else "False"
            cmd.extend([flag, str(value)])
    if len(cmd) > 1:
        res = sudo(*cmd, timeout=30)
        if not res.ok:
            return res
    return sudo("systemctl", "restart", "pironman5.service", timeout=60)


def get_cpu_fan() -> dict:
    res = run("pinctrl", "get", "FAN_PWM", timeout=5)
    if not res.ok:
        return {"ok": False, "error": res.error, "on": False}
    # pin driven low ("dl") powers the fan
    return {"ok": True, "on": " dl " in f" {res.output} "}


def set_cpu_fan(on: bool) -> CmdResult:
    return sudo("pinctrl", "FAN_PWM", "op", "dl" if on else "dh", timeout=5)
