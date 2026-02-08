import ast
import json
from datetime import datetime
from typing import Any, Dict, List, Optional


def _safe_eval(expression: str) -> Any:
    if not isinstance(expression, str):
        raise ValueError("Invalid expression")
    expression = expression.strip()
    if not expression:
        raise ValueError("Empty expression")
    if len(expression) > 100:
        raise ValueError("Expression too long")
    allowed_nodes = (
        ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Load,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow, ast.USub,
        ast.Constant, ast.FloorDiv
    )
    node = ast.parse(expression, mode="eval")
    for child in ast.walk(node):
        if not isinstance(child, allowed_nodes):
            raise ValueError("Unsupported expression")
        if isinstance(child, ast.Constant) and isinstance(child.value, (int, float)):
            if abs(child.value) > 1_000_000:
                raise ValueError("Number too large")
        if isinstance(child, ast.Pow):
            exponent = child.right
            if isinstance(exponent, ast.Constant) and isinstance(exponent.value, (int, float)):
                if exponent.value > 8:
                    raise ValueError("Exponent too large")
            else:
                raise ValueError("Exponent must be a constant")
    return eval(compile(node, "<calc>", "eval"), {"__builtins__": {}})


def _get_weather_plugin(plugin_registry: Optional[object]):
    if plugin_registry is None or not hasattr(plugin_registry, "get"):
        return None
    info = plugin_registry.get("weather_plugin")
    if not info:
        return None
    if hasattr(info, "enabled") and not info.enabled:
        return None
    return info


def _get_exchange_rate_plugin(plugin_registry: Optional[object]):
    if plugin_registry is None or not hasattr(plugin_registry, "get"):
        return None
    info = plugin_registry.get("exchangerate_plugin")
    if not info:
        return None
    if hasattr(info, "enabled") and not info.enabled:
        return None
    return info


def _get_wikimedia_plugin(plugin_registry: Optional[object]):
    if plugin_registry is None or not hasattr(plugin_registry, "get"):
        return None
    info = plugin_registry.get("wikimedia_plugin")
    if not info:
        return None
    if hasattr(info, "enabled") and not info.enabled:
        return None
    return info


def get_tools(plugin_registry: Optional[object] = None) -> List[Dict[str, Any]]:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_current_time",
                "description": "Get the current server time in ISO format",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "calculate",
                "description": "Evaluate a simple math expression",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string"}
                    },
                    "required": ["expression"]
                }
            }
        },
    ]
    weather_plugin = _get_weather_plugin(plugin_registry)
    if weather_plugin:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get today's and tomorrow's forecast plus a weekly temperature overview.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string", "description": "City or location name"},
                            "language": {
                                "type": "string",
                                "enum": ["en", "ru"],
                                "description": "Response language"
                            },
                        },
                    },
                },
            }
        )
    exchange_plugin = _get_exchange_rate_plugin(plugin_registry)
    if exchange_plugin:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "get_exchange_rate",
                    "description": "Get currency exchange rates or convert between two currencies.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "base": {"type": "string", "description": "Base currency code (e.g., USD)"},
                            "target": {"type": "string", "description": "Target currency code (e.g., EUR)"},
                            "amount": {"type": "number", "description": "Amount in base currency"},
                        },
                        "required": ["base"],
                    },
                },
            }
        )
    wikimedia_plugin = _get_wikimedia_plugin(plugin_registry)
    if wikimedia_plugin:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "get_wiki_summary",
                    "description": "Fetch a Wikipedia summary for a query.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "language": {
                                "type": "string",
                                "enum": ["en", "ru"],
                                "description": "Response language",
                            },
                        },
                        "required": ["query"],
                    },
                },
            }
        )
    return tools


def run_tool(
    name: str,
    arguments: Dict[str, Any],
    plugin_registry: Optional[object] = None,
) -> Dict[str, Any]:
    if name == "get_current_time":
        return {"time": datetime.now().isoformat()}
    if name == "calculate":
        expression = arguments.get("expression", "")
        try:
            return {"result": _safe_eval(expression)}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}
    if name == "get_weather":
        weather_plugin = _get_weather_plugin(plugin_registry)
        if not weather_plugin:
            return {"status": "error", "message": "Weather plugin is not available."}
        location = arguments.get("location") or "New York"
        language = arguments.get("language")
        return weather_plugin.instance.run({"location": location, "language": language})
    if name == "get_exchange_rate":
        exchange_plugin = _get_exchange_rate_plugin(plugin_registry)
        if not exchange_plugin:
            return {"status": "error", "message": "Exchange rate plugin is not available."}
        return exchange_plugin.instance.run(
            {
                "base": arguments.get("base"),
                "target": arguments.get("target"),
                "amount": arguments.get("amount"),
            }
        )
    if name == "get_wiki_summary":
        wikimedia_plugin = _get_wikimedia_plugin(plugin_registry)
        if not wikimedia_plugin:
            return {"status": "error", "message": "Wikimedia plugin is not available."}
        return wikimedia_plugin.instance.run(
            {
                "query": arguments.get("query"),
                "language": arguments.get("language"),
            }
        )
    raise ValueError(f"Unknown tool: {name}")


def tool_call_to_message(
    tool_call: Dict[str, Any],
    plugin_registry: Optional[object] = None,
) -> Dict[str, Any]:
    function = tool_call.get("function", {})
    name = function.get("name", "")
    raw_args = function.get("arguments", "{}")
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
    except json.JSONDecodeError:
        args = {}
    try:
        result = run_tool(name, args, plugin_registry=plugin_registry)
    except Exception as exc:
        result = {"status": "error", "message": str(exc)}
    return {
        "role": "tool",
        "tool_call_id": tool_call.get("id"),
        "name": name,
        "content": json.dumps(result)
    }
