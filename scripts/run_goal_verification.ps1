# Goal verification — single-session reproducible evidence capture
$ErrorActionPreference = "Stop"
$Scratch = $env:GOAL_SCRATCH
if (-not $Scratch) { $Scratch = "C:\Users\Keith\AppData\Local\Temp\grok-goal-96e31bb2e41a\implementer" }
New-Item -ItemType Directory -Force -Path $Scratch | Out-Null
$Root = Split-Path $PSScriptRoot -Parent

docker context use desktop-linux | Out-Null
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe" -ErrorAction SilentlyContinue
docker desktop start 2>&1 | Out-Null
$ready = $false
for ($i = 0; $i -lt 45; $i++) {
    $info = docker info 2>&1 | Out-String
    if ($info -match "Server Version") {
        $info | Out-File "$Scratch\docker_info.log" -Encoding utf8
        $ready = $true
        break
    }
    Start-Sleep -Seconds 4
}
if (-not $ready) {
    docker info 2>&1 | Out-File "$Scratch\docker_info.log" -Encoding utf8
    throw "Docker daemon not ready"
}

Push-Location $Root
$env:GOAL_SCRATCH = $Scratch
& .\.venv\Scripts\python scripts\verify_docker.py
if ($LASTEXITCODE -ne 0) { throw "verify_docker.py failed with $LASTEXITCODE" }
& .\.venv\Scripts\pytest -v 2>&1 | Tee-Object -FilePath "$Scratch\pytest.log"
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }
git -C $Root log --oneline -3 2>&1 | Out-File "$Scratch\git.log" -Encoding utf8
git -C $Root status --short 2>&1 | Out-File "$Scratch\git.log" -Append -Encoding utf8
Pop-Location
Write-Host "VERIFICATION_OK"