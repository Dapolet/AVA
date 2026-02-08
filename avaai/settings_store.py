import json
import os
import tempfile
from typing import Any, Dict


def _settings_path(base_dir: str) -> str:
    return os.path.join(base_dir, "data", "settings.json")


def load_settings(base_dir: str) -> Dict[str, Any]:
    path = _settings_path(base_dir)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(base_dir: str, data: Dict[str, Any]) -> None:
    path = _settings_path(base_dir)
    dir_path = os.path.dirname(path)
    os.makedirs(dir_path, exist_ok=True)
    current = load_settings(base_dir)
    current.update(data)
    fd, tmp_path = tempfile.mkstemp(prefix="settings_", suffix=".tmp", dir=dir_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(current, handle, ensure_ascii=True, indent=2)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
