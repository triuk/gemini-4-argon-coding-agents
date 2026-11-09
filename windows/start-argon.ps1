param([switch]$Background)
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
$runtime = Join-Path $PSScriptRoot 'argon_runtime.py'
if ($Background) { & $python $runtime proxy --background }
else { & $python $runtime proxy }
exit $LASTEXITCODE
