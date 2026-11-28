# Put the app back in the state the demo video starts from, then start the server.
#
#   powershell -ExecutionPolicy Bypass -File demos\video\reset_demo.ps1
#
# Run this before every take. Approving a review item changes the knowledge
# version, and the cached answers belong to the version the take starts with.
# The starting state is data\app.video.db; data\app.db is overwritten with it.

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repo

if (-not (Test-Path data\app.video.db)) { throw "data\app.video.db not found" }

Get-CimInstance Win32_Process -Filter "name='python.exe'" |
    Where-Object { $_.CommandLine -like '*--port 8000*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -Confirm:$false }
Start-Sleep -Seconds 2

Copy-Item data\app.video.db data\app.db -Force

Start-Process -WindowStyle Minimized -FilePath "$repo\.venv\Scripts\python.exe" `
    -ArgumentList '-m', 'uvicorn', 'verdict.api.main:app', '--host', '127.0.0.1', '--port', '8000' `
    -WorkingDirectory $repo

foreach ($i in 1..40) {
    try {
        Invoke-RestMethod -Uri http://127.0.0.1:8000/api/health -TimeoutSec 3 | Out-Null
        Write-Output "Ready: http://localhost:8000/ask"
        exit 0
    } catch { Start-Sleep -Seconds 2 }
}
throw "The server did not start within 80 seconds."
