import streamlit as st
import psutil
import time
import os
from collections import deque


# ===============================
# ⚙️ Streamlit Page Setup
# ===============================
st.set_page_config(page_title="Pi Health Dashboard", page_icon="🍓", layout="wide")
st.title("🍓 Pi Health Dashboard")

# Initialize history for charts
if "cpu_hist" not in st.session_state:
    st.session_state.cpu_hist = deque(maxlen=60)
if "ram_hist" not in st.session_state:
    st.session_state.ram_hist = deque(maxlen=60)
if "temp_hist" not in st.session_state:
    st.session_state.temp_hist = deque(maxlen=60)


# ===============================
# 📊 Data Collection
# ===============================
class TempSensors:
    CPU = "cpu_thermal"
    ADC = "rp1_adc"


class PiStats:
    """Collects system metrics for Raspberry Pi."""

    def refresh(self):
        self.temps = psutil.sensors_temperatures()
        self.cpu = psutil.cpu_percent(interval=None)
        self.ram = psutil.virtual_memory().percent
        self.disk = psutil.disk_usage('/')
        self.net_io = psutil.net_io_counters()
        self.uptime_val = self._uptime()
        self.processes = self._get_top_processes(10)

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
            return self.temps.get(name, [{}])[0].current
        except Exception:
            return 0.0

    def _get_top_processes(self, n):
        plist = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            plist.append(p.info)
        return sorted(plist, key=lambda x: x['cpu_percent'], reverse=True)[:n]


# ===============================
# 🎨 Helpers
# ===============================
def get_color(val, low=30, high=80):
    if val < low:
        return "green"
    elif val < high:
        return "orange"
    return "red"


def metric_box(label, val, unit="", max_val=100, color="green"):
    with st.container(border=True):
        st.markdown(f":{color}-badge[**{label}**]")
        st.progress(val / max_val, text=f"{val:.2f} {unit}")


# ===============================
# 🖥️ UI Renderer
# ===============================
class PiUI:
    def __init__(self, stats: PiStats):
        self.stats = stats

    def system_tab(self):
        cpu_temp = self.stats._get_temp(TempSensors.CPU)
        adc_temp = self.stats._get_temp(TempSensors.ADC)
        disk_usage = self.stats.disk.percent
        cols = st.columns(6)
        with cols[0]: st.metric(":blue-badge[**Uptime**]", self.stats.uptime_val, border=True)
        with cols[1]: metric_box("CPU Usage", self.stats.cpu, "%", 100, get_color(self.stats.cpu))
        with cols[2]: metric_box("RAM Usage", self.stats.ram, "%", 100, get_color(self.stats.ram))
        with cols[3]: metric_box("CPU Temp", cpu_temp, "°C", 100, get_color(cpu_temp))
        with cols[4]: metric_box("ADC Temp", adc_temp, "°C", 100, get_color(adc_temp))
        with cols[5]: metric_box("Disk Usage", disk_usage, "%", 100, get_color(disk_usage, 70, 90))

        # Charts
        st.subheader("📈 Live Metrics")
        st.session_state.cpu_hist.append(self.stats.cpu)
        st.session_state.ram_hist.append(self.stats.ram)
        st.session_state.temp_hist.append(cpu_temp)

        chart_cols = st.columns(3)
        chart_cols[0].line_chart(st.session_state.cpu_hist, y_label="CPU %")
        chart_cols[1].line_chart(st.session_state.ram_hist, y_label="RAM %")
        chart_cols[2].line_chart(st.session_state.temp_hist, y_label="Temp °C")

    def network_tab(self):
        net = self.stats.net_io
        col1, col2 = st.columns(2)
        col1.metric(":blue-badge[**Sent**]", f"{net.packets_sent} Packets", delta=f"{net.bytes_sent / (1024 ** 2):.2f} MB", border=True)
        col2.metric(":blue-badge[**Received**]", f"{net.packets_recv} Packets", delta=f"{-net.bytes_recv / (1024 ** 2):.2f} MB", border=True)

    def processes_tab(self):
        st.subheader("🔍 Top Processes by CPU Usage")
        data = [{"PID": p["pid"], "Name": p["name"], "CPU%": p["cpu_percent"], "RAM%": p["memory_percent"]} for p in self.stats.processes]
        st.dataframe(
            data, 
            column_config={
                "CPU%": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
                "RAM%": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100)
            },
            use_container_width=True
        )

    def controls_tab(self):
        st.subheader("⚙️ System Controls")
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("Reboot Pi", icon="🔄"):
                st.warning("Rebooting...")
                os.system("sudo reboot")

        with col2:
            if st.button("Shutdown Pi", icon="🔌"):
                st.error("Shutting down...")
                os.system("sudo shutdown now")

        with col3:
            if st.button("Check Updates", icon="🧩"):
                with st.status("Fetching updates..."):
                    updates = os.popen("apt list --upgradable 2>/dev/null | tail -n +2").read()
                    st.code(updates if updates else "✅ System is up-to-date")


# ===============================
# 🚀 Dashboard (Auto Refresh)
# ===============================
@st.fragment(run_every="5s")
def dashboard():
    stats = PiStats()
    stats.refresh()
    ui = PiUI(stats)

    tabs = st.tabs(["📊 System", "🌐 Network", "🧩 Processes", "⚙️ Controls"])

    with tabs[0]: ui.system_tab()
    with tabs[1]: ui.network_tab()
    with tabs[2]: ui.processes_tab()
    with tabs[3]: ui.controls_tab()


dashboard()
