import os

import streamlit as st

from avaai.admin_auth import require_admin_access
from avaai.monitoring.audit import log_admin_action
from avaai.plugins.loader import list_manifests, set_plugin_enabled, load_plugins
from avaai.plugins.registry import PluginRegistry
from avaai.state import init_app_state


def _base_dir() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main():
    init_app_state(_base_dir())
    config = st.session_state["config"]
    registry = st.session_state.get("plugin_registry")

    st.title("Plugin Management")

    if not require_admin_access(config, page_key="plugins"):
        return

    manifests = list_manifests(config.plugins_dir)
    if not manifests:
        st.info("No plugins found in the plugins directory.")
        return

    table_rows = []
    for manifest in manifests:
        plugin_id = manifest.get("id", "unknown")
        info = registry.get(plugin_id) if registry else None
        table_rows.append({
            "id": plugin_id,
            "name": manifest.get("name", ""),
            "version": manifest.get("version", ""),
            "enabled": manifest.get("enabled", True),
            "loaded": info is not None
        })

    st.subheader("Installed Plugins")
    st.dataframe(table_rows, width="stretch")

    st.subheader("Toggle Plugin")
    plugin_ids = [m.get("id", "unknown") for m in manifests]
    selected_id = st.selectbox("Plugin ID", options=plugin_ids)
    selected_manifest = next((m for m in manifests if m.get("id") == selected_id), None)

    if selected_manifest:
        enabled = st.checkbox("Enabled", value=selected_manifest.get("enabled", True))
        if st.button("Save"):
            if set_plugin_enabled(config.plugins_dir, selected_id, enabled):
                log_admin_action(
                    config.monitoring_db_path,
                    actor="admin",
                    action="set_plugin_enabled",
                    details=f"{selected_id} => {enabled}"
                )
                st.success("Plugin settings updated. Reload to apply.")
            else:
                st.error("Failed to update plugin manifest.")

    st.subheader("Reload Plugins")
    if st.button("Reload"):
        new_registry = PluginRegistry()
        load_plugins(config.plugins_dir, new_registry, config.monitoring_db_path)
        st.session_state["plugin_registry"] = new_registry
        log_admin_action(
            config.monitoring_db_path,
            actor="admin",
            action="reload_plugins",
            details="Reloaded plugins from manifest"
        )
        st.success("Plugins reloaded.")


if __name__ == "__main__":
    main()

