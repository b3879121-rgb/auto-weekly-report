# 給 Windows 工作排程器呼叫的包裝腳本：切到專案資料夾 → 執行週報 → 寄出 → 寫 log
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

New-Item -ItemType Directory -Force (Join-Path $root "output") | Out-Null
$log = Join-Path $root ("output\run_{0:yyyyMMdd_HHmm}.log" -f (Get-Date))

& $python run_report.py --regen-sample --send *>&1 | Tee-Object -FilePath $log
exit $LASTEXITCODE
