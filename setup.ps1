# Native Windows bootstrap. Provider overrides stay in the separate launcher.
param(
    [switch]$T3,
    [switch]$FilesOnly,
    [string]$T3Settings,
    [string]$T3Instance,
    [string]$CodexHome,
    [string]$CodexBinary,
    [string]$Port,
    [switch]$Help
)
$ErrorActionPreference = 'Stop'
$uvCommand = Get-Command uv.exe -ErrorAction SilentlyContinue
$uv = if ($uvCommand) { $uvCommand.Source } else { Join-Path $env:USERPROFILE '.local/bin/uv.exe' }
if (-not (Test-Path -LiteralPath $uv)) {
    throw 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/'
}
$setupArgs = @('--uv', $uv)
if ($T3) { $setupArgs += '--t3' }
if ($FilesOnly) { $setupArgs += '--files-only' }
if ($Help) { $setupArgs += '--help' }
foreach ($entry in @(
    @('--t3-settings', $T3Settings), @('--t3-instance', $T3Instance),
    @('--codex-home', $CodexHome), @('--codex-binary', $CodexBinary), @('--port', $Port)
)) {
    if ($entry[1]) { $setupArgs += $entry[0], $entry[1] }
}
& $uv run --no-project --python 3.12 (Join-Path $PSScriptRoot 'scripts/setup_windows.py') @setupArgs
exit $LASTEXITCODE
