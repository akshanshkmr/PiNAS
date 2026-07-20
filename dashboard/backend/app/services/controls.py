"""Power, Pironman case and CPU fan control."""

import json

from .shell import CmdResult, sudo

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
