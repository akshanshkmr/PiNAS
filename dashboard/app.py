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
    
    @staticmethod
    def _linux_user_options():
        """Return list of eligible Linux usernames for Samba bindings."""
        valid_users = []
        for entry in pwd.getpwall():
            if entry.pw_uid >= 1000 and entry.pw_shell not in ("/usr/sbin/nologin", "/bin/false"):
                valid_users.append(entry.pw_name)
        return sorted(set(valid_users))
    
    def system_tab(self):
        """Render system metrics tab."""
        st.subheader("📊 Live System Metrics")
        
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
        cols = st.columns(3)
        
        with cols[0]:
            if st.button("Reboot Pi", icon="🔄"):
                st.warning("Rebooting...")
                self.controller.reboot()
        
        with cols[1]:
            if st.button("Shutdown Pi", icon="🔌"):
                st.error("Shutting down...")
                self.controller.shutdown()
        
        with cols[2]:
            if st.button("Check Updates", icon="🧩"):
                with st.status("Fetching updates..."):
                    updates = self.controller.check_updates()
                    st.code(updates if updates else "✅ System is up-to-date")
    
    def nas_tab(self):
        """Render NAS management tab."""
        nas = PiNAS()
        self._init_nas_state(nas)

        st.subheader("💾 NAS Overview")
        status_cols = st.columns(2)

        with status_cols[0], st.container(border=True, height="stretch"):
            st.subheader("RAID")
            st.code(nas.raid_status().strip() or "No RAID information found")
            rebuild = nas.rebuild_progress().strip() or "Idle"
            st.caption("Rebuild / Sync status")
            st.code(rebuild)
            if st.button("Manage RAID", use_container_width=True):
                self._raid_management_dialog(nas)

        with status_cols[1], st.container(border=True, height="stretch"):
            st.subheader("Samba Shares")
            nas.show_samba_share_status()
            if nas.smb_shares:
                st.dataframe(
                    nas.smb_shares,
                    hide_index=True,
                    use_container_width=True,
                )
            if st.button("Manage SAMBA Shares", use_container_width=True):
                self._samba_management_dialog(nas)

    def _init_nas_state(self, nas: PiNAS):
        defaults = {
            "smb_share_rows": None,
        }
        for key, val in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = val
        if st.session_state["smb_share_rows"] is None:
            base_rows = [dict(share) for share in nas.smb_shares] if nas.smb_shares else []
            st.session_state["smb_share_rows"] = base_rows or [
                {"name": "nas", "path": "/mnt/nas", "allow_guest": False, "read_only": False}
            ]


    @st.dialog("RAID Manager")
    def _raid_management_dialog(self, nas: PiNAS):
        drives = nas.get_available_disks()
        drive_options = {f"{d['device']} — {d['size']} ({d['model']})": d["device"] for d in drives}
        arrays = nas.detect_arrays()

        st.subheader("Restore existing arrays")
        st.code(arrays.strip() or "No arrays detected.")
        if st.button("Assemble detected arrays", use_container_width=True, disabled=not arrays):
            msg = nas.restore_detected_arrays()
            st.success(msg or "Assemble command executed.")

        st.divider()
        st.subheader("Build new array")
        if drive_options:
            selected = st.multiselect(
                "Pick drives",
                options=list(drive_options.keys()),
                key="raid_drive_multiselect",
            )
            level = st.selectbox("RAID level", ["0", "1", "5", "10"], index=1)
            if st.button("Create array", use_container_width=True, disabled=not selected):
                disks = [drive_options[label] for label in selected]
                with st.status("Provisioning RAID…", expanded=True) as status:
                    status.write(f"Disks: {', '.join(disks)}")
                    status.write(f"Level: {level}")
                    msg = nas.create_raid(disks, level)
                    status.update(label="Complete", state="complete")
                st.success(msg)
        else:
            st.info("No eligible drives detected.")

        st.divider()
        st.subheader("Rebuild / Sync array")
        pick = st.selectbox(
            "Select array",
            options=arrays or ["No arrays detected"],
            index=0,
            key="raid_array_select",
        )
        if st.button("Trigger repair sync", use_container_width=True, disabled = not arrays):
            msg = nas.resync_array(pick if arrays else "/dev/md0")
            st.success(msg or "Repair command issued.")

    @st.dialog("Samba Services")
    def _samba_management_dialog(self, nas: PiNAS):
        with st.expander("Share users"), st.form("smb_user_form"):
            linux_users = self._linux_user_options()
            user_options = linux_users or ["No eligible Linux users found"]
            username = st.selectbox(
                "Username",
                options=user_options,
                key="smb_user_name",
                disabled=not linux_users,
            )
            password = st.text_input(
                "Password",
                type="password",
                key="smb_user_pass",
                disabled=not linux_users,
            )
            add_col, disable_col = st.columns(2)
            with add_col:
                submitted = st.form_submit_button(
                    "Add / Update User",
                    use_container_width=True,
                    disabled=not linux_users,
                )
            with disable_col:
                disable_user = st.form_submit_button(
                    "Disable User",
                    use_container_width=True,
                    disabled=not linux_users,
                    type="secondary",
                )
            if submitted:
                msg = nas.add_samba_user(username, password)
                st.success(msg)
            elif disable_user:
                msg = nas.disable_samba_user(username)
                st.warning(msg)

        st.subheader("Shares")
        share_rows_df = st.data_editor(
            st.session_state["smb_share_rows"],
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="smb_share_editor",
            column_config={
                "allow_guest": st.column_config.CheckboxColumn("Guest access"),
                "read_only": st.column_config.CheckboxColumn("Read only"),
            },
        )
        share_rows = share_rows_df.to_dict("records") if hasattr(share_rows_df, "to_dict") else share_rows_df
        st.session_state["smb_share_rows"] = share_rows

        if st.button("Save shares", use_container_width=True):
            valid = [
                {
                    "name": row["name"],
                    "path": row.get("path") or "/mnt/nas",
                    "allow_guest": bool(row.get("allow_guest")),
                    "read_only": bool(row.get("read_only")),
                }
                for row in share_rows
                if row.get("name") and row.get("path")
            ]
            if not valid:
                st.warning("Add at least one share with a name and path.")
            else:
                nas.configure_samba_shares(valid)
                st.session_state["smb_share_rows"] = [dict(share) for share in valid]
                st.success("Shares updated and Samba restarted.")


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