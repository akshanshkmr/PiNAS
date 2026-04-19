import streamlit as st
from ui import UIComponents, MetricHistory
from utils import PiStats


def render_system_tab():
    """Render system metrics tab with fresh stats."""
    stats = PiStats()
    stats.refresh()
    ui = UIComponents()
    MetricHistory.update(stats.cpu, stats.ram, stats.cpu_temp)
    cpu_state = ui.severity_text(stats.cpu)
    ram_state = ui.severity_text(stats.ram)
    disk_state = ui.severity_text(stats.disk.percent, low=70, high=90)

    st.subheader("Compute")
    compute_cols = st.columns(3)
    with compute_cols[0]:
        ui.metric_chart(
            f"CPU Usage: {cpu_state}",
            stats.cpu,
            st.session_state.cpu_hist,
            "%",
            ui.get_color(stats.cpu),
        )
    with compute_cols[1]:
        ui.metric_chart(
            f"RAM Usage: {ram_state}",
            stats.ram,
            st.session_state.ram_hist,
            "%",
            ui.get_color(stats.ram),
        )
    with compute_cols[2]:
        temp_state = ui.severity_text(stats.cpu_temp, low=55, high=75)
        ui.metric_chart(
            f"CPU Temp: {temp_state}",
            stats.cpu_temp,
            st.session_state.cpu_temp_hist,
            "\u00b0C",
            ui.get_color(stats.cpu_temp, low=55, high=75),
        )

    st.subheader("Network")
    network_cols = st.columns(3)
    with network_cols[0], st.container(border=True, height="stretch"):
        st.markdown("IP Address")
        st.code(stats.ip)
    with network_cols[1]:
        st.metric(
            "Packets Sent",
            f"{round(stats.net_io.packets_sent/1000)}K",
            delta=f"{stats.net_io.bytes_sent / (1024 ** 2):.2f} MB",
            border=True,
        )
    with network_cols[2]:
        st.metric(
            "Packets Received",
            f"{round(stats.net_io.packets_recv/1000)}K",
            delta=f"{stats.net_io.bytes_recv / (1024 ** 2):.2f} MB",
            border=True,
        )

    st.subheader("Storage")
    storage_cols = st.columns(2)
    with storage_cols[0]:
        st.metric("Uptime", stats.uptime_val, border=True)
    with storage_cols[1], st.container(border=True, height="stretch"):
        color = ui.get_color(stats.disk.percent, 70, 90)
        st.markdown(f":{color}-badge[Disk Usage: {disk_state}]")
        st.progress(stats.disk.percent / 100, text=f"{stats.disk.percent:.2f}%")

    st.subheader("Top Processes")
    data = [{"Name": p["name"], "PID": p["pid"], 
              "CPU%": p["cpu_percent"], "RAM%": p["memory_percent"]}
              for p in stats.processes]
    st.dataframe(
        data,
        column_config={
            "CPU%": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
            "RAM%": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100)
        },
        width="stretch"
    )

