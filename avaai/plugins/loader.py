import importlib.util
import json
import os
from typing import List, Dict, Optional, Tuple

from avaai.monitoring.audit import log_plugin_run
from .registry import PluginRegistry


def _load_manifest(manifest_path: str) -> Dict:
    with open(manifest_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def discover_manifests(plugins_dir: str) -> List[str]:
    if not os.path.isdir(plugins_dir):
        return []

    manifests = []
    for entry in os.listdir(plugins_dir):
        manifest_path = os.path.join(plugins_dir, entry, "plugin.json")
        if os.path.isfile(manifest_path):
            manifests.append(manifest_path)
    return manifests


def list_manifests(plugins_dir: str) -> List[Dict]:
    manifests = []
    for manifest_path in discover_manifests(plugins_dir):
        try:
            manifest = _load_manifest(manifest_path)
            manifest["__path"] = manifest_path
            manifests.append(manifest)
        except Exception:
            continue
    return manifests


def _import_entrypoint(plugin_dir: str, entrypoint: str) -> Tuple[Optional[object], Optional[str]]:
    if ":" not in entrypoint:
        return None, "Invalid entrypoint format"

    module_name, class_name = entrypoint.split(":", 1)
    module_path = os.path.join(plugin_dir, f"{module_name}.py")
    if not os.path.isfile(module_path):
        return None, "Module file not found"

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        return None, "Failed to load module spec"

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, class_name):
        return None, "Class not found in module"

    cls = getattr(module, class_name)
    return cls(), None


def load_plugins(plugins_dir: str, registry: PluginRegistry, db_path: str) -> None:
    manifests = discover_manifests(plugins_dir)
    for manifest_path in manifests:
        plugin_dir = os.path.dirname(manifest_path)
        try:
            manifest = _load_manifest(manifest_path)
            if not manifest.get("enabled", True):
                log_plugin_run(db_path, manifest.get("id", "unknown"), "load", "skipped", "")
                continue

            plugin_instance, error = _import_entrypoint(plugin_dir, manifest.get("entrypoint", ""))
            if error:
                log_plugin_run(db_path, manifest.get("id", "unknown"), "load", "error", error)
                continue

            registry.register(
                plugin_instance,
                enabled=True,
                description=manifest.get("description", "")
            )
            log_plugin_run(db_path, manifest.get("id", "unknown"), "load", "ok", "")
        except Exception as exc:
            log_plugin_run(db_path, "unknown", "load", "error", str(exc))


def set_plugin_enabled(plugins_dir: str, plugin_id: str, enabled: bool) -> bool:
    for manifest_path in discover_manifests(plugins_dir):
        try:
            manifest = _load_manifest(manifest_path)
            if manifest.get("id") == plugin_id:
                manifest["enabled"] = enabled
                with open(manifest_path, "w", encoding="utf-8") as handle:
                    json.dump(manifest, handle, indent=2)
                return True
        except Exception:
            continue
    return False

