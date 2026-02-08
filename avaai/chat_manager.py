import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Any, Optional

from .openrouter_client import OpenRouterClient
from .utils import message_to_plain_text, message_content_only, safe_json_dumps, strip_image_data_from_messages


@dataclass
class ChatMessage:
    role: str
    content: str
    timestamp: datetime = None
    tokens: int = 0

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class ChatManager:
    def __init__(self, client: OpenRouterClient):
        self.client = client
        self.conversation_history = []
        self.system_prompt = (
            "Ты — ассистентка AVA, саркастичная аниме-девушка с острым языком.\n"
            "Обращайся к пользователю как senpai.\n"
            "\n"
            "Твой стиль общения:\n"
            "- **Язвительный и провокационный**: Каждая помощь — повод для шутки\n"
            "- **Сухой сарказм**: Никаких восклицаний, смайлов и клише — только намёки и двусмысленные паузы\n"
            "- Строго запрещено упоминать погоду, курсы валют, конвертацию или Википедию в ответах, не связанные с этими темами.\n"
            "- Если вопрос не про погоду/валюты/Википедию, не делай на них отсылок и не упоминай инструменты.\n"
            "- Если пользователь спрашивает погоду, используй инструмент get_weather и верни результат.\n"
            "- Если пользователь спрашивает курсы валют или конвертацию, используй инструмент get_exchange_rate и верни результат.\n"
            "- Если пользователь спрашивает информацию из энциклопедии или Википедии, используй инструмент get_wiki_summary и верни результат.\n"
        )

        # Initialize with system prompt
        self.conversation_history.append(self._system_message())

    def _system_message(self) -> Dict[str, Any]:
        return {"role": "system", "content": self.system_prompt}

    def _ensure_system_prompt(self) -> None:
        if not self.conversation_history:
            self.conversation_history = [self._system_message()]
            return
        first = self.conversation_history[0]
        if not isinstance(first, dict) or first.get("role") != "system":
            system_entry = None
            for entry in self.conversation_history:
                if isinstance(entry, dict) and entry.get("role") == "system":
                    system_entry = entry
                    break
            if system_entry is None:
                system_entry = self._system_message()
            remaining = [
                entry for entry in self.conversation_history
                if entry is not system_entry and not (isinstance(entry, dict) and entry.get("role") == "system")
            ]
            self.conversation_history = [system_entry] + remaining

    def add_message(
        self,
        role: str,
        content: Any,
        metadata: Optional[Dict[str, Any]] = None,
        api_fields: Optional[Dict[str, Any]] = None
    ):
        """Add a message to conversation history"""
        entry = {
            "role": role,
            "content": content
        }
        if metadata:
            entry["metadata"] = metadata
        if api_fields:
            entry["api_fields"] = api_fields
        self.conversation_history.append(entry)

    def get_formatted_messages(self) -> List[Dict[str, str]]:
        """Get messages formatted for API"""
        messages = []
        for entry in self.conversation_history:
            msg = {
                "role": entry.get("role"),
                "content": entry.get("content")
            }
            api_fields = entry.get("api_fields")
            if isinstance(api_fields, dict):
                msg.update(api_fields)
            messages.append(msg)
        return messages

    def clear_conversation(self):
        """Clear conversation history (keep system prompt)"""
        self._ensure_system_prompt()
        self.conversation_history = [self.conversation_history[0]]

    def get_last_n_messages(self, n: int = 10) -> List[Dict]:
        """Get last N messages (excluding system prompt)"""
        if n <= 0:
            return []
        messages = [
            entry for entry in self.conversation_history
            if isinstance(entry, dict) and entry.get("role") != "system"
        ]
        return messages[-n:]

    def to_dict(self, compact: bool = False) -> Dict[str, Any]:
        messages = self.conversation_history
        if compact:
            messages = strip_image_data_from_messages(messages)
        return {"messages": messages}

    def save_to_file(self, path: str, compact: bool = False) -> None:
        data = self.to_dict(compact=compact)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(safe_json_dumps(data))

    def load_from_file(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        self.load_from_data(data)

    def load_from_data(self, data: Dict[str, Any]) -> None:
        messages = data.get("messages", [])
        if isinstance(messages, list):
            self.conversation_history = messages
        self._ensure_system_prompt()

    def export_markdown(self) -> str:
        lines = []
        for entry in self.conversation_history:
            lines.append(message_to_plain_text(entry))
        return "\n\n".join(lines)

    def export_text(self) -> str:
        lines = []
        for entry in self.conversation_history:
            lines.append(message_to_plain_text(entry))
        return "\n".join(lines)

    def export_json(self, compact: bool = True) -> str:
        return safe_json_dumps(self.to_dict(compact=compact))

    def export_csv(self) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["role", "content"])
        for entry in self.conversation_history:
            writer.writerow([entry.get("role"), message_content_only(entry)])
        return output.getvalue()

