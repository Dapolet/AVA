from avaai.plugins.base import BasePlugin


class Plugin(BasePlugin):
    id = "example_plugin"
    name = "Example Plugin"
    version = "0.1.0"

    def run(self, context) -> dict:
        return {"status": "ok", "message": "Example plugin executed"}

