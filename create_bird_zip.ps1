# Create a cross-platform compatible ZIP for BIRD dataset
# This fixes the backslash issue for Kaggle upload

$sourceDir = "c:\Users\Dell\OneDrive\Desktop\verdict\datasets"
$zipPath = "c:\Users\Dell\OneDrive\Desktop\verdict\BIRD_dataset.zip"

# Remove old ZIP if exists
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
    Write-Host "Removed old ZIP file" -ForegroundColor Yellow
}

Write-Host "Creating cross-platform ZIP file..." -ForegroundColor Cyan

# Load .NET compression libraries
Add-Type -Assembly System.IO.Compression.FileSystem

# Create the ZIP archive
$compressionLevel = [System.IO.Compression.CompressionLevel]::Optimal
$zip = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)

# Get all files to include
$filesToAdd = @(
    "dev.json",
    "dev.sql", 
    "dev_tables.json",
    "dev_tied_append.json"
)

# Add root files
foreach ($file in $filesToAdd) {
    $fullPath = Join-Path $sourceDir $file
    if (Test-Path $fullPath) {
        $entryName = $file -replace '\\', '/'
        Write-Host "Adding: $entryName" -ForegroundColor Green
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $fullPath, $entryName, $compressionLevel) | Out-Null
    }
}

# Add all files from dev_databases
$devDatabasesPath = Join-Path $sourceDir "dev_databases"
if (Test-Path $devDatabasesPath) {
    $allFiles = Get-ChildItem -Path $devDatabasesPath -Recurse -File
    
    $count = 0
    foreach ($file in $allFiles) {
        # Get relative path and convert backslashes to forward slashes
        $relativePath = $file.FullName.Substring($sourceDir.Length + 1)
        $entryName = $relativePath -replace '\\', '/'
        
        $count++
        if ($count % 10 -eq 0) {
            Write-Host "Added $count files..." -ForegroundColor Gray
        }
        
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $file.FullName, $entryName, $compressionLevel) | Out-Null
    }
    Write-Host "Total files added: $count" -ForegroundColor Green
}

# Close the ZIP
$zip.Dispose()

Write-Host "`n✓ ZIP created successfully!" -ForegroundColor Green
Write-Host "Location: $zipPath" -ForegroundColor Cyan

# Show file size
$zipInfo = Get-Item $zipPath
$sizeMB = [math]::Round($zipInfo.Length / 1MB, 2)
Write-Host "Size: $sizeMB MB" -ForegroundColor Cyan

Write-Host "`nVerifying ZIP contents..." -ForegroundColor Yellow

# Quick verification - check first few entries
$zipArchive = [System.IO.Compression.ZipFile]::OpenRead($zipPath)

Write-Host "`nFirst 10 entries in ZIP:" -ForegroundColor Cyan
$zipArchive.Entries | Select-Object -First 10 | ForEach-Object {
    Write-Host "  $($_.FullName)" -ForegroundColor Gray
}

# Check for backslashes
$hasBackslashes = $zipArchive.Entries | Where-Object { $_.FullName -match '\\' }
if ($hasBackslashes) {
    Write-Host "`n⚠ WARNING: Found backslashes in ZIP paths!" -ForegroundColor Red
    $hasBackslashes | Select-Object -First 5 | ForEach-Object {
        Write-Host "  $($_.FullName)" -ForegroundColor Red
    }
} else {
    Write-Host "`n✓ All paths use forward slashes (cross-platform compatible)" -ForegroundColor Green
}

Write-Host "`nTotal entries in ZIP: $($zipArchive.Entries.Count)" -ForegroundColor Cyan

# Close verification
$zipArchive.Dispose()

Write-Host "`n✓ Ready for Kaggle upload!" -ForegroundColor Green
