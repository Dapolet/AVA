import json
import os
from datetime import datetime

import streamlit as st

from avaai.admin_auth import require_admin_access
from avaai.chat_manager import ChatManager
from avaai.monitoring.metrics import get_usage_summary
from avaai.openrouter_client import OpenRouterClient
from avaai.state import init_app_state
from avaai.settings_store import load_settings, save_settings


@st.cache_data(ttl=600)
def _get_models_cached(api_key: str, base_url: str):
    client = OpenRouterClient(api_key, base_url)
    return client.get_models()


@st.cache_data(ttl=30)
def _get_usage_summary_cached(db_path: str):
    return get_usage_summary(db_path)


def main():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    init_app_state(base_dir)

    config = st.session_state["config"]
    client: OpenRouterClient = st.session_state["client"]
    chat_manager: ChatManager = st.session_state["chat_manager"]

    default_model = "trinity-large-preview:free"
    settings = load_settings(base_dir)
    st.session_state.setdefault("selected_model", settings.get("selected_model") or default_model)
    st.session_state.setdefault("temperature", settings.get("temperature", 0.7))
    st.session_state.setdefault("max_tokens", settings.get("max_tokens", 500))
    st.session_state.setdefault("use_streaming", settings.get("use_streaming", True))
    st.session_state.setdefault("enable_tools", settings.get("enable_tools", False))
    st.session_state.setdefault("price_per_1k", settings.get("price_per_1k", 0.0))
    st.session_state.setdefault("use_async", settings.get("use_async", False))
    st.session_state.setdefault("selected_model_widget", st.session_state["selected_model"])

    st.title("\u2699\ufe0f Settings")

    if not require_admin_access(config, page_key="settings"):
        return

    api_key = config.api_key
    if not api_key:
        st.warning("OPENROUTER_API_KEY is not configured. Set it in Streamlit secrets or environment variables.")
    elif api_key != client.api_key:
        client.set_api_key(api_key)

    st.session_state.setdefault("use_async_widget", st.session_state.get("use_async", False))
    use_async = st.checkbox("Async mode", key="use_async_widget")
    st.session_state["use_async"] = use_async

    st.subheader("Model Settings")
    with st.spinner("Loading available models..."):
        try:
            models = _get_models_cached(api_key, client.base_url) if api_key else []
            model_ids = [model['id'] for model in models if model.get('id')]
            if not model_ids:
                model_ids = [st.session_state.get("selected_model", default_model)]
            free_models = [m for m in model_ids if 'free' in m.lower() or 'gpt-3.5' in m.lower()]
            paid_models = [m for m in model_ids if m not in free_models]
            options = free_models + paid_models if (free_models or paid_models) else model_ids
            current = st.session_state.get("selected_model", options[0])
            if current and current not in options:
                options = [current] + options
            index = options.index(current) if current in options else 0
            st.session_state.setdefault("selected_model_widget", current or options[index])
            if st.session_state["selected_model_widget"] not in options:
                st.session_state["selected_model_widget"] = options[index]
            st.selectbox(
                "Select Model",
                options=options,
                index=options.index(st.session_state["selected_model_widget"]),
                key="selected_model_widget"
            )
            selected_model = st.session_state.get("selected_model_widget", current)
            if st.session_state.get("selected_model") != selected_model:
                st.session_state["selected_model"] = selected_model
            if selected_model:
                model_info = client.get_model_info(selected_model)
                if model_info:
                    with st.expander("Model Details"):
                        st.write(f"**ID:** {model_info.get('id')}")
                        st.write(f"**Context Length:** {model_info.get('context_length', 'N/A')}")
                        st.write(f"**Description:** {model_info.get('description', 'N/A')}")
        except Exception as e:
            st.error(f"Failed to load models: {e}")
            fallback = st.session_state.get("selected_model", default_model)
            st.session_state["selected_model_widget"] = fallback
            st.selectbox(
                "Select Model",
                options=[fallback],
                index=0,
                key="selected_model_widget"
            )

    def _use_custom_model():
        custom = st.session_state.get("custom_model", "").strip()
        if custom:
            st.session_state["selected_model"] = custom
            st.session_state["selected_model_widget"] = custom

    st.text_input("Custom model ID", key="custom_model")
    st.button("Use custom model", on_click=_use_custom_model)

    st.subheader("Generation Parameters")
    st.session_state.setdefault("temperature_widget", st.session_state.get("temperature", 0.7))
    temperature = st.slider(
        "Temperature",
        min_value=0.1,
        max_value=2.0,
        step=0.1,
        key="temperature_widget",
        help="Higher values = more creative, Lower values = more focused"
    )
    st.session_state["temperature"] = temperature

    st.session_state.setdefault("max_tokens_widget", int(st.session_state.get("max_tokens", 500)))
    max_tokens = st.number_input(
        "Max Tokens",
        min_value=50,
        max_value=4000,
        step=50,
        key="max_tokens_widget",
        help="Maximum length of response"
    )
    st.session_state["max_tokens"] = max_tokens

    st.session_state.setdefault("use_streaming_widget", st.session_state.get("use_streaming", True))
    use_streaming = st.checkbox(
        "Stream Response",
        key="use_streaming_widget",
        help="Stream the response token by token"
    )
    st.session_state["use_streaming"] = use_streaming

    st.session_state.setdefault("enable_tools_widget", st.session_state.get("enable_tools", False))
    enable_tools = st.checkbox(
        "Enable tools",
        key="enable_tools_widget",
        help="Allow tool calling in non-streaming mode"
    )
    st.session_state["enable_tools"] = enable_tools

    st.session_state.setdefault("price_per_1k_widget", float(st.session_state.get("price_per_1k", 0.0)))
    price_per_1k = st.number_input(
        "Price per 1K tokens (USD)",
        min_value=0.0,
        max_value=100.0,
        step=0.001,
        format="%.3f",
        key="price_per_1k_widget"
    )
    st.session_state["price_per_1k"] = price_per_1k

    def _save_all_settings():
        selected_model = (
            st.session_state.get("selected_model_widget")
            or st.session_state.get("selected_model")
            or default_model
        )
        st.session_state["selected_model"] = selected_model
        save_settings(base_dir, {
            "selected_model": selected_model,
            "temperature": st.session_state.get("temperature"),
            "max_tokens": st.session_state.get("max_tokens"),
            "use_streaming": st.session_state.get("use_streaming"),
            "enable_tools": st.session_state.get("enable_tools"),
            "price_per_1k": st.session_state.get("price_per_1k"),
            "use_async": st.session_state.get("use_async"),
        })
        st.success("Settings saved.")

    if st.button("Save Settings"):
        _save_all_settings()

    st.subheader("Quick Commands")
    command_templates = {
        "Summarize this conversation": "Summarize our conversation so far.",
        "Create action items": "Create a list of action items from our conversation.",
        "Explain last answer": "Explain your last answer with examples.",
        "Translate to English": "Translate your last answer to English.",
    }
    selected_template = st.selectbox(
        "Templates",
        options=[""] + list(command_templates.keys()),
        key="command_template"
    )
    col_c, col_d = st.columns(2)
    with col_c:
        if st.button("Insert Template") and selected_template:
            st.session_state["draft_prompt"] = command_templates[selected_template]
            st.rerun()
    with col_d:
        if st.button("Send Template") and selected_template:
            st.session_state["queued_prompt"] = command_templates[selected_template]
            st.rerun()

    recent_prompts = st.session_state.get("recent_prompts", [])
    if recent_prompts:
        picked_recent = st.selectbox("Recent prompts", options=[""] + recent_prompts, key="recent_prompt")
        if st.button("Use Recent") and picked_recent:
            st.session_state["draft_prompt"] = picked_recent
            st.rerun()

    st.subheader("History")
    default_history_path = os.path.join(
        base_dir,
        "data",
        f"chat_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    history_path = st.text_input("Save path", value=default_history_path, key="history_path")
    compact_history = st.checkbox("Compact (strip big images)", value=True, key="compact_history")
    if st.button("Save History"):
        os.makedirs(os.path.dirname(history_path), exist_ok=True)
        chat_manager.save_to_file(history_path, compact=compact_history)
        st.success(f"Saved to {history_path}")

    uploaded_history = st.file_uploader("Load history (.json)", type=["json"], key="history_upload")
    if uploaded_history:
        try:
            data = json.loads(uploaded_history.getvalue().decode("utf-8"))
            chat_manager.load_from_data(data)
            st.success("History loaded")
        except Exception as exc:
            st.error(f"Failed to load history: {exc}")

    st.subheader("Export")
    st.download_button(
        "Download JSON",
        data=chat_manager.export_json(compact=True),
        file_name="chat_history.json",
        mime="application/json"
    )
    st.download_button(
        "Download Markdown",
        data=chat_manager.export_markdown(),
        file_name="chat_history.md",
        mime="text/markdown"
    )
    st.download_button(
        "Download Text",
        data=chat_manager.export_text(),
        file_name="chat_history.txt",
        mime="text/plain"
    )
    st.download_button(
        "Download CSV",
        data=chat_manager.export_csv(),
        file_name="chat_history.csv",
        mime="text/csv"
    )

    st.subheader("Usage")
    summary = _get_usage_summary_cached(config.monitoring_db_path)
    if summary:
        row = summary[0]
        st.metric("Total Tokens", row.get("total_tokens", 0))
        st.metric("Total Cost (USD)", f"{row.get('total_cost', 0):.4f}")

    st.subheader("Conversation")
    if st.button("\U0001F504 Clear Conversation", width="stretch"):
        chat_manager.clear_conversation()
        st.rerun()

    message_count = sum(
        1 for entry in chat_manager.conversation_history
        if isinstance(entry, dict) and entry.get("role") != "system"
    )
    st.metric("Messages in History", message_count)


if __name__ == "__main__":
    main()

