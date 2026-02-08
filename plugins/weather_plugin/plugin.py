import re
import requests

from avaai.plugins.base import BasePlugin


class Plugin(BasePlugin):
    id = "weather_plugin"
    name = "Weather Plugin"
    version = "0.1.0"

    _CODE_MAP = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        56: "Light freezing drizzle",
        57: "Dense freezing drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        66: "Light freezing rain",
        67: "Heavy freezing rain",
        71: "Slight snow fall",
        73: "Moderate snow fall",
        75: "Heavy snow fall",
        77: "Snow grains",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }
    _CODE_MAP_RU = {
        0: "Ясно",
        1: "В основном ясно",
        2: "Переменная облачность",
        3: "Облачно",
        45: "Туман",
        48: "Инейный туман",
        51: "Слабая морось",
        53: "Умеренная морось",
        55: "Сильная морось",
        56: "Слабая ледяная морось",
        57: "Сильная ледяная морось",
        61: "Слабый дождь",
        63: "Умеренный дождь",
        65: "Сильный дождь",
        66: "Слабый ледяной дождь",
        67: "Сильный ледяной дождь",
        71: "Слабый снег",
        73: "Умеренный снег",
        75: "Сильный снег",
        77: "Снежные зерна",
        80: "Слабые ливни",
        81: "Умеренные ливни",
        82: "Сильные ливни",
        85: "Слабые снегопады",
        86: "Сильные снегопады",
        95: "Гроза",
        96: "Гроза с небольшим градом",
        99: "Гроза с сильным градом",
    }
    _CODE_EMOJI = {
        0: "☀️",
        1: "🌤️",
        2: "⛅",
        3: "☁️",
        45: "🌫️",
        48: "🌫️",
        51: "🌦️",
        53: "🌦️",
        55: "🌧️",
        56: "🌧️",
        57: "🌧️",
        61: "🌧️",
        63: "🌧️",
        65: "🌧️",
        66: "🧊🌧️",
        67: "🧊🌧️",
        71: "🌨️",
        73: "🌨️",
        75: "🌨️",
        77: "🌨️",
        80: "🌦️",
        81: "🌦️",
        82: "🌧️",
        85: "🌨️",
        86: "🌨️",
        95: "⛈️",
        96: "⛈️🧊",
        99: "⛈️🧊",
    }

    def _is_cyrillic(self, text: str) -> bool:
        return bool(re.search(r"[А-Яа-яЁё]", text))

    def _is_moscow(self, text: str) -> bool:
        lowered = text.lower()
        return "москв" in lowered or "moscow" in lowered or "moskva" in lowered

    def _location_candidates(self, location: str) -> list[str]:
        location = location.strip()
        if not location:
            return []
        candidates = [location]
        lower = location.lower()
        if "москв" in lower:
            candidates.append("Москва")
        if self._is_cyrillic(location):
            if lower.endswith("е") and len(location) > 1:
                candidates.append(location[:-1] + "а")
                candidates.append(location[:-1] + "я")
            if lower.endswith("и") and len(location) > 1:
                candidates.append(location[:-1] + "ь")
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for item in candidates:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    def _detect_language(self, location: str, language: str | None) -> str:
        if language in ("ru", "en"):
            return language
        return "ru" if self._is_cyrillic(location) else "en"

    def _condition_text(self, code: int | None, language: str) -> str:
        if code is None:
            return "Unknown" if language == "en" else "Неизвестно"
        return (
            self._CODE_MAP_RU.get(code, "Неизвестно")
            if language == "ru"
            else self._CODE_MAP.get(code, "Unknown")
        )

    def _emoji(self, code: int | None) -> str:
        return self._CODE_EMOJI.get(code, "🌡️")

    def _pick_best_result(self, location: str, results: list[dict]) -> dict:
        if not results:
            return {}
        if self._is_moscow(location):
            ru_matches = [r for r in results if r.get("country_code") == "RU"]
            if ru_matches:
                return ru_matches[0]
            name_matches = [
                r for r in results
                if str(r.get("name", "")).lower() in ("moscow", "москва", "moskva")
            ]
            if name_matches:
                return name_matches[0]
        return results[0]

    def _geocode(self, candidate: str, country: str | None = None, language: str = "en") -> list[dict]:
        params = {
            "name": candidate,
            "count": 5,
            "language": language,
            "format": "json",
        }
        if country:
            params["country"] = country
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params=params,
            timeout=10
        )
        geo.raise_for_status()
        data = geo.json()
        return data.get("results") or []

    def run(self, context) -> dict:
        context = context or {}
        location = context.get("location", "New York")
        scope = context.get("scope", "multi_day")
        language = self._detect_language(location, context.get("language"))
        try:
            results = []
            last_candidate = location
            candidates = self._location_candidates(location) or [location]
            for candidate in candidates:
                last_candidate = candidate
                if self._is_moscow(candidate) or self._is_cyrillic(candidate):
                    results = self._geocode(candidate, country="RU", language="ru")
                if not results:
                    results = self._geocode(candidate, country=None, language="en")
                if results:
                    break
            if not results:
                return {"status": "error", "message": f"Location not found: {last_candidate}"}

            best = self._pick_best_result(last_candidate, results) or results[0]
            lat = best["latitude"]
            lon = best["longitude"]
            name = best.get("name", last_candidate)
            admin1 = best.get("admin1")
            country = best.get("country")

            weather = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "weathercode,temperature_2m_max,temperature_2m_min",
                    "forecast_days": 7,
                    "timezone": "auto",
                },
                timeout=10
            )
            weather.raise_for_status()
            forecast = weather.json()
            daily = forecast.get("daily", {})
            daily_units = forecast.get("daily_units", {})
            timezone = forecast.get("timezone")
            times = daily.get("time", [])
            tmax = daily.get("temperature_2m_max", [])
            tmin = daily.get("temperature_2m_min", [])
            codes = daily.get("weathercode", [])

            def _safe_get(items, idx):
                return items[idx] if idx < len(items) else None

            today_max = _safe_get(tmax, 0)
            today_min = _safe_get(tmin, 0)
            today_code = _safe_get(codes, 0)
            tomorrow_max = _safe_get(tmax, 1)
            tomorrow_min = _safe_get(tmin, 1)
            tomorrow_code = _safe_get(codes, 1)

            today_condition = self._condition_text(today_code, language)
            tomorrow_condition = self._condition_text(tomorrow_code, language)
            today_emoji = self._emoji(today_code)
            tomorrow_emoji = self._emoji(tomorrow_code)

            daily_entries = []
            for idx, date in enumerate(times):
                code = _safe_get(codes, idx)
                condition = self._condition_text(code, language)
                daily_entries.append({
                    "date": date,
                    "temperature_min_c": _safe_get(tmin, idx),
                    "temperature_max_c": _safe_get(tmax, idx),
                    "weathercode": code,
                    "emoji": self._emoji(code),
                    "condition": condition,
                })

            valid_pairs = [
                (mx, mn) for mx, mn in zip(tmax, tmin)
                if mx is not None and mn is not None
            ]
            if valid_pairs:
                daily_means = [(mx + mn) / 2.0 for mx, mn in valid_pairs]
                week_min = min(mn for _, mn in valid_pairs)
                week_max = max(mx for mx, _ in valid_pairs)
                week_avg = sum(daily_means) / len(daily_means)
            else:
                week_min = None
                week_max = None
                week_avg = None

            def _fmt_temp(value):
                return f"{value:.1f} C" if value is not None else "N/A"

            if language == "ru":
                response_text = (
                    f"Погода для **{name}**"
                    f"{f' ({admin1}, {country})' if admin1 or country else ''}\n\n"
                    f"- Сегодня: {today_emoji} **{_fmt_temp(today_min)}** до **{_fmt_temp(today_max)}**, {today_condition}\n"
                    f"- Завтра: {tomorrow_emoji} **{_fmt_temp(tomorrow_min)}** до **{_fmt_temp(tomorrow_max)}**, {tomorrow_condition}\n"
                    f"- Неделя: {_fmt_temp(week_min)} до {_fmt_temp(week_max)} (ср. {_fmt_temp(week_avg)})\n"
                    f"- Координаты: {lat:.3f}, {lon:.3f}\n"
                    f"- Часовой пояс: {timezone or 'N/A'}"
                )
            else:
                response_text = (
                    f"Weather for **{name}**"
                    f"{f' ({admin1}, {country})' if admin1 or country else ''}\n\n"
                    f"- Today: {today_emoji} **{_fmt_temp(today_min)}** to **{_fmt_temp(today_max)}**, {today_condition}\n"
                    f"- Tomorrow: {tomorrow_emoji} **{_fmt_temp(tomorrow_min)}** to **{_fmt_temp(tomorrow_max)}**, {tomorrow_condition}\n"
                    f"- Week overview: {_fmt_temp(week_min)} to {_fmt_temp(week_max)} (avg {_fmt_temp(week_avg)})\n"
                    f"- Coordinates: {lat:.3f}, {lon:.3f}\n"
                    f"- Timezone: {timezone or 'N/A'}"
                )
            return {
                "status": "ok",
                "requested_location": location,
                "location": name,
                "admin1": admin1,
                "country": country,
                "latitude": lat,
                "longitude": lon,
                "timezone": timezone,
                "units": {
                    "temperature": daily_units.get("temperature_2m_max", "C"),
                },
                "scope": scope,
                "language": language,
                "today": {
                    "date": _safe_get(times, 0),
                    "temperature_min_c": today_min,
                    "temperature_max_c": today_max,
                    "weathercode": today_code,
                    "emoji": today_emoji,
                    "condition": today_condition,
                },
                "tomorrow": {
                    "date": _safe_get(times, 1),
                    "temperature_min_c": tomorrow_min,
                    "temperature_max_c": tomorrow_max,
                    "weathercode": tomorrow_code,
                    "emoji": tomorrow_emoji,
                    "condition": tomorrow_condition,
                },
                "daily": daily_entries,
                "week_overview": {
                    "temperature_min_c": week_min,
                    "temperature_max_c": week_max,
                    "temperature_avg_c": week_avg,
                },
                "response_text": response_text,
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

