import logging
import os
import time
import re

import streamlit as st

from avaai.chat_manager import ChatManager
from avaai.monitoring.db import log_request
from avaai.openrouter_client import OpenRouterClient
from avaai.state import init_app_state
from avaai.settings_store import load_settings
from avaai.tools import get_tools, tool_call_to_message
from avaai.utils import (
    build_content_parts,
    calculate_cost_usd,
    estimate_tokens_for_messages,
    estimate_tokens_from_text,
    run_async,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _sanitize_error(text: str, api_key: str) -> str:
    if api_key:
        return text.replace(api_key, "[redacted]")
    return text


def _render_message(message: dict) -> None:
    if message.get("role") == "system":
        return
    if message.get("metadata", {}).get("hidden"):
        return

    with st.chat_message(message.get("role", "assistant")):
        content = message.get("content")
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
            st.write("\n".join(text_parts).strip())
        else:
            st.write(content)

        attachments = message.get("metadata", {}).get("attachments") if message.get("metadata") else []
        if attachments:
            included = [a for a in attachments if a.get("included")]
            skipped = [a for a in attachments if not a.get("included")]
            if included:
                st.caption(f"Attachments included: {', '.join(a['name'] for a in included)}")
            if skipped:
                st.caption(f"Attachments skipped: {', '.join(a['name'] for a in skipped)}")


def chat_page() -> None:
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    init_app_state(base_dir)

    config = st.session_state["config"]
    client: OpenRouterClient = st.session_state["client"]
    chat_manager: ChatManager = st.session_state["chat_manager"]
    plugin_registry = st.session_state.get("plugin_registry")

    default_model = "arcee-ai/trinity-mini:free"
    settings = load_settings(base_dir)
    st.session_state.setdefault("selected_model", settings.get("selected_model") or default_model)
    st.session_state.setdefault("selected_model_widget", st.session_state["selected_model"])
    st.session_state.setdefault("temperature", settings.get("temperature", 0.7))
    st.session_state.setdefault("max_tokens", settings.get("max_tokens", 500))
    st.session_state.setdefault("use_streaming", settings.get("use_streaming", True))
    st.session_state.setdefault("enable_tools", settings.get("enable_tools", False))
    st.session_state.setdefault("price_per_1k", settings.get("price_per_1k", 0.0))
    st.session_state.setdefault("use_async", settings.get("use_async", False))
    st.session_state.setdefault("weather_last_result", None)
    st.session_state.setdefault("weather_last_location", "")
    st.session_state.setdefault("debug_logs", [])
    st.session_state.setdefault("draft_prompt", "")

    def _log_debug(event: str, data: dict | None = None):
        entry = {"event": event, "data": data or {}}
        st.session_state["debug_logs"].append(entry)

    st.title("\U0001F4AC AVA AI Chat")
    st.caption(" ")
    st.session_state.setdefault("attachments_uploader_key", 0)
    if st.button("Clear chat", type="secondary"):
        chat_manager.clear_conversation()
        st.session_state["draft_prompt"] = ""
        st.session_state.pop("queued_prompt", None)
        st.session_state["attachments_uploader_key"] += 1
        st.rerun()

    api_key = config.api_key
    if not api_key:
        st.warning(
            "OPENROUTER_API_KEY is not configured. "
            "Set it in Streamlit secrets or environment variables."
        )
        return

    if api_key != client.api_key:
        client.set_api_key(api_key)

    if (
        st.session_state.get("selected_model_widget")
        and st.session_state.get("selected_model") != st.session_state.get("selected_model_widget")
    ):
        st.session_state["selected_model"] = st.session_state["selected_model_widget"]
    selected_model = (
        st.session_state.get("selected_model")
        or st.session_state.get("selected_model_widget")
        or default_model
    )
    if not selected_model:
        selected_model = default_model
        st.session_state["selected_model"] = selected_model
    _log_debug(
        "model_resolved",
        {
            "selected_model": selected_model,
            "selected_model_state": st.session_state.get("selected_model"),
            "selected_model_widget": st.session_state.get("selected_model_widget"),
            "default_model": default_model,
            "settings_selected_model": settings.get("selected_model"),
        },
    )
    temperature = st.session_state.get("temperature")
    max_tokens = st.session_state.get("max_tokens")
    use_streaming = st.session_state.get("use_streaming")
    enable_tools = st.session_state.get("enable_tools")
    price_per_1k = st.session_state.get("price_per_1k")
    use_async = st.session_state.get("use_async")
    tools_unsupported_models = st.session_state.setdefault("tools_unsupported_models", [])

    for message in chat_manager.get_last_n_messages(20):
        _render_message(message)

    with st.sidebar:
        st.subheader("Attachments")
        uploaded_files = st.file_uploader(
            "Add files",
            accept_multiple_files=True,
            type=["png", "jpg", "jpeg", "webp", "txt", "md", "json", "csv"],
            key=f"chat_attachments_{st.session_state['attachments_uploader_key']}",
        )

    prompt_input = st.chat_input("Message", key="draft_prompt")
    queued_prompt = st.session_state.pop("queued_prompt", None)
    prompt = queued_prompt or prompt_input

    if not prompt:
        return

    prompt_lower = prompt.lower()
    is_rate_query = prompt_lower.startswith("/rate")
    is_weather_query = prompt_lower.startswith("/weather") or any(
        keyword in prompt_lower
        for keyword in (
            "weather",
            "forecast",
            "temperature",
            "погода",
            "прогноз",
            "температур",
            "ветер",
        )
    )

    def _detect_language(text: str) -> str:
        return "ru" if re.search(r"[А-Яа-яЁё]", text) else "en"



    def _is_wiki_auto(text: str) -> bool:
        strict_starts = (
            "who is",
            "what is",
            "\u043a\u0442\u043e \u0442\u0430\u043a\u043e\u0439",
            "\u0447\u0442\u043e \u0442\u0430\u043a\u043e\u0435",
        )
        keyword_anywhere = (
            "wiki",
            "wikipedia",
            "\u0432\u0438\u043a\u0438\u043f\u0435\u0434\u0438\u044f",
        )
        text = text.strip()
        if text.startswith(strict_starts):
            return True
        return any(k in text for k in keyword_anywhere)

    def _parse_rate_command(text: str):
        raw = text[len("/rate"):].strip()
        if not raw:
            return "USD", None, None, None
        parts = raw.split()
        base = None
        target = None
        amount = None

        if parts:
            if "/" in parts[0]:
                base_part, target_part = parts[0].split("/", 1)
                base = base_part.strip()
                target = target_part.strip() or None
                if len(parts) > 1:
                    amount = parts[1]
            else:
                base = parts[0]
                if len(parts) > 1:
                    target = parts[1]
                if len(parts) > 2:
                    amount = parts[2]

        if amount is not None:
            try:
                amount = float(amount)
            except (TypeError, ValueError):
                return base or "USD", target, None, "Invalid amount."

        if not base:
            base = "USD"

        return base, target, amount, None

    def _extract_rate_from_text(text: str):
        mapping = {
            "USD": [
                "usd", "dollar", "dollars", "buck", "bucks",
                "доллар", "доллара", "долларов",
            ],
            "EUR": [
                "eur", "euro", "euros",
                "евро",
            ],
            "RUB": [
                "rub", "ruble", "rubles",
                "рубль", "рубля", "рублей", "руб",
            ],
            "GBP": [
                "gbp", "pound", "pounds", "sterling",
                "фунт", "фунта", "фунтов", "фунт стерлингов",
            ],
            "JPY": [
                "jpy", "yen",
                "иена", "иен", "йена", "йен",
            ],
            "CNY": [
                "cny", "yuan", "renminbi",
                "юань", "юаней",
            ],
            "CHF": [
                "chf", "franc", "francs",
                "франк", "франка", "франков",
            ],
            "CAD": [
                "cad", "canadian dollar", "canadian dollars",
                "канадский доллар", "канадских долларов",
            ],
            "AUD": [
                "aud", "australian dollar", "australian dollars",
                "австралийский доллар", "австралийских долларов",
            ],
        }

        def _find_code(fragment: str) -> str | None:
            f = fragment.lower()
            for code, names in mapping.items():
                for name in names:
                    if name in f:
                        return code
            return None

        lower = text.lower()
        amount_match = re.search(r"(\d+(?:[.,]\d+)?)", lower)
        amount = None
        if amount_match:
            amount = float(amount_match.group(1).replace(",", "."))

        # RU: "сколько в евро 10 долларов"
        ru_match = re.search(r"сколько\s+в\s+(.+?)\s+(\d+(?:[.,]\d+)?)\s+(.+)", lower)
        if ru_match:
            target_code = _find_code(ru_match.group(1))
            base_code = _find_code(ru_match.group(3))
            amt = float(ru_match.group(2).replace(",", "."))
            if base_code and target_code:
                return base_code, target_code, amt

        # EN: "how much is 10 dollars in euro"
        en_match = re.search(r"how\s+much\s+is\s+(\d+(?:[.,]\d+)?)\s+(.+?)\s+in\s+(.+)", lower)
        if en_match:
            base_code = _find_code(en_match.group(2))
            target_code = _find_code(en_match.group(3))
            amt = float(en_match.group(1).replace(",", "."))
            if base_code and target_code:
                return base_code, target_code, amt

        # EN/RU: "convert 10 USD to EUR" / "конвертируй 10 долларов в евро"
        convert_match = re.search(r"(convert|exchange|конвертируй|переведи)\s+(\d+(?:[.,]\d+)?)\s+(.+?)\s+(to|в)\s+(.+)", lower)
        if convert_match:
            amt = float(convert_match.group(2).replace(",", "."))
            base_code = _find_code(convert_match.group(3))
            target_code = _find_code(convert_match.group(5))
            if base_code and target_code:
                return base_code, target_code, amt

        # Fallback: if we have amount and two currency mentions anywhere
        codes_found = []
        for code, names in mapping.items():
            for name in names:
                if name in lower:
                    codes_found.append(code)
                    break
        if amount is not None and len(codes_found) >= 2:
            return codes_found[0], codes_found[1], amount

        return None

    def _extract_location(text: str) -> str | None:
        match = re.search(r"\bin\s+([^\n\r,?.!;:]+)", text, flags=re.IGNORECASE)
        if not match:
            match = re.search(r"\bв\s+([^\n\r,?.!;:]+)", text, flags=re.IGNORECASE)
        if not match:
            return None
        location_text = match.group(1).strip()
        # Remove trailing temporal keywords (EN/RU) if present.
        location_text = re.sub(
            r"\b(today|tomorrow|tonight|now|сегодня|завтра|сейчас|ночью|утром|днём|днем|вечером)\b.*$",
            "",
            location_text,
            flags=re.IGNORECASE,
        ).strip()
        return re.sub(r"[\\?\\!\\.,;:]+$", "", location_text).strip() or None

    is_wiki_command = prompt_lower.startswith("/wiki")
    is_wiki_auto = _is_wiki_auto(prompt_lower) and not (is_rate_query or is_weather_query)

    rate_context = None
    if not is_rate_query:
        rate_context = _extract_rate_from_text(prompt)
    if is_rate_query or rate_context:
        with st.chat_message("user"):
            st.write(prompt)
        if is_rate_query:
            base, target, amount, parse_error = _parse_rate_command(prompt)
        else:
            base, target, amount = rate_context
            parse_error = None

        if parse_error:
            rate_result = {"status": "error", "message": parse_error}
        elif not plugin_registry or not plugin_registry.get("exchangerate_plugin"):
            rate_result = {"status": "error", "message": "Exchange rate plugin is not available."}
        else:
            plugin_info = plugin_registry.get("exchangerate_plugin")
            if hasattr(plugin_info, "enabled") and not plugin_info.enabled:
                rate_result = {"status": "error", "message": "Exchange rate plugin is not available."}
            else:
                rate_result = plugin_info.instance.run(
                    {
                        "base": base,
                        "target": target,
                        "amount": amount,
                    }
                )

        if rate_result.get("status") == "ok":
            response_text = rate_result.get("response_text") or "Rate fetched."
            comment_text = ""
            try:
                language = _detect_language(prompt)
                comment_system = (
                    "Ты — AVA, саркастичная аниме-девушка с острым языком. "
                    "Дай короткий комментарий (1–2 предложения) про курс валют, "
                    "без упоминания инструментов и без повторения чисел."
                )
                comment_user = (
                    f"Сделай комментарий про курс валют на русском.\n\n{response_text}"
                    if language == "ru"
                    else f"Make a short currency rate comment in English.\n\n{response_text}"
                )
                comment_response = client.chat_completion(
                    messages=[
                        {"role": "system", "content": comment_system},
                        {"role": "user", "content": comment_user},
                    ],
                    model=selected_model,
                    temperature=0.7,
                    max_tokens=80,
                    stream=False,
                    tools=None,
                    tool_choice=None,
                )
                comment_text = comment_response["choices"][0]["message"]["content"].strip()
            except Exception:
                comment_text = ""
            if comment_text:
                response_text = f"{response_text}\n\n_AVA:_ {comment_text}"
        else:
            response_text = f"Rate error: {rate_result.get('message', 'Unknown error')}"

        chat_manager.add_message("assistant", response_text)
        with st.chat_message("assistant"):
            st.markdown(response_text)
        return

    if is_wiki_command or is_wiki_auto:
        with st.chat_message("user"):
            st.write(prompt)
        if is_wiki_command:
            query = prompt[len("/wiki"):].strip()
        else:
            query = prompt.strip()
        if not query:
            wiki_result = {"status": "error", "message": "Query is required."}
        elif not plugin_registry or not plugin_registry.get("wikimedia_plugin"):
            wiki_result = {"status": "error", "message": "Wikimedia plugin is not available."}
        else:
            plugin_info = plugin_registry.get("wikimedia_plugin")
            if hasattr(plugin_info, "enabled") and not plugin_info.enabled:
                wiki_result = {"status": "error", "message": "Wikimedia plugin is not available."}
            else:
                wiki_result = plugin_info.instance.run(
                    {
                        "query": query,
                        "language": _detect_language(query),
                    }
                )

        page_url = None
        if wiki_result.get("status") == "ok":
            title = wiki_result.get("title") or "Unknown title"
            excerpt = wiki_result.get("excerpt") or ""
            description = wiki_result.get("description") or ""
            extract = wiki_result.get("extract") or ""
            page_url = wiki_result.get("page_url")

            base_text = f"**{title}**"
            blend_text = ""
            try:
                language = _detect_language(query)
                comment_system = (
                    "Ты — ассистентка AVA, саркастичная аниме-девушка с острым языком. "
                    "Обращайся к пользователю как senpai. "
                    "Перефразируй своими словами в 1-2 предложениях, "
                    "смешай описание и отрывок, не копируй фразы дословно "
                    "и не повторяй заголовок. Не упоминай инструменты."
                )
                comment_user = (
                    "\u041f\u0435\u0440\u0435\u0444\u0440\u0430\u0437\u0438\u0440\u0443\u0439 \u0441\u0432\u043e\u0438\u043c\u0438 \u0441\u043b\u043e\u0432\u0430\u043c\u0438 \u0432 1-2 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u044f\u0445, \u0441\u043c\u0435\u0448\u0430\u0439 \u043e\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u0438 \u043e\u0442\u0440\u044b\u0432\u043e\u043a, \u043d\u0435 \u043a\u043e\u043f\u0438\u0440\u0443\u0439 \u0444\u0440\u0430\u0437\u044b \u0434\u043e\u0441\u043b\u043e\u0432\u043d\u043e \u0438 \u043d\u0435 \u043f\u043e\u0432\u0442\u043e\u0440\u044f\u0439 \u0437\u0430\u0433\u043e\u043b\u043e\u0432\u043e\u043a.\n\n"
                    f"Title: {title}\n\nDescription: {description}\n\nExcerpt: {excerpt}\n\nExtract: {extract}"
                    if language == "ru"
                    else (
                        "Paraphrase in 1-2 sentences, blend description and excerpt, "
                        "avoid copying phrases, and do not repeat the title.\n\n"
                        f"Title: {title}\n\nDescription: {description}\n\nExcerpt: {excerpt}\n\nExtract: {extract}"
                    )
                )
                comment_response = client.chat_completion(
                    messages=[
                        {"role": "system", "content": comment_system},
                        {"role": "user", "content": comment_user},
                    ],
                    model=selected_model,
                    temperature=0.8,
                    max_tokens=120,
                    stream=False,
                    tools=None,
                    tool_choice=None,
                )
                blend_text = comment_response["choices"][0]["message"]["content"].strip()
            except Exception:
                blend_text = ""

            if not blend_text:
                combined = " ".join([part for part in (description, excerpt) if part])
                blend_text = combined or extract or "No summary available."

            response_text = f"{base_text} — {blend_text}"
        else:
            response_text = f"Wiki error: {wiki_result.get('message', 'Unknown error')}"

        chat_manager.add_message("assistant", response_text)
        with st.chat_message("assistant"):
            st.markdown(response_text)
            if page_url:
                st.link_button("Ссылка", page_url)
        return

    if is_weather_query:
        with st.chat_message("user"):
            st.write(prompt)
        language = _detect_language(prompt)
        if prompt_lower.startswith("/weather"):
            location = prompt[len("/weather"):].strip() or "New York"
        else:
            location = _extract_location(prompt) or "New York"
        if not plugin_registry or not plugin_registry.get("weather_plugin"):
            weather_result = {"status": "error", "message": "Weather plugin is not available."}
        else:
            plugin = plugin_registry.get("weather_plugin")
            weather_result = plugin.instance.run({"location": location, "language": language})

        if weather_result.get("status") == "ok":
            response_text = weather_result.get("response_text")
            if not response_text:
                loc = weather_result.get("location", location)
                temp = weather_result.get("temperature_c")
                wind = weather_result.get("windspeed_kph")
                code = weather_result.get("weathercode")
                condition = weather_result.get("condition", "Unknown")
                temp_display = f"{temp} C" if temp is not None else "N/A"
                wind_display = f"{wind} km/h" if wind is not None else "N/A"
                code_display = code if code is not None else "N/A"
                response_text = (
                    f"Weather for **{loc}**\n\n"
                    f"- Temperature: **{temp_display}**\n"
                    f"- Wind: **{wind_display}**\n"
                    f"- Condition: **{condition}**\n"
                    f"- Code: `{code_display}`"
                )
            comment_text = ""
            try:
                comment_system = (
                    "You are AVA, a sarcastic anime assistant. "
                    "Give a short 1-2 sentence comment about the weather. "
                    "Do not mention tools and do not repeat numbers."
                )
                comment_user = (
                    "\u0421\u0434\u0435\u043b\u0430\u0439 \u043a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u0439 \u043f\u043e \u043f\u043e\u0433\u043e\u0434\u0435 \u043d\u0430 \u0440\u0443\u0441\u0441\u043a\u043e\u043c.\n\n{response_text}"
                    if language == "ru"
                    else f"Make a short weather comment in English.\n\n{response_text}"
                )
                comment_response = client.chat_completion(
                    messages=[
                        {"role": "system", "content": comment_system},
                        {"role": "user", "content": comment_user},
                    ],
                    model=selected_model,
                    temperature=0.7,
                    max_tokens=80,
                    stream=False,
                    tools=None,
                    tool_choice=None,
                )
                comment_text = comment_response["choices"][0]["message"]["content"].strip()
            except Exception:
                comment_text = ""
            if comment_text:
                response_text = f"{response_text}\n\n_AVA:_ {comment_text}"
        else:
            response_text = f"Weather error: {weather_result.get('message', 'Unknown error')}"

        chat_manager.add_message("assistant", response_text)
        with st.chat_message("assistant"):
            st.markdown(response_text)
        return

    _log_debug(
        "send_prompt",
        {
            "prompt_len": len(prompt),
            "selected_model": selected_model,
        },
    )

    content_parts, attachments = build_content_parts(prompt, uploaded_files or [])
    content = content_parts if attachments else prompt
    chat_manager.add_message("user", content, metadata={"attachments": attachments})

    recent_prompts = st.session_state.get("recent_prompts", [])
    if prompt not in recent_prompts:
        st.session_state["recent_prompts"] = ([prompt] + recent_prompts)[:10]

    with st.chat_message("user"):
        st.write(prompt)
        if attachments:
            included = [a for a in attachments if a.get("included")]
            skipped = [a for a in attachments if not a.get("included")]
            if included:
                st.caption(f"Attachments included: {', '.join(a['name'] for a in included)}")
            if skipped:
                st.caption(f"Attachments skipped: {', '.join(a['name'] for a in skipped)}")

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        start_time = time.time()
        status = "ok"
        error_text = ""
        prompt_tokens = None
        completion_tokens = None
        total_tokens = None

        def _chat_completion_request(tools_payload, tool_choice_payload):
            try:
                if use_async:
                    return run_async(
                        client.chat_completion_async(
                            messages=messages_for_api,
                            model=selected_model,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            tools=tools_payload,
                            tool_choice=tool_choice_payload,
                        )
                    ), False
                return client.chat_completion(
                    messages=messages_for_api,
                    model=selected_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=False,
                    tools=tools_payload,
                    tool_choice=tool_choice_payload,
                ), False
            except Exception as exc:
                message = str(exc)
                if tools_payload and ("tool_choice" in message or "tools" in message):
                    if selected_model not in tools_unsupported_models:
                        tools_unsupported_models.append(selected_model)
                    st.info("Without tools for this request.")
                    if use_async:
                        return run_async(
                            client.chat_completion_async(
                                messages=messages_for_api,
                                model=selected_model,
                                temperature=temperature,
                                max_tokens=max_tokens,
                                tools=None,
                                tool_choice=None,
                            )
                        ), True
                    return client.chat_completion(
                        messages=messages_for_api,
                        model=selected_model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=False,
                        tools=None,
                        tool_choice=None,
                    ), True
                raise

        try:
            messages_for_api = chat_manager.get_formatted_messages()
            prompt_tokens = estimate_tokens_for_messages(messages_for_api)
            if enable_tools and use_streaming and is_weather_query:
                use_streaming = False

            if use_streaming:
                for chunk in client.stream_completion(
                    {
                        "model": selected_model,
                        "messages": messages_for_api,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "stream": True,
                    }
                ):
                    full_response += chunk
                    message_placeholder.markdown(full_response + "\u258c")

                message_placeholder.markdown(full_response)
            else:
                with st.spinner("AVA is thinking..."):
                    tools = None
                    tool_choice = None
                    tools_disabled = False
                    if enable_tools and selected_model in tools_unsupported_models:
                        st.info("Without tools for this request.")
                        tools_disabled = True
                    elif enable_tools:
                        tools = get_tools(plugin_registry)
                        tool_choice = None
                    response, tools_disabled_retry = _chat_completion_request(
                        tools,
                        tool_choice,
                    )
                    tools_disabled = tools_disabled or tools_disabled_retry

                    assistant_message = response["choices"][0]["message"]
                    tool_calls = [] if tools_disabled else assistant_message.get("tool_calls", [])
                    if tool_calls:
                        chat_manager.add_message(
                            "assistant",
                            assistant_message.get("content", ""),
                            metadata={"hidden": True},
                            api_fields={"tool_calls": tool_calls},
                        )
                        for tool_call in tool_calls:
                            tool_message = tool_call_to_message(
                                tool_call,
                                plugin_registry=plugin_registry,
                            )
                            chat_manager.add_message(
                                "tool",
                                tool_message["content"],
                                metadata={"hidden": True},
                                api_fields={
                                    "tool_call_id": tool_message["tool_call_id"],
                                    "name": tool_message["name"],
                                },
                            )
                        messages_for_api = chat_manager.get_formatted_messages()
                        response, _ = _chat_completion_request(None, None)

                    full_response = response["choices"][0]["message"]["content"]
                    message_placeholder.write(full_response)

                    if "usage" in response:
                        tokens = response["usage"]
                        prompt_tokens = tokens.get("prompt_tokens", 0)
                        completion_tokens = tokens.get("completion_tokens", 0)
                        total_tokens = tokens.get("total_tokens", 0)
                        st.caption(
                            f"Tokens: {tokens.get('total_tokens', 0)} "
                            f"(Prompt: {tokens.get('prompt_tokens', 0)}, "
                            f"Completion: {tokens.get('completion_tokens', 0)})"
                        )

            chat_manager.add_message("assistant", full_response)

        except Exception as e:
            status = "error"
            error_text = _sanitize_error(str(e), api_key)
            st.error(f"Error: {error_text}")
            if "402" in error_text:
                st.info(
                    "Payment Required from OpenRouter. This usually means the selected model "
                    "is not free or your account has no credits. Try a free model or add credits."
                )
            if "404" in error_text:
                st.info(
                    "OpenRouter returned 404. This often means the selected model is unavailable "
                    "or not permitted for your account. Check the model in Settings."
                )
            logger.error("Chat error: %s", error_text, exc_info=True)
        finally:
            if completion_tokens is None:
                completion_tokens = estimate_tokens_from_text(full_response)
            if total_tokens is None:
                total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)
            cost_usd = calculate_cost_usd(total_tokens or 0, price_per_1k)
            latency_ms = int((time.time() - start_time) * 1000)
            log_request(
                config.monitoring_db_path,
                model=selected_model,
                temperature=temperature,
                max_tokens=max_tokens,
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
                price_per_1k=price_per_1k,
                status=status,
                error=error_text,
            )

