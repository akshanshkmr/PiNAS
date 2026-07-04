"""Per-drive SMART health via smartctl (JSON output).

Normalises both ATA and NVMe reports into one shape the UI can render, so a
failing disk on the NAS is visible before it takes data with it.
"""

import json

from .nas import list_disks
from .shell import sudo

# ATA SMART attribute ids we surface
_ATA_ATTRS = {5: "reallocated", 197: "pending", 198: "uncorrectable"}


def _attr_value(table, attr_id):
    for row in table:
        if row.get("id") == attr_id:
            raw = row.get("raw", {})
            return raw.get("value")
    return None


def _report_for(device, model_hint=None):
    # smartctl uses a bitmask exit code (nonzero even on benign warnings), so we
    # parse whatever JSON it produced regardless of the return code.
    res = sudo("smartctl", "-H", "-A", "-i", "-j", device, timeout=30)
    if not res.output:
        return {"device": device, "model": model_hint, "available": False, "error": res.error or "no SMART data"}
    try:
        data = json.loads(res.output)
    except json.JSONDecodeError:
        return {"device": device, "model": model_hint, "available": False, "error": "unreadable smartctl output"}

    messages = data.get("smartctl", {}).get("messages", [])
    if data.get("device") is None and messages:
        return {"device": device, "model": model_hint, "available": False, "error": messages[0].get("string", "SMART unavailable")}

    dev_type = (data.get("device", {}) or {}).get("type", "")
    health = data.get("smart_status", {}).get("passed")
    temp = (data.get("temperature", {}) or {}).get("current")
    poh = (data.get("power_on_time", {}) or {}).get("hours")

    report = {
        "device": device,
        "model": data.get("model_name") or model_hint,
        "serial": data.get("serial_number"),
        "capacity": (data.get("user_capacity", {}) or {}).get("bytes"),
        "type": "nvme" if "nvme" in dev_type else "ata",
        "available": True,
        "health": "passed" if health is True else "failed" if health is False else "unknown",
        "temperature": temp,
        "power_on_hours": poh,
        "warnings": [],
    }

    if "nvme" in dev_type:
        log = data.get("nvme_smart_health_information_log", {}) or {}
        report["temperature"] = report["temperature"] if report["temperature"] is not None else log.get("temperature")
        report["power_on_hours"] = report["power_on_hours"] if report["power_on_hours"] is not None else log.get("power_on_hours")
        report["media_errors"] = log.get("media_errors")
        report["percentage_used"] = log.get("percentage_used")
        report["available_spare"] = log.get("available_spare")
        if log.get("critical_warning"):
            report["warnings"].append("Controller reports a critical warning")
        if (log.get("available_spare") or 100) < (log.get("available_spare_threshold") or 10):
            report["warnings"].append("Available spare below threshold")
    else:
        table = (data.get("ata_smart_attributes", {}) or {}).get("table", [])
        for attr_id, key in _ATA_ATTRS.items():
            report[key] = _attr_value(table, attr_id)
        for key, label in (("reallocated", "reallocated sectors"), ("pending", "pending sectors"), ("uncorrectable", "uncorrectable sectors")):
            if report.get(key):
                report["warnings"].append(f"{report[key]} {label}")

    if report["health"] == "failed":
        report["warnings"].insert(0, "SMART overall-health self-assessment FAILED")
    return report


def smart_report():
    """SMART report for every non-boot physical disk."""
    return [_report_for(d["device"], d.get("model")) for d in list_disks()]
