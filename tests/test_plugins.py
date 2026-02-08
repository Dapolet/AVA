import json
import os
import tempfile
import unittest

from avaai.plugins.loader import load_plugins, set_plugin_enabled
from avaai.plugins.registry import PluginRegistry
from avaai.monitoring.db import init_db


PLUGIN_JSON = {
    "id": "test_plugin",
    "name": "Test Plugin",
    "version": "0.1.0",
    "entrypoint": "plugin:Plugin",
    "enabled": True,
    "description": "Test plugin"
}

PLUGIN_PY = """
from avaai.plugins.base import BasePlugin

class Plugin(BasePlugin):
    id = "test_plugin"
    name = "Test Plugin"
    version = "0.1.0"
"""


class PluginLoaderTests(unittest.TestCase):
    def test_loads_plugin(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_dir = os.path.join(tmpdir, "plugins")
            os.makedirs(os.path.join(plugins_dir, "test_plugin"), exist_ok=True)

            manifest_path = os.path.join(plugins_dir, "test_plugin", "plugin.json")
            plugin_path = os.path.join(plugins_dir, "test_plugin", "plugin.py")
            with open(manifest_path, "w", encoding="utf-8") as handle:
                json.dump(PLUGIN_JSON, handle)
            with open(plugin_path, "w", encoding="utf-8") as handle:
                handle.write(PLUGIN_PY)

            db_path = os.path.join(tmpdir, "monitoring.db")
            init_db(db_path)

            registry = PluginRegistry()
            load_plugins(plugins_dir, registry, db_path)

            self.assertIsNotNone(registry.get("test_plugin"))

    def test_disable_plugin_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_dir = os.path.join(tmpdir, "plugins")
            os.makedirs(os.path.join(plugins_dir, "test_plugin"), exist_ok=True)

            manifest_path = os.path.join(plugins_dir, "test_plugin", "plugin.json")
            with open(manifest_path, "w", encoding="utf-8") as handle:
                json.dump(PLUGIN_JSON, handle)

            ok = set_plugin_enabled(plugins_dir, "test_plugin", False)
            self.assertTrue(ok)

            with open(manifest_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
                self.assertFalse(data["enabled"])


if __name__ == "__main__":
    unittest.main()

