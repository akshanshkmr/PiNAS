import streamlit as st
from collections import deque


class UIComponents:
    """Reusable UI components and helpers."""

    @staticmethod
    def get_color(val, low=30, high=80):
        """Get color based on value thresholds."""
        if val < low:
            return "green"
        elif val < high:
            return "orange"
        return "red"

    @staticmethod
    def severity_text(val, low=30, high=80):
        """Get severity text based on value thresholds."""
        if val < low:
            return "Normal"
        elif val < high:
            return "Warning"
        return "Critical"

    @staticmethod
    def metric_chart(label, val, hist, unit="", color="green"):
        """Display metric with chart and delta."""
        delta = round(hist[-1] - hist[-2], 2) if len(hist) >= 2 else 0
        st.metric(
            label=f":{color}-badge[{label}]",
            value=f"{val}{unit}",
            delta=f"{delta}{unit}",
            delta_color="inverse",
            chart_type="area",
            chart_data=list(hist) if hist else [val],
            border=True,
        )


class MetricHistory:
    """Manages metric history state."""

    METRICS = ['cpu_hist', 'ram_hist', 'cpu_temp_hist']

    @staticmethod
    def init():
        """Initialize all metric histories."""
        for metric in MetricHistory.METRICS:
            if metric not in st.session_state:
                st.session_state[metric] = deque(maxlen=60)

    @staticmethod
    def update(cpu, ram, cpu_temp):
        """Update all metric histories."""
        MetricHistory.init()
        st.session_state.cpu_hist.append(cpu)
        st.session_state.ram_hist.append(ram)
        st.session_state.cpu_temp_hist.append(cpu_temp)
