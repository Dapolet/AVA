import asyncio
import base64
import json
import threading
from typing import Any, Dict, List, Tuple


def run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    if loop.is_running():
        result = {"value": None, "error": None}

        def _runner():
            try:
                result["value"] = asyncio.run(coro)
            except Exception as exc:
                result["error"] = exc

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()
        if result["error"] is not None:
            raise result["error"]
        return result["value"]
    return loop.run_until_complete(coro)


def estimate_tokens_from_text(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_tokens_for_messages(messages: List[Dict[str, Any]]) -> int:
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens_from_text(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += estimate_tokens_from_text(part.get("text", ""))
    return total


def calculate_cost_usd(total_tokens: int, price_per_1k: float) -> float:
    if total_tokens <= 0 or price_per_1k <= 0:
        return 0.0
    return round((total_tokens / 1000.0) * price_per_1k, 6)


def safe_json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=True, indent=2)


def strip_image_data_from_messages(messages: List[Dict[str, Any]], max_bytes: int = 200_000) -> List[Dict[str, Any]]:
    stripped = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            new_content = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    url = part.get("image_url", {}).get("url", "")
                    if isinstance(url, str) and url.startswith("data:") and len(url) > max_bytes:
                        new_content.append({
                            "type": "image_url",
                            "image_url": {"url": "[omitted]"}
                        })
                    else:
                        new_content.append(part)
                else:
                    new_content.append(part)
            new_msg = dict(msg)
            new_msg["content"] = new_content
            stripped.append(new_msg)
        else:
            stripped.append(dict(msg))
    return stripped


def message_to_plain_text(message: Dict[str, Any]) -> str:
    role = message.get("role", "unknown")
    content = message_content_only(message)
    return f"{role}: {content}"


def message_content_only(message: Dict[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    parts.append(part.get("text", ""))
                elif part.get("type") == "image_url":
                    parts.append("[image]")
        return " ".join(parts).strip()
    return "[unsupported content]"


def build_content_parts(
    prompt: str,
    files: List[Any],
    max_text_bytes: int = 200_000,
    max_total_bytes: int = 2_000_000,
    max_image_bytes: int = 1_000_000,
    max_files: int = 6,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    parts: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
    attachments: List[Dict[str, Any]] = []
    total_bytes = 0
    for idx, uploaded in enumerate(files or []):
        try:
            content_type = getattr(uploaded, "type", "")
            data = uploaded.getvalue()
            name = getattr(uploaded, "name", "file")
            size = len(data)
            if max_files is not None and idx >= max_files:
                attachments.append({"name": name, "type": content_type, "size": size, "included": False, "reason": "too_many_files"})
                continue
            if max_total_bytes is not None and (total_bytes + size) > max_total_bytes:
                attachments.append({"name": name, "type": content_type, "size": size, "included": False, "reason": "total_size_limit"})
                continue
            if content_type.startswith("image/"):
                if max_image_bytes is not None and size > max_image_bytes:
                    attachments.append({"name": name, "type": content_type, "size": size, "included": False, "reason": "image_size_limit"})
                    continue
                b64 = base64.b64encode(data).decode("ascii")
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{content_type};base64,{b64}"}
                })
                attachments.append({"name": name, "type": content_type, "size": size, "included": True})
                total_bytes += size
            elif content_type in ("text/plain", "text/markdown", "application/json", "text/csv") or name.endswith((".txt", ".md", ".json", ".csv")):
                if size <= max_text_bytes:
                    text = data.decode("utf-8", errors="ignore")
                    parts.append({"type": "text", "text": f"\n\n[File: {name}]\n{text}"})
                    attachments.append({"name": name, "type": content_type, "size": size, "included": True})
                    total_bytes += size
                else:
                    attachments.append({"name": name, "type": content_type, "size": size, "included": False, "reason": "text_size_limit"})
            else:
                attachments.append({"name": name, "type": content_type, "size": size, "included": False, "reason": "unsupported_type"})
        except Exception:
            attachments.append({"name": "unknown", "type": "unknown", "size": 0, "included": False, "reason": "error"})
    return parts, attachments
