<#
.SYNOPSIS
    Download the BIRD dev set and place it at the layout the project expects.

.DESCRIPTION
    Target layout (paths are load-bearing - see datasets/README.md):

        datasets/dev.json
        datasets/dev_databases/<db_id>/<db_id>.sqlite

    BIRD's zip layout has changed between releases: the archive usually extracts
    into a dated subfolder, and dev_databases is often a SECOND zip nested inside
    the first. This script locates dev.json and dev_databases wherever they land
    and flattens them into datasets/, so it works across those variants.

    Safe to re-run. Skips the download if the zip is already in TEMP.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\fetch_bird.ps1
#>

[CmdletBinding()]
param(
    # Path to an already-downloaded dev.zip. If omitted, the script looks in
    # Downloads and TEMP, and downloads it only if neither has it.
    [string]$Zip
)

$ErrorActionPreference = "Stop"

$Url      = "https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip"
$Root     = Split-Path -Parent $PSScriptRoot
$Datasets = Join-Path $Root "datasets"
$Staging  = Join-Path $env:TEMP "bird-dev-extract"

if (-not $Zip) {
    # Reuse an existing download rather than pulling 330 MB again.
    $candidates = @(
        (Join-Path $env:USERPROFILE "Downloads\dev.zip"),
        (Join-Path $env:TEMP "bird-dev.zip")
    )
    $found = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($found) { $Zip = $found } else { $Zip = Join-Path $env:TEMP "bird-dev.zip" }
}

Write-Host "Project root : $Root"
Write-Host "Target       : $Datasets"
Write-Host ""

# --- 1. Download ------------------------------------------------------------
if (Test-Path $Zip) {
    $sizeMb = [math]::Round((Get-Item $Zip).Length / 1MB, 1)
    Write-Host "[1/5] Using existing zip ($sizeMb MB): $Zip"
    Write-Host "      Delete it, or pass -Zip <path>, to change this."
} else {
    Write-Host "[1/5] Downloading dev.zip (~1-2 GB, this takes a while)..."
    # curl.exe ships with Windows 10/11 and is far faster than Invoke-WebRequest
    # for large files (no progress-bar overhead). It also shows real throughput.
    curl.exe -L --fail -o $Zip $Url
    if ($LASTEXITCODE -ne 0) { throw "Download failed (curl exit $LASTEXITCODE)." }
}

# --- 2. Extract -------------------------------------------------------------
Write-Host "[2/5] Extracting to staging..."
if (Test-Path $Staging) { Remove-Item $Staging -Recurse -Force }
Expand-Archive -Path $Zip -DestinationPath $Staging -Force

# Some releases nest dev_databases as its own zip. Expand any inner zips once.
Get-ChildItem $Staging -Recurse -Filter "*.zip" | ForEach-Object {
    Write-Host "      Found nested zip: $($_.Name) - expanding"
    Expand-Archive -Path $_.FullName -DestinationPath $_.DirectoryName -Force
}

# --- 3. Locate the two things we actually need ------------------------------
Write-Host "[3/5] Locating dev.json and dev_databases..."

# Prefer the plain 'dev.json'; ignore macOS resource forks (__MACOSX).
$devJson = Get-ChildItem $Staging -Recurse -Filter "dev.json" |
           Where-Object { $_.FullName -notmatch "__MACOSX" } |
           Sort-Object { $_.FullName.Length } |
           Select-Object -First 1
if (-not $devJson) { throw "Could not find dev.json anywhere under $Staging" }

$devDbs = Get-ChildItem $Staging -Recurse -Directory -Filter "dev_databases" |
          Where-Object { $_.FullName -notmatch "__MACOSX" } |
          Sort-Object { $_.FullName.Length } |
          Select-Object -First 1
if (-not $devDbs) { throw "Could not find a dev_databases folder under $Staging" }

Write-Host "      dev.json      : $($devJson.FullName)"
Write-Host "      dev_databases : $($devDbs.FullName)"

# --- 4. Place into datasets/ ------------------------------------------------
Write-Host "[4/5] Copying into datasets/ ..."
if (-not (Test-Path $Datasets)) { New-Item -ItemType Directory -Force $Datasets | Out-Null }

Copy-Item $devJson.FullName (Join-Path $Datasets "dev.json") -Force

$targetDbs = Join-Path $Datasets "dev_databases"
if (Test-Path $targetDbs) { Remove-Item $targetDbs -Recurse -Force }
Copy-Item $devDbs.FullName $targetDbs -Recurse -Force

# Anything else useful that shipped alongside (gold SQL, evidence files).
Get-ChildItem $devJson.DirectoryName -File |
    Where-Object { $_.Name -ne "dev.json" -and $_.Extension -in ".json", ".sql", ".txt" } |
    ForEach-Object {
        Copy-Item $_.FullName (Join-Path $Datasets $_.Name) -Force
        Write-Host "      also copied: $($_.Name)"
    }

# --- 5. Verify --------------------------------------------------------------
Write-Host "[5/5] Verifying..."

$tasks = Get-Content (Join-Path $Datasets "dev.json") -Raw | ConvertFrom-Json
$dbDirs = Get-ChildItem $targetDbs -Directory
$sqlite = Get-ChildItem $targetDbs -Recurse -Filter "*.sqlite"

Write-Host ""
Write-Host "  questions in dev.json : $($tasks.Count)"
Write-Host "  database folders      : $($dbDirs.Count)"
Write-Host "  .sqlite files         : $($sqlite.Count)"

$ok = $true
if ($tasks.Count -lt 1000) { Write-Warning "Expected >1000 questions (Day 7 test asserts this)."; $ok = $false }
if ($sqlite.Count -lt 1)   { Write-Warning "No .sqlite files found - check the archive layout."; $ok = $false }

# A dehydrated OneDrive placeholder will open but behave badly. Prove one reads.
$probe = $sqlite | Select-Object -First 1
if ($probe) {
    Write-Host "  probe database        : $($probe.Name)"
    Write-Host ""
    Write-Host "  Sanity check with:"
    Write-Host "    python -c ""import sqlite3;c=sqlite3.connect(r'$($probe.FullName)');print([r[0] for r in c.execute(\""SELECT name FROM sqlite_master WHERE type='table'\"")])"""
}

Write-Host ""
if ($ok) {
    Write-Host "Done. BIRD dev is in place." -ForegroundColor Green
    Write-Host "Staging copy left at $Staging - delete it to reclaim disk."
} else {
    Write-Warning "Placed, but verification flagged something above. Inspect before trusting it."
}
