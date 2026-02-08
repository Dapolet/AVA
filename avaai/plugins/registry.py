from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class PluginInfo:
    plugin_id: str
    name: str
    version: str
    enabled: bool
    description: str
    instance: object


class PluginRegistry:
    def __init__(self):
        self._plugins: Dict[str, PluginInfo] = {}

    def register(self, plugin, enabled: bool = True, description: str = "") -> None:
        plugin_id = getattr(plugin, "id", "") or plugin.__class__.__name__
        name = getattr(plugin, "name", plugin_id)
        version = getattr(plugin, "version", "0.0.0")

        self._plugins[plugin_id] = PluginInfo(
            plugin_id=plugin_id,
            name=name,
            version=version,
            enabled=enabled,
            description=description,
            instance=plugin
        )

    def get(self, plugin_id: str) -> Optional[PluginInfo]:
        return self._plugins.get(plugin_id)

    def list(self) -> List[PluginInfo]:
        return list(self._plugins.values())

    def enable(self, plugin_id: str) -> None:
        if plugin_id in self._plugins:
            self._plugins[plugin_id].enabled = True

    def disable(self, plugin_id: str) -> None:
        if plugin_id in self._plugins:
            self._plugins[plugin_id].enabled = False
