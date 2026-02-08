import html
import os
import re
import time
from urllib.parse import quote

import requests
from requests import HTTPError

from avaai.plugins.base import BasePlugin


class Plugin(BasePlugin):
    id = "wikimedia_plugin"
    name = "Wikimedia Plugin"
    version = "0.1.0"

    _CODE_RE = re.compile(r"[\u0410-\u042f\u0430-\u044f\u0401\u0451]")
    _MIN_INTERVAL_SEC = 1.0
    _MAX_RETRIES = 3
    _BASE_BACKOFF_SEC = 0.5
    _MAX_BACKOFF_SEC = 4.0
    _last_request_ts = 0.0

    def _detect_language(self, text: str, language: str | None = None) -> str:
        if language in ("en", "ru"):
            return language
        return "ru" if self._CODE_RE.search(text or "") else "en"

    def _user_agent(self) -> str:
        return os.getenv("WIKIMEDIA_USER_AGENT") or "AVA/0.1 (contact: you@example.com)"

    def _strip_html(self, value: str | None) -> str:
        if not value:
            return ""
        text = re.sub(r"<[^>]+>", "", value)
        return html.unescape(text).strip()

    def _throttle(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_ts
        if elapsed < self._MIN_INTERVAL_SEC:
            time.sleep(self._MIN_INTERVAL_SEC - elapsed)
        self._last_request_ts = time.monotonic()

    def _retry_sleep(self, attempt: int, retry_after: str | None) -> None:
        if retry_after and retry_after.isdigit():
            time.sleep(min(int(retry_after), self._MAX_BACKOFF_SEC))
            return
        backoff = min(self._BASE_BACKOFF_SEC * (2 ** attempt), self._MAX_BACKOFF_SEC)
        time.sleep(backoff)

    def _request_json(self, url: str, params: dict | None = None) -> dict:
        headers = {"User-Agent": self._user_agent(), "Accept": "application/json"}
        last_exc = None
        for attempt in range(self._MAX_RETRIES):
            self._throttle()
            try:
                response = requests.get(url, params=params, headers=headers, timeout=10)
                if response.status_code == 429:
                    self._retry_sleep(attempt, response.headers.get("Retry-After"))
                    continue
                response.raise_for_status()
                return response.json()
            except HTTPError as exc:
                last_exc = exc
                status = exc.response.status_code if exc.response is not None else None
                if status in (429, 500, 502, 503, 504) and attempt < self._MAX_RETRIES - 1:
                    retry_after = exc.response.headers.get("Retry-After") if exc.response else None
                    self._retry_sleep(attempt, retry_after)
                    continue
                raise
        if last_exc:
            raise last_exc
        raise RuntimeError("Wikimedia request failed.")

    def _search_page(self, query: str, language: str) -> dict | None:
        url = f"https://{language}.wikipedia.org/w/rest.php/v1/search/page"
        data = self._request_json(url, params={"q": query, "limit": 1})
        pages = data.get("pages") or []
        return pages[0] if pages else None

    def _summary(self, title: str, language: str) -> dict:
        encoded_title = quote(title, safe="")
        url = f"https://{language}.wikipedia.org/api/rest_v1/page/summary/{encoded_title}"
        return self._request_json(url)

    def run(self, context) -> dict:
        context = context or {}
        query = (context.get("query") or "").strip()
        if not query:
            return {"status": "error", "message": "Query is required."}

        try:
            language = self._detect_language(query, context.get("language"))
            search_hit = self._search_page(query, language)
            if not search_hit:
                return {"status": "error", "message": "No results."}

            title = search_hit.get("title") or ""
            excerpt = self._strip_html(search_hit.get("excerpt"))
            description = self._strip_html(search_hit.get("description"))

            summary = self._summary(title, language)
            extract = self._strip_html(summary.get("extract"))
            if not description:
                description = self._strip_html(summary.get("description"))

            page_url = None
            content_urls = summary.get("content_urls") or {}
            desktop = content_urls.get("desktop") or {}
            page_url = desktop.get("page") or None

            response_text = title
            return {
                "status": "ok",
                "query": query,
                "language": language,
                "title": title,
                "excerpt": excerpt,
                "description": description,
                "extract": extract,
                "page_url": page_url,
                "response_text": response_text,
            }
        except HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 429:
                return {
                    "status": "error",
                    "message": "Wikimedia rate limit reached. Please wait a few seconds and try again.",
                }
            return {"status": "error", "message": str(exc)}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

