import streamlit as st
import psutil
import os
import time

def get_sd_health():
    """Estimate SD card wear by checking total writes."""
    try:
        result = os.popen("iostat -d | grep mmcblk0 | awk '{print $4}'").read().strip()
        writes = float(result) if result else 0
        # Arbitrary simple health score logic for demo
        max_writes = 100000  # adjust for your SD card endurance
        health = max(0, 100 - (writes / max_writes * 100))
        return round(health, 2)
    except Exception:
        return 100

st.set_page_config(page_title="Pi Health Dashboard", page_icon="🩺", layout="wide")

st.title("🍓 Raspberry Pi Health Dashboard")

uptime = (time.time() - psutil.boot_time()) / 60 / 60
cpu = psutil.cpu_percent(interval=1)
ram = psutil.virtual_memory().percent
cpu_temp = psutil.sensors_temperatures().get('cpu_thermal')[0].current
adc_temp = psutil.sensors_temperatures().get('rp1_adc')[0].current
sd_health = get_sd_health()


cols = st.columns(6)
cols[0].metric("Uptime", f"{uptime:.2f} hours", border=True)
cols[1].metric("CPU Usage", f"{cpu}%", border=True)
cols[2].metric("RAM Usage", f"{ram}%", border=True)
cols[3].metric("CPU Temperature", f"{cpu_temp}°C", border=True)
cols[4].metric("ADC Temperature", f"{adc_temp}°C", border=True)
cols[5].metric("SD Card Health", f"{sd_health}%", border=True)

if sd_health < 30:
    st.warning("⚠️ SD Card health is low! Consider cloning to a new card.")
    st.write("Run `./scripts/backup_sd.sh` and `./scripts/clone_sd.sh` for backup.")
