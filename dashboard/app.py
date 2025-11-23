import streamlit as st
import pam
import pwd
from collections import deque
from utils import PiNAS, PiController, PiStats

st.set_page_config(page_title="Pi Admin Dashboard", page_icon="🖥️", layout="wide")

class AuthManager:
    """Handles user authentication and session management."""
    
    def __init__(self):
        self.init_session_state()
    
    def init_session_state(self):
        """Initialize authentication session state."""
        for key, default in [('authenticated', False), ('username', None), ('name', None)]:
            if key not in st.session_state:
                st.session_state[key] = default
    
    def authenticate(self, username, password):
        """Authenticate user using PAM."""
        try:
            if pam.pam().authenticate(username, password, service='login'):
                try:
                    name = pwd.getpwnam(username).pw_gecos.split(',')[0] or username
                except:
                    name = username
                return True, name
            return False, None
        except Exception as e:
            print(f"PAM authentication error: {str(e)}")
            return False, None
    
    def login(self, username, name):
        """Set session state after successful login."""
        st.session_state.update(authenticated=True, username=username, name=name)
        st.rerun()
    
    def show_login_form(self):
        """Display login form UI."""
        st.title("🔐 Login")
        st.markdown("Enter your Linux username and password")
        with st.form("login_form"):
            username = st.text_input("Username", placeholder="Enter your Linux username")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            if st.form_submit_button("Login", use_container_width=True):
                if not (username and password):
                    st.error("Please enter both username and password")
                else:
                    with st.spinner("Authenticating..."):
                        authenticated, name = self.authenticate(username, password)
                        if authenticated:
                            self.login(username, name)
                        else:
                            st.error("Invalid username or password. Please try again.")


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
    def metric_chart(label, val, hist, unit="", color="green"):
        """Display metric with chart and delta."""
        delta = round(hist[-1] - hist[-2], 2) if len(hist) >= 2 else 0
        st.metric(
            label=f":{color}-badge[**{label}**]",
            value=f"{val}{unit}",
            delta=f"{delta}{unit}",
            delta_color="inverse",
            chart_data=hist,
            border=True,
        )


class MetricHistory:
    """Manages metric history state."""
    
    METRICS = ['cpu_hist', 'ram_hist', 'cpu_temp_hist', 'adc_temp_hist']
    
    @staticmethod
    def init():
        """Initialize all metric histories."""
        for metric in MetricHistory.METRICS:
            if metric not in st.session_state:
                st.session_state[metric] = deque(maxlen=60)
    
    @staticmethod
    def update(cpu, ram, cpu_temp, adc_temp):
        """Update all metric histories."""
        MetricHistory.init()
        st.session_state.cpu_hist.append(cpu)
        st.session_state.ram_hist.append(ram)
        st.session_state.cpu_temp_hist.append(cpu_temp)
        st.session_state.adc_temp_hist.append(adc_temp)


