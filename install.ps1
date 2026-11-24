# Установка Spoti Skipper (Windows). Запуск: правой кнопкой -> "Выполнить с помощью PowerShell"
# или в терминале:  powershell -ExecutionPolicy Bypass -File .\install.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "== 1/3 Расширение Spicetify ==" -ForegroundColor Cyan
if (-not (Get-Command spicetify -ErrorAction SilentlyContinue)) {
    Write-Host "spicetify не найден. Установи его: https://spicetify.app/docs/getting-started" -ForegroundColor Red
    exit 1
}
$userdata = (& spicetify path userdata 2>$null | Select-Object -Last 1)
if (-not $userdata -or -not (Test-Path $userdata)) { $userdata = Join-Path $env:APPDATA "spicetify" }
$extDir = Join-Path $userdata "Extensions"
New-Item -ItemType Directory -Force -Path $extDir | Out-Null
Copy-Item (Join-Path $root "extension\spoti-skipper.js") $extDir -Force
& spicetify config extensions spoti-skipper.js
& spicetify apply

Write-Host "== 2/3 Python-зависимости ==" -ForegroundColor Cyan
$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
$venv = Join-Path $root "listener\.venv"
if (-not (Test-Path $venv)) { & $py -m venv $venv }
& (Join-Path $venv "Scripts\python.exe") -m pip install --upgrade pip
& (Join-Path $venv "Scripts\python.exe") -m pip install -r (Join-Path $root "listener\requirements.txt")

Write-Host "== 3/3 Готово ==" -ForegroundColor Green
Write-Host "Запусти start.bat и скажи: «Джарвис, некст»"
