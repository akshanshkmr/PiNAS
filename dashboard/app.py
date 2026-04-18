import streamlit as st
import pam
import pwd
from collections import deque
from datetime import datetime
from utils import PiNAS, PiController, PiStats

st.set_page_config(page_title="Pi Admin Dashboard", page_icon="🖥️", layout="wide")

class AuthManager:
    """Handles user authentication and session management."""
    
    def __init__(self):
        self.init_session_state()
    
    def init_session_state(self):
        """Initialize authentication session state."""
        for key, default in [
            ('authenticated', False),
            ('username', None),
            ('name', None),
            ('confirm_reboot', False),
            ('confirm_shutdown', False),
            ('confirm_reboot_token', ""),
            ('confirm_shutdown_token', ""),
            ('last_refresh_at', None),
        ]:
            if key not in st.session_state:
                st.session_state[key] = default
    
    def authenticate(self, username, password):
        """Authenticate user using PAM."""
        try:
            if pam.pam().authenticate(username, password, service='login'):
                try:
                    name = pwd.getpwnam(username).pw_gecos.split(',')[0] or username
                except KeyError:
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

    def logout(self):
        """Clear auth state and return to login."""
        st.session_state.update(
            authenticated=False,
            username=None,
            name=None,
            confirm_reboot=False,
            confirm_shutdown=False,
            confirm_reboot_token="",
            confirm_shutdown_token="",
        )
        st.rerun()
    
    def show_login_form(self):
        """Display login form UI."""
        with st.container(horizontal_alignment="center", vertical_alignment="center"), st.form("login_form", width="content"):
            st.title("🔐 Login")
            st.markdown("Enter your Linux username and password")
            username = st.text_input("Username", placeholder="Enter your Linux username")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            if st.form_submit_button("Login", width="stretch"):
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
    def severity_text(val, low=30, high=80):
        if val < low:
            return "Normal"
        if val < high:
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
            chart_data=hist,
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


