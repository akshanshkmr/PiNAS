import streamlit as st
from utils import PiNAS
from auth import linux_user_options


def _init_nas_state(nas):
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
def _raid_management_dialog(nas):
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
            with st.status("Provisioning RAID\u2026", expanded=True) as status:
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
def _samba_management_dialog(nas):
    with st.expander("Share users"), st.form("smb_user_form"):
        linux_users = linux_user_options()
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


def render_nas_tab():
    """Render NAS management tab."""
    nas = PiNAS()
    _init_nas_state(nas)

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
        st.caption(f"Rebuild / Sync status: :blue-badge[{rebuild}]")
        if st.button("Open RAID Manager", width="stretch"):
            _raid_management_dialog(nas)

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
            _samba_management_dialog(nas)

