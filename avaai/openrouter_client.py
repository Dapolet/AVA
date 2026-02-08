import asyncio
import json
import time
from typing import Optional, List, Dict, Generator

import requests

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OpenRouterClient:
    def __init__(self, api_key: str, base_url: str = "https://openrouter.ai/api/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "localhost:8000",
            "X-Title": "AVA - Sarcastic Anime Assistant"
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.max_retries = 3
        self.retry_backoff = 1.5

    def set_api_key(self, api_key: str) -> None:
        self.api_key = api_key
        self.headers["Authorization"] = f"Bearer {self.api_key}"
        self.session.headers.update(self.headers)

    def _log_error(self, message: str, exc: Exception) -> None:
        text = str(exc)
        if self.api_key:
            text = text.replace(self.api_key, "[redacted]")
        logger.error("%s: %s", message, text)
        if hasattr(exc, "response") and exc.response is not None:
            logger.error("Status code: %s", exc.response.status_code)

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        last_exc = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.request(method, url, **kwargs)
                if response.status_code >= 400:
                    detail = None
                    try:
                        data = response.json()
                        if isinstance(data, dict):
                            detail = (
                                data.get("error", {}).get("message")
                                or data.get("message")
                                or data.get("detail")
                            )
                    except Exception:
                        detail = response.text.strip() if response.text else None
                    message = f"{response.status_code} Client Error"
                    if detail:
                        message = f"{message}: {detail}"
                    raise requests.HTTPError(message, response=response)
                return response
            except requests.exceptions.RequestException as exc:
                last_exc = exc
                status = getattr(exc.response, "status_code", None)
                should_retry = status in (429, 500, 502, 503, 504)
                if not should_retry or attempt == self.max_retries:
                    raise
                time.sleep(self.retry_backoff ** attempt)
        raise last_exc  # type: ignore[misc]

    def chat_completion(
            self,
            messages: List[Dict[str, str]],
            model: str = "gpt-3.5-turbo",
            temperature: float = 0.7,
            max_tokens: Optional[int] = None,
            stream: bool = False,
            tools: Optional[List[Dict]] = None,
            tool_choice: Optional[str] = None
    ) -> Dict:
        """
        Send chat completion request to OpenRouter
        """
        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": model,
            "messages": messages,
            "temperature": max(0.1, min(temperature, 2.0)),
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice

        if stream:
            payload["stream"] = True
            return self._stream_completion(url, payload)

        try:
            response = self._request("POST", url, json=payload, timeout=30)
            return response.json()
        except requests.exceptions.RequestException as e:
            self._log_error("Request failed", e)
            raise

    async def chat_completion_async(
            self,
            messages: List[Dict[str, str]],
            model: str = "gpt-3.5-turbo",
            temperature: float = 0.7,
            max_tokens: Optional[int] = None,
            tools: Optional[List[Dict]] = None,
            tool_choice: Optional[str] = None
    ) -> Dict:
        return await asyncio.to_thread(
            self.chat_completion,
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            tools=tools,
            tool_choice=tool_choice
        )

    def stream_completion(self, payload: Dict) -> Generator[str, None, None]:
        url = f"{self.base_url}/chat/completions"
        return self._stream_completion(url, payload)

    def _stream_completion(self, url: str, payload: dict) -> Generator[str, None, None]:
        """
        Handle streaming responses
        """
        try:
            response = self._request(
                "POST",
                url,
                json=payload,
                timeout=60,
                stream=True
            )
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data = line_str[6:]
                        if data != '[DONE]':
                            try:
                                chunk = json.loads(data)
                                if 'choices' in chunk and chunk['choices']:
                                    delta = chunk['choices'][0].get('delta', {})
                                    if 'content' in delta:
                                        yield delta['content']
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            self._log_error("Streaming error", e)
            yield f"\n[Error: {str(e)}]"

    def get_models(self) -> List[Dict]:
        """Get available models from OpenRouter"""
        url = f"{self.base_url}/models"

        try:
            response = self._request("GET", url, timeout=10)
            models = response.json().get('data', [])
            return sorted(models, key=lambda x: x.get('id', '').lower())
        except requests.exceptions.RequestException as e:
            self._log_error("Failed to fetch models", e)
            return []

    def get_model_info(self, model_id: str) -> Optional[Dict]:
        """Get specific model information"""
        models = self.get_models()
        for model in models:
            if model.get('id') == model_id:
                return model
        return None

    def validate_api_key(self) -> bool:
        url = f"{self.base_url}/models"
        try:
            response = self._request("GET", url, timeout=10)
            return response.status_code == 200
        except requests.exceptions.RequestException as e:
            self._log_error("API key validation failed", e)
            return False

    async def validate_api_key_async(self) -> bool:
        return await asyncio.to_thread(self.validate_api_key)
