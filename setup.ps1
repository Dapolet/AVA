$ErrorActionPreference = "Stop"

Write-Host "Setting up AVA..."

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
} else {
    Write-Host "Virtual environment already exists."
}

Write-Host "Activating virtual environment..."
& .\.venv\Scripts\Activate.ps1

Write-Host "Installing dependencies..."
pip install -r requirements.txt

$secretsPath = ".streamlit\secrets.toml"
$secretsExample = ".streamlit\secrets.example.toml"

if (-not (Test-Path $secretsPath)) {
    if (Test-Path $secretsExample) {
        Write-Host "Creating secrets.toml from example (no overwrite)."
        Copy-Item $secretsExample $secretsPath
    } else {
        Write-Warning "Missing .streamlit\secrets.example.toml. Please create .streamlit\secrets.toml manually."
    }
} else {
    Write-Host "Secrets file already exists. Skipping copy."
}

Write-Host "Starting Streamlit app..."
streamlit run main.py
