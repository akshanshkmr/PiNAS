import streamlit as st
import pam
import pwd
import hmac
import hashlib
import secrets
import time
import json
from pathlib import Path
from math import inf


SESSION_MAX_AGE = inf


def linux_user_options():
    """Return list of eligible Linux usernames (uid >= 1000, valid shell)."""
    valid_users = []
    for entry in pwd.getpwall():
        if entry.pw_uid >= 1000 and entry.pw_shell not in ("/usr/sbin/nologin", "/bin/false"):
            valid_users.append(entry.pw_name)
    return sorted(set(valid_users))


def _load_secret_key():
    """Load or generate a persistent HMAC signing key."""
    key_path = Path(__file__).parent / ".session_secret"
    try:
        key = key_path.read_text().strip()
        if len(key) >= 64:
            return key
    except OSError:
        pass
    key = secrets.token_hex(32)
    key_path.write_text(key)
    key_path.chmod(0o600)
    return key


_SECRET_KEY = _load_secret_key()


def _sign_session(username, name):
    """Create an HMAC-signed session token with expiry."""
    expires = int(time.time()) + SESSION_MAX_AGE
    payload = json.dumps({"u": username, "n": name, "exp": expires}, separators=(",", ":"))
    sig = hmac.new(_SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _verify_session(token):
    """Verify and decode a signed session token. Returns (username, name) or None."""
    if not token or "." not in token:
        return None
    last_dot = token.rfind(".")
    payload = token[:last_dot]
    sig = token[last_dot + 1:]
    expected = hmac.new(_SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return None
    if data.get("exp", 0) < int(time.time()):
        return None
    username = data.get("u")
    if not username:
        return None
    return username, data.get("n") or username


class AuthManager:
    """Handles user authentication and session management."""

    def __init__(self, cookies):
        self.cookies = cookies
        self.init_session_state()

    def init_session_state(self):
        """Initialize authentication session state, restoring from cookies if available."""
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

        # Process deferred cookie operations from the previous render cycle.
        # st.rerun() discards the current render, so cookie ops queued before
        # it never reach the JS component. We save the intent to session state
        # and execute it here, on the fresh CookieController instance.
        pending_token = st.session_state.pop("_pending_cookie_set", None)
        if pending_token:
            self.cookies.set("pi_auth_session", pending_token)

        pending_logout = st.session_state.pop("_pending_cookie_remove", False)
        if pending_logout:
            self.cookies.remove("pi_auth_session")
            return None # Don't restore from cookie after logout

        if not st.session_state['authenticated']:
            token = self.cookies.get("pi_auth_session")
            result = _verify_session(token)
            if result:
                st.session_state.update(
                    authenticated=True,
                    username=result[0],
                    name=result[1],
                )
            elif token is not None:
                self.cookies.remove("pi_auth_session")

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
        except Exception:
            return False, None

    def login(self, username, name):
        """Set session state after successful login and persist signed token to cookie."""
        st.session_state.update(
            authenticated=True,
            username=username,
            name=name,
            _pending_cookie_set=_sign_session(username, name),
        )
        st.rerun()

    def logout(self):
        """Clear auth state, remove cookies, and return to login."""
        st.session_state.update(
            authenticated=False,
            username=None,
            name=None,
            confirm_reboot=False,
            confirm_shutdown=False,
            confirm_reboot_token="",
            confirm_shutdown_token="",
            _pending_cookie_remove=True,
        )
        st.rerun()

    def show_login_form(self):
        """Display login form UI."""
        users = linux_user_options()
        with st.container(horizontal_alignment="center", vertical_alignment="center"), st.form("login_form", width="content"):
            st.title("Pi Admin Dashboard", text_alignment="center")
            st.markdown("Select your Linux user and enter your password")
            if users:
                username = st.selectbox("Username", options=users)
            else:
                username = st.text_input("Username", placeholder="Enter your Linux username")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            if st.form_submit_button("Login", width="stretch", icon=":material/login:"):
                if not (username and password):
                    st.error("Please enter both username and password")
                else:
                    with st.spinner("Authenticating..."):
                        authenticated, name = self.authenticate(username, password)
                    if authenticated:
                        self.login(username, name)
                    else:
                        st.error("Invalid username or password. Please try again.")

