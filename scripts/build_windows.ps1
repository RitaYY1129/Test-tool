param(
    [string]$OutputDirectory = "dist"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

python -m pip install -e .
python -m pip install pyinstaller
$targetRoot = Join-Path $projectRoot $OutputDirectory
$targetDirectory = Join-Path $targetRoot "TestPilotAI"
if (Test-Path -LiteralPath $targetDirectory) {
    throw "输出目录已存在，请先移动或删除：$targetDirectory"
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
Write-Host "构建完成：$targetDirectory"
