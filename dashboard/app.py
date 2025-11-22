import streamlit as st
import psutil
import socket
import time
import os
from collections import deque

# ===============================
# ⚙️ Streamlit Page Setup
# ===============================
st.set_page_config(page_title="Pi Health Dashboard", page_icon="🍓", layout="wide")
st.title("🍓 Pi Health Dashboard")


# ===============================
# 📊 Data Collection
# ===============================
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


# ===============================
# ⚙️ Pi Controller (Reboot / Shutdown / Fan)
# ===============================
class PiController:

    def reboot(self):
        os.system("sudo reboot")

    def shutdown(self):
        os.system("sudo shutdown now")

    def check_updates(self):
        return os.popen("apt list --upgradable 2>/dev/null | tail -n +2").read()

    def fan_on(self):
        os.system(f"sudo pinctrl FAN_PWM op dl")

    def fan_off(self):
        os.system(f"sudo pinctrl FAN_PWM op dh")

    def is_fan_on(self):
        """
        Reads the pin state using ONLY `pinctrl FAN_PWM` and os.popen().
        Expected outputs:
            "op dl pd | lo" → ON
            "op dh pd | hi" → OFF
        """
        out = os.popen("pinctrl FAN_PWM").read().lower()

        if "dl" in out or " lo" in out:
            return True     # fan ON
        elif "dh" in out or " hi" in out:
            return False    # fan OFF

# ===============================
# 🎨 Helpers
# ===============================
def get_color(val, low=30, high=80):
    if val < low:
        return "green"
    elif val < high:
        return "orange"
    return "red"

def metric_chart(label, val, hist, unit="", color="green"):
    if len(hist) < 2:
        delta = 0
    else:
        delta = round(hist[-1] - hist[-2], 2)
    st.metric(
        label=f":{color}-badge[**{label}**]",
        value=f"{val}{unit}",
        delta=f"{delta}{unit}",
        delta_color="inverse",
        chart_data=hist,
        border=True,
    )


# ===============================
# 🖥️ UI Renderer
# ===============================
class PiUI:
    def __init__(self, stats: PiStats):
        self.stats = stats
        self.ctrl = PiController()

        # History state
        if "cpu_hist" not in st.session_state:
            st.session_state.cpu_hist = deque(maxlen=60)
        if "ram_hist" not in st.session_state:
            st.session_state.ram_hist = deque(maxlen=60)
        if "cpu_temp_hist" not in st.session_state:
            st.session_state.cpu_temp_hist = deque(maxlen=60)
        if "adc_temp_hist" not in st.session_state:
            st.session_state.adc_temp_hist = deque(maxlen=60)
        if "fan_on" not in st.session_state:
            st.session_state.fan_on = self.ctrl.is_fan_on()

        st.session_state.cpu_hist.append(self.stats.cpu)
        st.session_state.ram_hist.append(self.stats.ram)
        st.session_state.cpu_temp_hist.append(self.stats.cpu_temp)
        st.session_state.adc_temp_hist.append(self.stats.adc_temp)


    def system_tab(self):
        st.subheader("Live System Metrics")
        cols = st.columns(5)
        with cols[0]: st.metric(":blue-badge[**Uptime**]", self.stats.uptime_val, border=True, height="stretch")
        with cols[1], st.container(border=True, height="stretch"):
            st.markdown(":blue-badge[**IP Addr**]")
            st.code(self.stats.ip)
        with cols[2]: st.metric(":blue-badge[**Packets Sent**]", f"{round(self.stats.net_io.packets_sent/1000)}K", delta=f"{self.stats.net_io.bytes_sent / (1024 ** 2):.2f} MB", border=True)
        with cols[3]: st.metric(":blue-badge[**Packets Received**]", f"{round(self.stats.net_io.packets_recv/1000)}K", delta=f"{-self.stats.net_io.bytes_recv / (1024 ** 2):.2f} MB", border=True)
        with cols[4], st.container(border=True, height="stretch"):
            st.markdown(f":{get_color(self.stats.disk.percent, 70, 90)}-badge[**Disk Usage**]")
            st.progress(self.stats.disk.percent/100, text=f"{self.stats.disk.percent:.2f} %")

        cols = st.columns(4)
        with cols[0]: metric_chart("CPU Usage", self.stats.cpu, st.session_state.cpu_hist, "%", get_color(self.stats.cpu))
        with cols[1]: metric_chart("RAM Usage", self.stats.ram, st.session_state.ram_hist, "%", get_color(self.stats.ram))
        with cols[2]: metric_chart("CPU Temp", self.stats.cpu_temp, st.session_state.cpu_temp_hist, "°𝐶", get_color(self.stats.cpu_temp))
        with cols[3]: metric_chart("ADC Temp", self.stats.adc_temp, st.session_state.adc_temp_hist, "°𝐶", get_color(self.stats.adc_temp))

        st.subheader("Top Processes by CPU Usage")
        data = [{"PID": p["pid"], "Name": p["name"], "CPU%": p["cpu_percent"], "RAM%": p["memory_percent"]} for p in self.stats.processes]
        st.dataframe(
            data,
            column_config={
                "CPU%": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
                "RAM%": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100)
            },
            use_container_width=True
        )

    @st.fragment
    def controls_tab(self):
        st.subheader("⚙️ System Controls")
        cols = st.columns(4)
        with cols[0]:
            # Fan toggle
            fan_on = st.toggle("🌀 Fan Power", key=st.session_state.fan_on)
            if fan_on:
                self.ctrl.fan_on()
            else:
                self.ctrl.fan_off()

        with cols[1]:
            if st.button("Reboot Pi", icon="🔄"):
                st.warning("Rebooting...")
                self.ctrl.reboot()

        with cols[2]:
            if st.button("Shutdown Pi", icon="🔌"):
                st.error("Shutting down...")
                self.ctrl.shutdown()

        with cols[3]:
            if st.button("Check Updates", icon="🧩"):
                with st.status("Fetching updates..."):
                    updates = self.ctrl.check_updates()
                    st.code(updates if updates else "✅ System is up-to-date")



# ===============================
# 🚀 Dashboard (Auto Refresh)
# ===============================
@st.fragment(run_every="10s")
def dashboard():
    stats = PiStats()
    stats.refresh()
    ui = PiUI(stats)

    tabs = st.tabs(["📊 System", "⚙️ Controls"])
    with tabs[0]: ui.system_tab()
    with tabs[1]: ui.controls_tab()

dashboard()
