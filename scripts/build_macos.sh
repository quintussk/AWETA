#!/usr/bin/env bash
set -euo pipefail

# Build standalone macOS executable using PyInstaller
# Output: dist/aweta-app (console) and dist/aweta-app.app (GUI bundle if enabled)

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "pyinstaller>=6.10" "python-snap7>=1.3.0"

# Build single-file console binary targeting main.py
pyinstaller \
  --name aweta-app \
  --onefile \
  --clean \
  --console \
  main.py

echo "Build complete. Binaries in: $PROJECT_ROOT/dist"


