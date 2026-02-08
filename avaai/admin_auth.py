import time

import streamlit as st


def require_admin_access(config, page_key: str) -> bool:
    if not config.admin_password:
        st.warning("ADMIN_PASSWORD is not configured. Set it in env or Streamlit secrets.")
        return False

    if st.session_state.get("admin_authenticated"):
        return True

    max_attempts = 5
    lock_seconds = 300
    now = time.time()
    lock_until = st.session_state.get("admin_lock_until", 0)
    if lock_until and now >= lock_until:
        st.session_state["admin_lock_until"] = 0
        st.session_state["admin_failed_attempts"] = 0
        lock_until = 0
    if lock_until and now < lock_until:
        remaining = int(lock_until - now)
        st.warning(f"Admin login locked. Try again in {remaining} seconds.")
        return False

    st.subheader("Admin Login")
    password = st.text_input(
        "Admin password",
        type="password",
        key=f"admin_password_{page_key}",
    )
    if st.button("Login", key=f"admin_login_{page_key}"):
        if password == config.admin_password:
            st.session_state["admin_authenticated"] = True
            st.session_state["admin_failed_attempts"] = 0
            st.session_state["admin_lock_until"] = 0
            return True
        attempts = int(st.session_state.get("admin_failed_attempts", 0)) + 1
        st.session_state["admin_failed_attempts"] = attempts
        if attempts >= max_attempts:
            st.session_state["admin_lock_until"] = now + lock_seconds
            st.error("Too many failed attempts. Login is locked for 5 minutes.")
            return False
        st.error("Invalid password")
        return False

    return False
