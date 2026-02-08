import logging
import os
import re

import requests

from avaai.plugins.base import BasePlugin

try:
    import streamlit as st
except Exception:
    st = None


class Plugin(BasePlugin):
    id = "exchangerate_plugin"
    name = "Exchange Rate Plugin"
    version = "0.1.0"

    _BASE_URL = "https://v6.exchangerate-api.com/v6"
    _CODE_RE = re.compile(r"^[A-Z]{3}$")
    _MAJOR = ["USD", "EUR", "GBP", "JPY", "CNY", "CHF", "CAD", "AUD", "RUB"]
    _GENERIC_ERROR = "Exchange rate request failed. Please try again later."

    def __init__(self):
        self._logger = logging.getLogger(__name__)

    def _get_api_key(self) -> str:
        if st is not None:
            try:
                if hasattr(st, "secrets") and "EXCHANGERATE_API_KEY" in st.secrets:
                    return st.secrets.get("EXCHANGERATE_API_KEY", "")
                if hasattr(st, "secrets") and "EXCHANGE_RATE_API_KEY" in st.secrets:
                    return st.secrets.get("EXCHANGE_RATE_API_KEY", "")
            except Exception:
                pass
        return (
            os.getenv("EXCHANGERATE_API_KEY")
            or os.getenv("EXCHANGE_RATE_API_KEY")
            or ""
        )

    def _normalize_code(self, value: str | None) -> str | None:
        if not value:
            return None
        code = value.strip().upper()
        if not self._CODE_RE.match(code):
            return None
        return code

    def _fmt_rate(self, value: float | None) -> str:
        if value is None:
            return "N/A"
        text = f"{value:.4f}".rstrip("0").rstrip(".")
        return text or "0"

    def _fmt_amount(self, value: float | None) -> str:
        if value is None:
            return "N/A"
        text = f"{value:.2f}".rstrip("0").rstrip(".")
        return text or "0"

    def _api_error(self, error_type: str | None) -> str:
        return f"ExchangeRate-API error: {error_type or 'unknown-error'}"

    def _request_json(self, url: str) -> dict:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("result") == "error":
            raise RuntimeError(self._api_error(data.get("error-type")))
        return data

    def _safe_error(self, exc: Exception, api_key: str) -> str:
        text = str(exc)
        if api_key:
            text = text.replace(api_key, "[redacted]")
        self._logger.error("Exchange rate plugin error: %s", text)
        if isinstance(exc, requests.RequestException):
            return self._GENERIC_ERROR
        return text or self._GENERIC_ERROR

    def _build_pair_url(self, api_key: str, base: str, target: str, amount: float | None) -> str:
        if amount is None:
            return f"{self._BASE_URL}/{api_key}/pair/{base}/{target}"
        return f"{self._BASE_URL}/{api_key}/pair/{base}/{target}/{amount}"

    def _build_latest_url(self, api_key: str, base: str) -> str:
        return f"{self._BASE_URL}/{api_key}/latest/{base}"

    def run(self, context) -> dict:
        context = context or {}
        api_key = ""
        try:
            api_key = self._get_api_key()
            if not api_key:
                return {"status": "error", "message": "EXCHANGERATE_API_KEY is not configured."}

            base = context.get("base") or "USD"
            target = context.get("target")
            amount = context.get("amount")

            base_code = self._normalize_code(base)
            if not base_code:
                return {"status": "error", "message": f"Invalid base currency: {base}"}

            target_code = None
            if target:
                target_code = self._normalize_code(target)
                if not target_code:
                    return {"status": "error", "message": f"Invalid target currency: {target}"}

            amount_value = None
            if target_code is not None:
                if amount is None:
                    amount_value = 1.0
                else:
                    try:
                        amount_value = float(amount)
                    except (TypeError, ValueError):
                        return {"status": "error", "message": f"Invalid amount: {amount}"}

            if target_code:
                url = self._build_pair_url(api_key, base_code, target_code, amount_value if amount is not None else None)
                data = self._request_json(url)
                conversion_rate = data.get("conversion_rate")
                conversion_result = data.get("conversion_result")
                if conversion_result is None and conversion_rate is not None and amount_value is not None:
                    conversion_result = conversion_rate * amount_value

                time_last_update_utc = data.get("time_last_update_utc")
                time_next_update_utc = data.get("time_next_update_utc")

                response_text = (
                    f"{self._fmt_amount(amount_value)} {base_code} = "
                    f"{self._fmt_amount(conversion_result)} {target_code}"
                )
                if time_last_update_utc:
                    response_text = f"{response_text}\nLast updated: {time_last_update_utc}"

                return {
                    "status": "ok",
                    "base": base_code,
                    "target": target_code,
                    "amount": amount_value,
                    "conversion_rate": conversion_rate,
                    "conversion_result": conversion_result,
                    "time_last_update_utc": time_last_update_utc,
                    "time_next_update_utc": time_next_update_utc,
                    "response_text": response_text,
                }

            url = self._build_latest_url(api_key, base_code)
            data = self._request_json(url)
            rates = data.get("conversion_rates") or {}
            time_last_update_utc = data.get("time_last_update_utc")
            time_next_update_utc = data.get("time_next_update_utc")

            summary = {}
            for code in self._MAJOR:
                if code == base_code:
                    continue
                if code in rates:
                    summary[code] = rates[code]

            if not summary:
                return {"status": "error", "message": f"No rates available for base {base_code}."}

            summary_items = [f"{code} {self._fmt_rate(value)}" for code, value in summary.items()]
            response_text = f"Rates for {base_code}: {', '.join(summary_items)}"
            if time_last_update_utc:
                response_text = f"{response_text}\nLast updated: {time_last_update_utc}"

            return {
                "status": "ok",
                "base": base_code,
                "rates": summary,
                "time_last_update_utc": time_last_update_utc,
                "time_next_update_utc": time_next_update_utc,
                "response_text": response_text,
            }
        except Exception as exc:
            return {"status": "error", "message": self._safe_error(exc, api_key)}

