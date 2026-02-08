import streamlit as st


def require_admin_access(config, page_key: str) -> bool:
    if not config.admin_password:
        st.warning("ADMIN_PASSWORD is not configured. Set it in env or Streamlit secrets.")
        return False

    if st.session_state.get("admin_authenticated"):
        return True

    st.subheader("Admin Login")
    password = st.text_input(
        "Admin password",
        type="password",
        key=f"admin_password_{page_key}",
    )
    if st.button("Login", key=f"admin_login_{page_key}"):
        if password == config.admin_password:
            st.session_state["admin_authenticated"] = True
            return True
        st.error("Invalid password")
        return False

    return False
