param(
    [string]$OutputDirectory = "release"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

python -m pip install -e ".[desktop]"
python -m pip install pyinstaller

$targetRoot = Join-Path $projectRoot $OutputDirectory
$targetDirectory = Join-Path $targetRoot "TestPilotAI"

# A release is replaced in place.  This deliberately keeps exactly one
# user-facing installation directory and prevents old versions accumulating.
if (Test-Path -LiteralPath $targetDirectory) {
    Remove-Item -LiteralPath $targetDirectory -Recurse -Force
}

python -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --name TestPilotAI `
  --paths src `
  --distpath $targetRoot `
  --workpath build-pyinstaller `
  src/testpilot/main.py

Copy-Item -LiteralPath "README.md" -Destination $targetDirectory
Copy-Item -LiteralPath "docs\user-guide.md" -Destination $targetDirectory
Write-Host "Build complete: $targetDirectory"
