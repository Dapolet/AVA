import os

import streamlit as st

from avaai.admin_auth import require_admin_access
from avaai.monitoring.audit import log_admin_action
from avaai.monitoring.metrics import (
    get_recent_requests,
    get_error_counts,
    get_top_models,
    get_admin_audit,
    get_usage_summary,
    get_daily_costs,
)
from avaai.state import init_app_state


def _base_dir() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main():
    init_app_state(_base_dir())
    config = st.session_state["config"]

    st.title("Admin Panel")

    if not require_admin_access(config, page_key="overview"):
        return

    st.subheader("Monitoring")
    summary = get_usage_summary(config.monitoring_db_path)
    summary_row = summary[0] if summary else {}
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Recent Requests", len(get_recent_requests(config.monitoring_db_path, 50)))
    with col2:
        errors = get_error_counts(config.monitoring_db_path)
        error_total = sum(row["count"] for row in errors if row["status"] == "error")
        st.metric("Errors", error_total)
    with col3:
        top_models = get_top_models(config.monitoring_db_path, 1)
        st.metric("Top Model", top_models[0]["model"] if top_models else "n/a")
    with col4:
        st.metric("Total Tokens", summary_row.get("total_tokens", 0))

    st.markdown("### Cost Summary")
    st.dataframe(get_daily_costs(config.monitoring_db_path, 14), width="stretch")
    st.caption(f"Total cost: ${summary_row.get('total_cost', 0):.4f} | Avg latency: {summary_row.get('avg_latency', 0):.0f} ms")

    st.markdown("### Recent Requests")
    st.dataframe(get_recent_requests(config.monitoring_db_path, 20), width="stretch")

    st.markdown("### Error Counts")
    st.dataframe(errors, width="stretch")

    st.markdown("### Top Models")
    st.dataframe(get_top_models(config.monitoring_db_path, 10), width="stretch")

    st.subheader("Admin Actions")
    chat_manager = st.session_state.get("chat_manager")
    if st.button("Clear Chat History"):
        if chat_manager:
            chat_manager.clear_conversation()
            log_admin_action(
                config.monitoring_db_path,
                actor="admin",
                action="clear_chat_history",
                details="Cleared conversation history"
            )
            st.success("Chat history cleared")
        else:
            st.warning("Chat manager not initialized")

    st.subheader("Admin Audit Log")
    st.dataframe(get_admin_audit(config.monitoring_db_path, 50), width="stretch")


if __name__ == "__main__":
    main()

