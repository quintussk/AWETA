#!/usr/bin/env pwsh
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Build standalone Windows executable using PyInstaller

$ProjectRoot = (Resolve-Path "$PSScriptRoot/..")
Set-Location $ProjectRoot

python -m venv .venv
./.venv/Scripts/Activate.ps1
python -m pip install --upgrade pip
python -m pip install "pyinstaller>=6.10" "python-snap7>=1.3.0"

pyinstaller \
  --name aweta-app \
  --onefile \
  --clean \
  --console \
  main.py

Write-Host "Build complete. Binaries in: $ProjectRoot/dist"