class PiUI:
    """Main UI renderer for dashboard tabs."""
    
    def __init__(self, with_metrics=True):
        self.stats = None
        if with_metrics:
            self.stats = PiStats()
            self.stats.refresh()
        self.controller = PiController()
        self.ui = UIComponents()
        if self.stats is not None:
            MetricHistory.update(self.stats.cpu, self.stats.ram, self.stats.cpu_temp)
    
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
        st.subheader("System Health")
        cpu_state = self.ui.severity_text(self.stats.cpu)
        ram_state = self.ui.severity_text(self.stats.ram)
        disk_state = self.ui.severity_text(self.stats.disk.percent, low=70, high=90)
        overall = "Critical" if "Critical" in {cpu_state, ram_state, disk_state} else ("Warning" if "Warning" in {cpu_state, ram_state, disk_state} else "Healthy")
        status_color = "red" if overall == "Critical" else ("orange" if overall == "Warning" else "green")
        st.markdown(f":{status_color}-badge[Overall Status: {overall}]")

        st.markdown("#### Compute")
        compute_cols = st.columns(3)
        with compute_cols[0]:
            self.ui.metric_chart(
                f"CPU Usage ({cpu_state})",
                self.stats.cpu,
                st.session_state.cpu_hist,
                "%",
                self.ui.get_color(self.stats.cpu),
            )
        with compute_cols[1]:
            self.ui.metric_chart(
                f"RAM Usage ({ram_state})",
                self.stats.ram,
                st.session_state.ram_hist,
                "%",
                self.ui.get_color(self.stats.ram),
            )
        with compute_cols[2]:
            temp_state = self.ui.severity_text(self.stats.cpu_temp, low=55, high=75)
            self.ui.metric_chart(
                f"CPU Temp ({temp_state})",
                self.stats.cpu_temp,
                st.session_state.cpu_temp_hist,
                "°C",
                self.ui.get_color(self.stats.cpu_temp, low=55, high=75),
            )

        st.markdown("#### Network")
        network_cols = st.columns(3)
        with network_cols[0], st.container(border=True, height="stretch"):
            st.markdown("IP Address")
            st.code(self.stats.ip)
        with network_cols[1]:
            st.metric(
                "Packets Sent",
                f"{round(self.stats.net_io.packets_sent/1000)}K",
                delta=f"{self.stats.net_io.bytes_sent / (1024 ** 2):.2f} MB",
                border=True,
            )
        with network_cols[2]:
            st.metric(
                "Packets Received",
                f"{round(self.stats.net_io.packets_recv/1000)}K",
                delta=f"{self.stats.net_io.bytes_recv / (1024 ** 2):.2f} MB",
                border=True,
            )

        st.markdown("#### Storage")
        storage_cols = st.columns(2)
        with storage_cols[0]:
            st.metric("Uptime", self.stats.uptime_val, border=True)
        with storage_cols[1], st.container(border=True, height="stretch"):
            color = self.ui.get_color(self.stats.disk.percent, 70, 90)
            st.markdown(f":{color}-badge[Disk Usage: {disk_state}]")
            st.progress(self.stats.disk.percent / 100, text=f"{self.stats.disk.percent:.2f}%")

        st.subheader("Top Processes by CPU")
        data = [{"PID": p["pid"], "Name": p["name"], 
                "CPU%": p["cpu_percent"], "RAM%": p["memory_percent"]} 
                for p in self.stats.processes]
        st.dataframe(
            data,
            column_config={
                "CPU%": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
                "RAM%": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100)
            },
            width="stretch"
        )
    
    def controls_tab(self):
        """Render system controls tab."""
        section_tabs = st.tabs(["Power & Lifecycle", "Updates", "Pironman Visual", "Pironman Advanced"])

        with section_tabs[0]:
            st.caption("Danger zone. These actions disconnect users and may interrupt active workloads.")
            power_cols = st.columns(2)
            with power_cols[0]:
                if st.button("Reboot Server", icon=":material/restart_alt:", width="stretch"):
                    st.session_state["confirm_reboot"] = True
                    st.session_state["confirm_shutdown"] = False
                    st.session_state["confirm_reboot_token"] = ""
            with power_cols[1]:
                if st.button("Power Off Server", icon=":material/power:", width="stretch"):
                    st.session_state["confirm_shutdown"] = True
                    st.session_state["confirm_reboot"] = False
                    st.session_state["confirm_shutdown_token"] = ""

            if st.session_state.get("confirm_reboot"):
                with st.container(border=True):
                    st.warning("Type REBOOT to confirm. This disconnects all active sessions.")
                    st.text_input("Confirmation token", key="confirm_reboot_token")
                    confirm_cols = st.columns(2)
                    with confirm_cols[0]:
                        if st.button(
                            "Confirm Reboot",
                            width="stretch",
                            key="confirm_reboot_action",
                            disabled=st.session_state.get("confirm_reboot_token", "").strip().upper() != "REBOOT",
                        ):
                            ok, msg, details = self.controller.reboot()
                            if ok:
                                st.warning(msg)
                            else:
                                st.error(f"{msg} {details.get('stderr', '')}".strip())
                    with confirm_cols[1]:
                        if st.button("Cancel", width="stretch", key="cancel_reboot_action"):
                            st.session_state["confirm_reboot"] = False
                            st.session_state["confirm_reboot_token"] = ""
                            st.rerun()

            if st.session_state.get("confirm_shutdown"):
                with st.container(border=True):
                    st.error("Type SHUTDOWN to confirm. The server will go offline immediately.")
                    st.text_input("Confirmation token", key="confirm_shutdown_token")
                    confirm_cols = st.columns(2)
                    with confirm_cols[0]:
                        if st.button(
                            "Confirm Power Off",
                            width="stretch",
                            key="confirm_shutdown_action",
                            disabled=st.session_state.get("confirm_shutdown_token", "").strip().upper() != "SHUTDOWN",
                        ):
                            ok, msg, details = self.controller.shutdown()
                            if ok:
                                st.error(msg)
                            else:
                                st.error(f"{msg} {details.get('stderr', '')}".strip())
                    with confirm_cols[1]:
                        if st.button("Cancel", width="stretch", key="cancel_shutdown_action"):
                            st.session_state["confirm_shutdown"] = False
                            st.session_state["confirm_shutdown_token"] = ""
                            st.rerun()

        with section_tabs[1]:
            if st.button("Check for Package Updates", icon=":material/update:", width="stretch"):
                with st.status("Fetching package metadata...", expanded=False):
                    ok, msg, details = self.controller.check_updates()
                    if ok:
                        if msg == "System is up-to-date.":
                            st.success(msg)
                        else:
                            st.code(msg)
                    else:
                        st.error(f"{msg} {details.get('stderr', '')}".strip())

        # Get current config used by visual + advanced sections.
        config = self.controller.get_pironman5_config()
        system_config = config.get("system", {}) if isinstance(config, dict) and "error" not in config else {}
        
        # Options for selectboxes
        style_options = ["solid", "breathing", "flow", "flow_reverse", "rainbow", "rainbow_reverse", "hue_cycle"]
        fan_mode_options = ["Always On", "Performance", "Cool", "Balanced", "Quiet"]
        rotation_options = [0, 180]
        
        # Get current values
        current_rgb_enable = bool(system_config.get("rgb_enable", True))
        current_rgb_color = system_config.get("rgb_color", "ffffff")
        current_rgb_brightness = int(system_config.get("rgb_brightness", 50))
        current_rgb_style = system_config.get("rgb_style", "hue_cycle")
        current_rgb_speed = int(system_config.get("rgb_speed", 50))
        current_rgb_led_count = int(system_config.get("rgb_led_count", 4))
        current_fan_mode = int(system_config.get("gpio_fan_mode", 0))
        current_oled_enable = bool(system_config.get("oled_enable", True))
        current_oled_rotation = int(system_config.get("oled_rotation", 0))
        current_oled_disk = system_config.get("oled_disk", "total")
        current_oled_network = system_config.get("oled_network_interface", "all")
        current_oled_timeout = int(system_config.get("oled_sleep_timeout", 10))
        
        with section_tabs[2]:
            with st.container(border=True):
                st.markdown("#### Visual Controls")
                st.caption("Adjust appearance and fan profile. Changes are previewed before apply.")
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    rgb_enable = st.toggle("RGB Enabled", value=current_rgb_enable)
                    rgb_color = st.color_picker("RGB Color", value=f"#{current_rgb_color}")
                    rgb_style = st.selectbox("RGB Style", options=style_options, index=style_options.index(current_rgb_style) if current_rgb_style in style_options else 0)
                with col_b:
                    rgb_brightness = st.slider("Brightness", 0, 100, current_rgb_brightness)
                    rgb_speed = st.slider("Animation Speed", 0, 100, current_rgb_speed)
                    rgb_led_count = st.slider("LED Count", 1, 100, current_rgb_led_count)
                with col_c:
                    fan_mode = st.selectbox("Fan Mode", options=list(range(5)), index=current_fan_mode if 0 <= current_fan_mode < 5 else 0, format_func=lambda x: fan_mode_options[x])
                    oled_enable = st.toggle("OLED Enabled", value=current_oled_enable)
                    oled_rotation = st.selectbox("OLED Rotation", options=rotation_options, index=0 if current_oled_rotation == 0 else 1)

                pending = {
                    "rgb_enable": bool(rgb_enable),
                    "rgb_color": rgb_color.lstrip("#").lower().strip(),
                    "rgb_brightness": int(rgb_brightness),
                    "rgb_style": str(rgb_style),
                    "rgb_speed": int(rgb_speed),
                    "rgb_led_count": int(rgb_led_count),
                    "gpio_fan_mode": int(fan_mode),
                    "oled_enable": bool(oled_enable),
                    "oled_rotation": int(oled_rotation),
                    "oled_disk": str(current_oled_disk),
                    "oled_network_interface": str(current_oled_network),
                    "oled_sleep_timeout": int(current_oled_timeout),
                }

                st.caption("Pending changes preview")
                st.json(pending, expanded=False)
                if st.button("Apply Visual Changes", width="stretch"):
                    with st.status("Applying settings and restarting service...", expanded=False) as status:
                        ok, msg, details = self.controller.apply_pironman5_config(pending)
                        if ok:
                            status.update(label="Settings applied", state="complete")
                            st.success(msg)
                            st.rerun()
                        else:
                            status.update(label="Failed to apply settings", state="error")
                            st.error(f"{msg} {details.get('stderr', '')}".strip())

        with section_tabs[3]:
            with st.expander("Advanced fields", expanded=False):
                oled_disk = st.text_input("OLED Disk", value=str(current_oled_disk), help="Example: total, nvme0n1")
                oled_network = st.text_input("OLED Network Interface", value=str(current_oled_network), help="Example: all, eth0, wlan0")
                oled_timeout = st.number_input("OLED Sleep Timeout (seconds)", min_value=0, step=1, value=int(current_oled_timeout))
                st.caption("Advanced settings are applied with the current visual controls.")
                if st.button("Apply Advanced Fields", width="stretch"):
                    config_dict = {
                        "rgb_enable": bool(system_config.get("rgb_enable", True)),
                        "rgb_color": str(system_config.get("rgb_color", "ffffff")).strip().lower(),
                        "rgb_brightness": int(system_config.get("rgb_brightness", 50)),
                        "rgb_style": str(system_config.get("rgb_style", "hue_cycle")),
                        "rgb_speed": int(system_config.get("rgb_speed", 50)),
                        "rgb_led_count": int(system_config.get("rgb_led_count", 4)),
                        "gpio_fan_mode": int(system_config.get("gpio_fan_mode", 0)),
                        "oled_enable": bool(system_config.get("oled_enable", True)),
                        "oled_rotation": int(system_config.get("oled_rotation", 0)),
                        "oled_disk": oled_disk.strip(),
                        "oled_network_interface": oled_network.strip(),
                        "oled_sleep_timeout": int(oled_timeout),
                    }
                    with st.status("Applying advanced fields...", expanded=False):
                        ok, msg, details = self.controller.apply_pironman5_config(config_dict)
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(f"{msg} {details.get('stderr', '')}".strip())
    
    def nas_tab(self):
        """Render NAS management tab."""
        nas = PiNAS()
        self._init_nas_state(nas)

        st.subheader("NAS Overview")
        status_cols = st.columns(2)

        with status_cols[0], st.container(border=True, height="stretch"):
            st.subheader("RAID")
            ok, raid_status, details = nas.raid_status()
            if ok:
                st.code(raid_status or "No RAID information found")
            else:
                st.error(f"{raid_status} {details.get('stderr', '')}".strip())
            _, rebuild, _ = nas.rebuild_progress()
            st.caption("Rebuild / Sync status")
            st.code(rebuild)
            if st.button("Open RAID Manager", width="stretch"):
                self._raid_management_dialog(nas)

        with status_cols[1], st.container(border=True, height="stretch"):
            st.subheader("Samba Shares")
            ok, smb_status, details = nas.show_samba_share_status()
            if ok:
                st.code(smb_status)
            else:
                st.error(f"{smb_status} {details.get('stderr', '')}".strip())
            if nas.smb_shares:
                st.dataframe(
                    nas.smb_shares,
                    hide_index=True,
                    width="stretch",
                )
            if st.button("Open Samba Share Manager", width="stretch"):
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
        ok, arrays_raw, details = nas.detect_arrays()
        arrays = []
        if ok and arrays_raw:
            for line in arrays_raw.splitlines():
                line = line.strip()
                if line.startswith("ARRAY "):
                    parts = line.split()
                    if len(parts) >= 2:
                        arrays.append(parts[1])

        st.subheader("Restore existing arrays")
        if ok:
            st.code(arrays_raw.strip() if arrays_raw else "No arrays detected.")
        else:
            st.error(f"{arrays_raw} {details.get('stderr', '')}".strip())
        if st.button("Assemble detected arrays", width="stretch", disabled=not arrays):
            ok, msg, op_details = nas.restore_detected_arrays()
            if ok:
                st.success(msg or "Assemble command executed.")
            else:
                st.error(f"{msg} {op_details.get('stderr', '')}".strip())

        st.divider()
        st.subheader("Build new array")
        if drive_options:
            selected = st.multiselect(
                "Pick drives",
                options=list(drive_options.keys()),
                key="raid_drive_multiselect",
            )
            level = st.selectbox("RAID level", ["0", "1", "5", "10"], index=1)
            confirm_text = st.text_input("Type CREATE to confirm RAID creation", key="raid_create_confirm")
            if st.button("Create array", width="stretch", disabled=not selected):
                if confirm_text.strip().upper() != "CREATE":
                    st.warning("Type CREATE before creating a new RAID array.")
                    return
                disks = [drive_options[label] for label in selected]
                with st.status("Provisioning RAID…", expanded=True) as status:
                    status.write(f"Disks: {', '.join(disks)}")
                    status.write(f"Level: {level}")
                    ok, msg, op_details = nas.create_raid(disks, level)
                    status.update(label="Complete" if ok else "Failed", state="complete" if ok else "error")
                if ok:
                    st.success(msg)
                else:
                    st.error(f"{msg} {op_details.get('stderr', '')}".strip())
        else:
            st.info("No eligible drives detected.")

        st.divider()
        st.subheader("Rebuild / Sync array")
        pick = st.selectbox(
            "Select array",
            options=arrays or ["/dev/md0"],
            index=0,
            key="raid_array_select",
        )
        repair_token = st.text_input("Type REPAIR to confirm sync action", key="raid_repair_confirm")
        if st.button("Trigger repair sync", width="stretch", disabled=not arrays):
            if repair_token.strip().upper() != "REPAIR":
                st.warning("Type REPAIR before triggering sync.")
                return
            ok, msg, op_details = nas.resync_array(pick)
            if ok:
                st.success(msg or "Repair command issued.")
            else:
                st.error(f"{msg} {op_details.get('stderr', '')}".strip())

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
                    width="stretch",
                    disabled=not linux_users,
                )
            with disable_col:
                disable_user = st.form_submit_button(
                    "Disable User",
                    width="stretch",
                    disabled=not linux_users,
                    type="secondary",
                )
            if submitted:
                ok, msg, details = nas.add_samba_user(username, password)
                if ok:
                    st.success(msg)
                else:
                    st.error(f"{msg} {details.get('stderr', '')}".strip())
            elif disable_user:
                ok, msg, details = nas.disable_samba_user(username)
                if ok:
                    st.warning(msg)
                else:
                    st.error(f"{msg} {details.get('stderr', '')}".strip())

        st.subheader("Shares")
        share_rows_df = st.data_editor(
            st.session_state["smb_share_rows"],
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            key="smb_share_editor",
            column_config={
                "allow_guest": st.column_config.CheckboxColumn("Guest access"),
                "read_only": st.column_config.CheckboxColumn("Read only"),
            },
        )
        share_rows = share_rows_df.to_dict("records") if hasattr(share_rows_df, "to_dict") else share_rows_df
        st.session_state["smb_share_rows"] = share_rows

        if st.button("Save shares", width="stretch"):
            duplicate_names = len({(row.get("name") or "").strip() for row in share_rows if row.get("name")}) != len(
                [(row.get("name") or "").strip() for row in share_rows if row.get("name")]
            )
            valid = [
                {
                    "name": (row.get("name") or "").strip(),
                    "path": (row.get("path") or "/mnt/nas").strip(),
                    "allow_guest": bool(row.get("allow_guest")),
                    "read_only": bool(row.get("read_only")),
                }
                for row in share_rows
                if row.get("name") and row.get("path")
            ]
            if not valid:
                st.warning("Add at least one share with a name and path.")
            elif duplicate_names:
                st.error("Share names must be unique.")
            elif any(not row["path"].startswith("/") for row in valid):
                st.error("Each share path must be an absolute path (start with '/').")
            else:
                ok, msg, details = nas.configure_samba_shares(valid)
                if not ok:
                    st.error(f"{msg} {details.get('stderr', '')}".strip())
                else:
                    st.session_state["smb_share_rows"] = [dict(share) for share in valid]
                    check_ok, state_msg, _ = nas.samba_service_status()
                    verification = f"Samba service status: {state_msg}" if check_ok else "Samba service status could not be verified."
                    st.success(f"{msg} {verification}".strip())


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
        header_cols = st.columns([9, 1, 1], vertical_alignment="center", gap="xxsmall")
        with header_cols[0]:
            st.title("Pi Admin Dashboard")
        with header_cols[1]:
            display_name = st.session_state.get("name") or st.session_state.get("username") or "Unknown"
            st.caption(f":material/account_circle: :blue-badge[{display_name}]")
        with header_cols[2]:
            if st.button("Logout", width="stretch"):
                self.auth.logout()

        tabs = st.tabs([":material/bar_chart: System", ":material/settings: Controls", ":material/storage: NAS"])
        
        with tabs[0]:
            st.caption("System metrics auto-refresh every 5 seconds.")
            @st.fragment(run_every="5s")
            def system_content():
                st.session_state["last_refresh_at"] = datetime.now().strftime("%H:%M:%S")
                PiUI(with_metrics=True).system_tab()
            system_content()
        
        with tabs[1]:
            st.caption("Controls are applied on demand and do not auto-refresh.")
            PiUI(with_metrics=False).controls_tab()
        
        with tabs[2]:
            st.caption("NAS status is read on demand when this tab renders.")
            PiUI(with_metrics=False).nas_tab()


if __name__ == "__main__":
    app = DashboardApp()
    app.render()