import os
from dataclasses import dataclass

try:
    import streamlit as st
except Exception:
    st = None


@dataclass
class AppConfig:
    api_key: str
    admin_password: str
    monitoring_db_path: str
    plugins_dir: str


def _get_secret(key: str, default: str = "") -> str:
    if st is not None:
        try:
            if hasattr(st, "secrets") and key in st.secrets:
                return st.secrets.get(key, default)
        except Exception:
            pass
    return os.getenv(key, default)


def load_config(base_dir: str) -> AppConfig:
    api_key = _get_secret("OPENROUTER_API_KEY", "")
    admin_password = _get_secret("ADMIN_PASSWORD", "")
    monitoring_db_path = _get_secret(
        "MONITORING_DB_PATH",
        os.path.join(base_dir, "data", "monitoring.db")
    )
    plugins_dir = _get_secret(
        "PLUGINS_DIR",
        os.path.join(base_dir, "plugins")
    )

    return AppConfig(
        api_key=api_key,
        admin_password=admin_password,
        monitoring_db_path=monitoring_db_path,
        plugins_dir=plugins_dir
    )
