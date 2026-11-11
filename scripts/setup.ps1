# Create .venv with Python 3.11 and install the project plus test tools.
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1          # verifier + tests
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Train   # also torch/transformers/trl
param([switch]$Train)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot)

if (-not (Test-Path .venv)) { py -3.11 -m venv .venv }
$extras = if ($Train) { "dev,train" } else { "dev" }
& .venv\Scripts\python.exe -m pip install --upgrade pip
& .venv\Scripts\python.exe -m pip install -e ".[$extras]"
& .venv\Scripts\python.exe -m pytest -q
