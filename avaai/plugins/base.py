class BasePlugin:
    id: str = ""
    name: str = ""
    version: str = ""

    def register(self, registry) -> None:
        registry.register(self)

    def run(self, context) -> dict:
        return {}
