$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
python scripts/verify_release.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python scripts/security_scan.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python scripts/build_wheel.py --output-dir dist/python
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python scripts/build_private_release.py --output-dir dist/private
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Get-FileHash -Algorithm SHA256 dist/python/*.whl,dist/private/*.tar.gz
