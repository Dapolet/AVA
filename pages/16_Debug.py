import os
import streamlit as st

from avaai.admin_auth import require_admin_access
from avaai.state import init_app_state
from avaai.settings_store import load_settings


def main():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    init_app_state(base_dir)

    st.title("\U0001F50D Debug Logs")

    config = st.session_state.get("config")
    if not config or not require_admin_access(config, page_key="debug"):
        return
    settings = load_settings(base_dir)

    st.subheader("Session State (model-related)")
    st.json({
        "selected_model": st.session_state.get("selected_model"),
        "selected_model_widget": st.session_state.get("selected_model_widget"),
        "default_model": "trinity-large-preview:free",
        "api_key_set": bool(config.api_key) if config else False,
        "settings_selected_model": settings.get("selected_model")
    })

    st.subheader("Debug Events")
    logs = st.session_state.get("debug_logs", [])
    if not logs:
        st.info("No debug logs yet.")
        return

    st.write(f"Total logs: {len(logs)}")
    st.json(logs[-50:])


if __name__ == "__main__":
    main()

