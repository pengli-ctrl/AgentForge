#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python scripts/verify_release.py
python scripts/security_scan.py
python scripts/build_wheel.py --output-dir dist/python
python scripts/build_private_release.py --output-dir dist/private
sha256sum dist/python/*.whl dist/private/*.tar.gz
