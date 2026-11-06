# 註冊 Windows 排程：每週一 09:00 自動產出並寄出週報
# 用法（一般權限的 PowerShell 即可）：
#   powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Time "08:30"
# 移除：Unregister-ScheduledTask -TaskName "AI營運週報" -Confirm:$false
param(
    [string]$TaskName = "AI營運週報",
    [string]$Time = "09:00"
)

$script = Join-Path $PSScriptRoot "run_weekly.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory (Split-Path -Parent $PSScriptRoot)
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At $Time
# 筆電沒插電也執行、錯過時間（例如週一 9 點還沒開機）開機後補跑
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "AI 自動化營運週報：每週一產出 PDF 並寄送" -Force | Out-Null

Write-Host "已註冊排程「$TaskName」：每週一 $Time 執行 $script"
Write-Host "立即測試：Start-ScheduledTask -TaskName `"$TaskName`""
