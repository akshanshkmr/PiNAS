import streamlit as st
from utils import PiController


def render_controls_tab():
    """Render system controls tab."""
    controller = PiController()
    section_tabs = st.tabs([":material/power: Power", ":material/update: Updates", ":material/computer: Pironman"])

    with section_tabs[0]:
        st.caption(":red[Danger zone. These actions disconnect users and may interrupt active workloads.]")
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
                    ok, msg, details = controller.reboot()
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
                    ok, msg, details = controller.shutdown()
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
                ok, msg, details = controller.check_updates()
                if ok:
                    if msg == "System is up-to-date.":
                        st.success(msg)
                    else:
                        st.code(msg)
                else:
                    st.error(f"{msg} {details.get('stderr', '')}".strip())

    # Get current config used by visual + advanced sections.
    config = controller.get_pironman5_config()
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
    current_fan_mode = int(system_config.get("gpio_fan_mode", 0))
    current_oled_enable = bool(system_config.get("oled_enable", True))
    current_oled_rotation = int(system_config.get("oled_rotation", 0))
    current_oled_disk = system_config.get("oled_disk", "total")
    current_oled_network = system_config.get("oled_network_interface", "all")
    current_oled_timeout = int(system_config.get("oled_sleep_timeout", 10))

    with section_tabs[2]:
        pironman_cols = st.columns(2)
        with pironman_cols[0].container(border=True, height="stretch"):
            st.caption("Adjust appearance and fan profile. Changes are previewed before apply.")
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                rgb_enable = st.toggle("RGB Enabled", value=current_rgb_enable)
                rgb_color = st.color_picker("RGB Color", value=f"#{current_rgb_color.strip('#')}")
                rgb_style = st.selectbox("RGB Style", options=style_options, index=style_options.index(current_rgb_style) if current_rgb_style in style_options else 0)
            with col_b:
                rgb_brightness = st.slider("Brightness", 0, 100, current_rgb_brightness)
                rgb_speed = st.slider("Animation Speed", 0, 100, current_rgb_speed)
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
                "gpio_fan_mode": int(fan_mode),
                "oled_enable": bool(oled_enable),
                "oled_rotation": int(oled_rotation),
                "oled_disk": str(current_oled_disk),
                "oled_network_interface": str(current_oled_network),
                "oled_sleep_timeout": int(current_oled_timeout),
            }

            if st.button("Apply Visual Changes", width="stretch"):
                with st.status("Applying settings and restarting service...", expanded=False) as status:
                    ok, msg, details = controller.apply_pironman5_config(pending)
                    if ok:
                        status.update(label="Settings applied", state="complete")
                        st.success(msg)
                        st.rerun()
                    else:
                        status.update(label="Failed to apply settings", state="error")
                        st.error(f"{msg} {details.get('stderr', '')}".strip())

        with pironman_cols[1].container(border=True, height="stretch"):
            st.caption("Advanced settings are applied with the current visual controls.")
            oled_disk = st.text_input("OLED Disk", value=str(current_oled_disk), help="Example: total, nvme0n1")
            oled_network = st.text_input("OLED Network Interface", value=str(current_oled_network), help="Example: all, eth0, wlan0")
            oled_timeout = st.number_input("OLED Sleep Timeout (seconds)", min_value=0, step=1, value=int(current_oled_timeout))
            if st.button("Apply Advanced Fields", width="stretch"):
                config_dict = {
                    "rgb_enable": bool(system_config.get("rgb_enable", True)),
                    "rgb_color": str(system_config.get("rgb_color", "ffffff")).strip().lower(),
                    "rgb_brightness": int(system_config.get("rgb_brightness", 50)),
                    "rgb_style": str(system_config.get("rgb_style", "hue_cycle")),
                    "rgb_speed": int(system_config.get("rgb_speed", 50)),
                    "gpio_fan_mode": int(system_config.get("gpio_fan_mode", 0)),
                    "oled_enable": bool(system_config.get("oled_enable", True)),
                    "oled_rotation": int(system_config.get("oled_rotation", 0)),
                    "oled_disk": oled_disk.strip(),
                    "oled_network_interface": oled_network.strip(),
                    "oled_sleep_timeout": int(oled_timeout),
                }
                with st.status("Applying advanced fields...", expanded=False):
                    ok, msg, details = controller.apply_pironman5_config(config_dict)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(f"{msg} {details.get('stderr', '')}".strip())

