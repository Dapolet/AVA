# AVA 🌸

AVA is a Streamlit-based chat app with admin controls, model settings, plugin tooling, and
basic usage monitoring. It integrates with OpenRouter for model access and supports
optional tools like weather, exchange rates, and Wikipedia summaries.

## Highlights ✨
- Clean chat UI with streaming or non-streaming responses
- Model selection, temperature, max tokens, and tool toggles
- Admin-gated Settings, Plugins, and Debug pages
- Plugin system with built-in examples
- Usage metrics stored in a local SQLite DB

## Quick Start (Windows) ⚡
```powershell
.\setup.ps1
```
If PowerShell blocks scripts:
```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

## Manual Setup (Any OS) 🧰
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration 🔐
Create `.streamlit/secrets.toml` (copy from `.streamlit/secrets.example.toml`) and set:
```
OPENROUTER_API_KEY = "your_openrouter_api_key"
ADMIN_PASSWORD = "your_admin_password"
```

Optional environment variables:
- `MONITORING_DB_PATH` (default: `data/monitoring.db`)
- `PLUGINS_DIR` (default: `plugins`)
- `AVA_ALLOWED_PLUGINS` (comma-separated allowlist of plugin IDs)
- `AVA_MAX_UPLOAD_TOTAL_BYTES` (default: `2000000`)
- `AVA_MAX_UPLOAD_IMAGE_BYTES` (default: `1000000`)
- `AVA_MAX_UPLOAD_TEXT_BYTES` (default: `200000`)
- `AVA_MAX_UPLOAD_FILES` (default: `6`)

## Run ▶️
```bash
streamlit run main.py
```

## Admin Access 🔒
The Settings, Plugins, and Debug pages require `ADMIN_PASSWORD`. If it is not set,
admin pages will be blocked.

## Plugins 🧩
Plugins live under `plugins/` and can be enabled or disabled in `plugin.json`.
Built-in examples:
- Weather (Open-Meteo)
- Exchange rate (ExchangeRate-API)
- Wikipedia summaries (MediaWiki REST API)

## Data 📦
- Monitoring DB: `data/monitoring.db`
- Saved settings: `data/settings.json`

## Project Structure 🗂️
- `main.py`: App entrypoint and navigation
- `avaai/`: Core app logic
- `pages/`: Streamlit pages
- `plugins/`: Plugin implementations
- `.streamlit/`: Streamlit config and secrets template

## Troubleshooting 🧯
- If you see `402` errors, the selected model is not free or your account has no credits.
- If you see `404` errors, the selected model is unavailable or not permitted.
- If tools fail, disable tools or switch models in Settings.

## License 📄
GNU General Public License v3.0. See `LICENSE`.
