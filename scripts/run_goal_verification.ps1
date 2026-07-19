# Goal verification — delegates to capture_goal_evidence.py (single entry point)
$ErrorActionPreference = "Stop"
$Scratch = $env:GOAL_SCRATCH
if (-not $Scratch) { $Scratch = Join-Path $env:TEMP "x402-mcp-evidence" }
New-Item -ItemType Directory -Force -Path $Scratch | Out-Null
$Root = Split-Path $PSScriptRoot -Parent
$env:GOAL_SCRATCH = $Scratch

docker context use desktop-linux 2>&1 | Out-Null

Push-Location $Root
& .\.venv\Scripts\python scripts\capture_goal_evidence.py
$code = $LASTEXITCODE
Pop-Location

if ($code -ne 0) { throw "capture_goal_evidence.py failed with $code" }
Write-Host "VERIFICATION_OK"