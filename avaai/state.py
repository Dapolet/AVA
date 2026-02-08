import streamlit as st

from .chat_manager import ChatManager
from .config import load_config
from .monitoring.db import init_db
from .openrouter_client import OpenRouterClient
from .plugins.loader import load_plugins
from .plugins.registry import PluginRegistry


def init_app_state(base_dir: str) -> None:
    if st.session_state.get("app_initialized"):
        return

    config = load_config(base_dir)
    init_db(config.monitoring_db_path)

    client = OpenRouterClient(config.api_key or "")
    chat_manager = ChatManager(client)

    registry = PluginRegistry()
    load_plugins(config.plugins_dir, registry, config.monitoring_db_path)

    st.session_state["config"] = config
    st.session_state["client"] = client
    st.session_state["chat_manager"] = chat_manager
    st.session_state["plugin_registry"] = registry
    st.session_state["app_initialized"] = True