class PiUI:
    """Main UI renderer for dashboard tabs."""
    
    def __init__(self):
        self.stats = PiStats()
        self.stats.refresh()
        self.controller = PiController()
        self.ui = UIComponents()
        MetricHistory.update(self.stats.cpu, self.stats.ram, 
                           self.stats.cpu_temp, self.stats.adc_temp)
    
    def system_tab(self):
        """Render system metrics tab."""
        st.subheader("Live System Metrics")
        
        cols = st.columns(5)
        with cols[0]: 
            st.metric(":blue-badge[**Uptime**]", self.stats.uptime_val, border=True, height="stretch")
        with cols[1], st.container(border=True, height="stretch"):
            st.markdown(":blue-badge[**IP Addr**]")
            st.code(self.stats.ip)
        with cols[2]: 
            st.metric(":blue-badge[**Packets Sent**]", 
                     f"{round(self.stats.net_io.packets_sent/1000)}K", 
                     delta=f"{self.stats.net_io.bytes_sent / (1024 ** 2):.2f} MB", border=True)
        with cols[3]: 
            st.metric(":blue-badge[**Packets Received**]", 
                     f"{round(self.stats.net_io.packets_recv/1000)}K", 
                     delta=f"{-self.stats.net_io.bytes_recv / (1024 ** 2):.2f} MB", border=True)
        with cols[4], st.container(border=True, height="stretch"):
            color = self.ui.get_color(self.stats.disk.percent, 70, 90)
            st.markdown(f":{color}-badge[**Disk Usage**]")
            st.progress(self.stats.disk.percent/100, text=f"{self.stats.disk.percent:.2f} %")
        
        cols = st.columns(4)
        with cols[0]: 
            self.ui.metric_chart("CPU Usage", self.stats.cpu, st.session_state.cpu_hist, 
                               "%", self.ui.get_color(self.stats.cpu))
        with cols[1]: 
            self.ui.metric_chart("RAM Usage", self.stats.ram, st.session_state.ram_hist, 
                               "%", self.ui.get_color(self.stats.ram))
        with cols[2]: 
            self.ui.metric_chart("CPU Temp", self.stats.cpu_temp, st.session_state.cpu_temp_hist, 
                               "°𝐶", self.ui.get_color(self.stats.cpu_temp))
        with cols[3]: 
            self.ui.metric_chart("ADC Temp", self.stats.adc_temp, st.session_state.adc_temp_hist, 
                               "°𝐶", self.ui.get_color(self.stats.adc_temp))
        
        st.subheader("Top Processes by CPU Usage")
        data = [{"PID": p["pid"], "Name": p["name"], 
                "CPU%": p["cpu_percent"], "RAM%": p["memory_percent"]} 
                for p in self.stats.processes]
        st.dataframe(
            data,
            column_config={
                "CPU%": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
                "RAM%": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100)
            },
            use_container_width=True
        )
    
    def controls_tab(self):
        """Render system controls tab."""
        st.subheader("⚙️ System Controls")
        cols = st.columns(4)
        
        with cols[0]:
            fan_on = st.toggle("🌀 Fan Power", value=st.session_state.is_fan_on)
            self.controller.fan_on() if fan_on else self.controller.fan_off()
        
        with cols[1]:
            if st.button("Reboot Pi", icon="🔄"):
                st.warning("Rebooting...")
                self.controller.reboot()
        
        with cols[2]:
            if st.button("Shutdown Pi", icon="🔌"):
                st.error("Shutting down...")
                self.controller.shutdown()
        
        with cols[3]:
            if st.button("Check Updates", icon="🧩"):
                with st.status("Fetching updates..."):
                    updates = self.controller.check_updates()
                    st.code(updates if updates else "✅ System is up-to-date")
    
    def nas_tab(self):
        """Render NAS management tab."""
        nas = PiNAS()
        
        colA, colB = st.columns(2)
        with colA, st.container(border=True, height="stretch"):
            st.header("RAID")
            st.write("Create or manage RAID arrays")
            st.write("Select drives to include:")
            
            drives = nas.get_available_disks()
            selected = [d['device'] for d in drives 
                       if st.checkbox(f"{d['device']} — {d['size']} ({d['model']})", 
                                     key=f"raid_disk_{d['device']}")]
            
            if not selected:
                st.warning("No drives selected")
            else:
                level = st.selectbox("RAID Level", ["0","1","5","10"], index=1)
                if st.button("Create RAID (Confirm)"):
                    with st.status("Creating RAID…", expanded=True) as status:
                        status.write(f"Disks: {selected}")
                        status.write(f"Level: {level}")
                        msg = nas.create_raid(selected, level)
                        status.update(label="Done", state="complete")
                    st.success(msg)
        
        with colB, st.container(border=True):
            st.header("Services")
            st.write("Manage SMB services and shares")
            
            share = st.text_input("Share Name", "nas", key="nas_share_name")
            path = st.text_input("Path", "/mnt/nas", key="nas_share_path")
            allow_guest = st.checkbox("Allow guest access", 
                                     help="This share will not require password but will be readonly", 
                                     key="nas_guest")
            
            if st.button("Create SMB Share"):
                with st.status("Creating SMB share…", expanded=True) as s:
                    conf = nas.add_samba_share(share, path, allow_guest)
                    s.write("Base share added.")
                    st.code(conf)
                st.success("SMB share created.")
        
        st.divider()
        st.subheader("RAID Status")
        st.code(nas.raid_status())
        st.subheader("Rebuild Progress")
        st.code(nas.rebuild_progress())


class DashboardApp:
    """Main dashboard application controller."""
    
    def __init__(self):
        self.auth = AuthManager()
    
    def render(self):
        """Main render method - routes to login or dashboard."""
        if not st.session_state.authenticated:
            self.auth.show_login_form()
        else:
            self.dashboard()
    
    def dashboard(self):
        """Render main dashboard with tabs."""
        st.title("🍓 Pi Admin Dashboard")
        tabs = st.tabs(["📊 System", "⚙️ Controls", "💾 NAS"])
        
        with tabs[0]:
            @st.fragment(run_every="5s")
            def system_content():
                PiUI().system_tab()
            system_content()
        
        with tabs[1]:
            PiUI().controls_tab()
        
        with tabs[2]:
            PiUI().nas_tab()


if __name__ == "__main__":
    app = DashboardApp()
    app.render()