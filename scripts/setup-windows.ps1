$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
python -c "import struct, sys; assert (3, 11) <= sys.version_info < (3, 14) and struct.calcsize('P') == 8, 'Use 64-bit Python 3.11, 3.12 or 3.13'; import tkinter"
if ($LASTEXITCODE -ne 0) { throw 'Install 64-bit Python 3.11-3.13 with Tcl/Tk and add Python to PATH.' }
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv.' }
}
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-windows.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check the error above.' }
Write-Host 'Ready. Run: .\scripts\run-windows.ps1'
