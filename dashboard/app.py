import streamlit as st
from datetime import datetime
from streamlit_cookies_controller import CookieController
from auth import AuthManager
from tabs.system import render_system_tab
from tabs.controls import render_controls_tab
from tabs.nas import render_nas_tab

st.set_page_config(page_title="Pi Admin Dashboard", page_icon=":material/dashboard:", layout="wide")

cookies = CookieController()


class DashboardApp:
    """Main dashboard application controller."""

    def __init__(self):
        self.auth = AuthManager(cookies)

    def render(self):
        """Main render method - routes to login or dashboard."""
        if not st.session_state.authenticated:
            self.auth.show_login_form()
        else:
            self.dashboard()

    def dashboard(self):
        """Render main dashboard with tabs."""
        header_cols = st.columns(2, vertical_alignment="center")
        with header_cols[0]:
            st.title("Pi Admin Dashboard")
        with header_cols[1], st.container(horizontal_alignment="right"):
                if st.button("Logout", type="tertiary", icon=":material/logout:"):
                    self.auth.logout()

        tabs = st.tabs([":material/bar_chart: System", ":material/storage: NAS", ":material/settings: Controls"])

        with tabs[0]:
            st.caption("System metrics auto-refresh every 5 seconds.")
            @st.fragment(run_every="5s")
            def system_content():
                st.session_state["last_refresh_at"] = datetime.now().strftime("%H:%M:%S")
                render_system_tab()
            system_content()

        with tabs[1]:
            st.caption("NAS status is read on demand when this tab renders.")
            render_nas_tab()
        
        with tabs[2]:
            st.caption("Controls are applied on demand and do not auto-refresh.")
            render_controls_tab()


if __name__ == "__main__":
    app = DashboardApp()
    app.render()
