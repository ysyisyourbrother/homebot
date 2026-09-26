<#
.SYNOPSIS
    注册（或移除）homebot 数据目录的每日备份计划任务。

.DESCRIPTION
    注册一个每天固定时间运行 backup-homebot.ps1 的计划任务，默认每天 03:30，
    窗口隐藏、只运行 30 分钟上限、错过时间点在稍后补跑。

    任务是「每天」触发，不需要登录会话（不像网关任务那样依赖音频设备），
    所以按当前用户身份以受限权限运行即可。

.PARAMETER TaskName
    任务名，默认 homebot-Backup。

.PARAMETER ScriptPath
    要运行的备份脚本，默认同目录下的 backup-homebot.ps1。

.PARAMETER At
    每天运行时刻，24 小时制 HH:mm，默认 03:30。

.PARAMETER Keep
    每个集合保留的份数，默认 3。

.PARAMETER Uninstall
    停掉并移除该任务。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\windows\install-backup-task.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\windows\install-backup-task.ps1 -At 04:15

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\windows\install-backup-task.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'homebot-Backup',
    # 空值表示"同目录下的 backup-homebot.ps1"。不能在 param 默认值里用 $PSScriptRoot：
    # 带 [CmdletBinding()] 的脚本在绑定参数时 $PSScriptRoot 还是空的。
    [string]$ScriptPath = '',
    [string]$At = '03:30',
    [string]$DataDir = (Join-Path $env:USERPROFILE '.homebot'),
    [int]$Keep = 3,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

if (-not $ScriptPath) { $ScriptPath = Join-Path $PSScriptRoot 'backup-homebot.ps1' }

if ($Uninstall) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "已移除计划任务 $TaskName。已有的快照保留在 $(Join-Path $DataDir 'backups')" -ForegroundColor Green
    exit 0
}

if (-not (Test-Path $ScriptPath)) { throw "backup script not found: $ScriptPath" }

$runAt = [datetime]::ParseExact($At, 'HH:mm', [System.Globalization.CultureInfo]::InvariantCulture)

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -DataDir "{1}" -Keep {2}' -f $ScriptPath, $DataDir, $Keep) `
    -WorkingDirectory (Split-Path -Parent $ScriptPath)
$trigger  = New-ScheduledTaskTrigger -Daily -At $runAt
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal -UserId "$env:COMPUTERNAME\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description ('Daily backup of {0}' -f $DataDir) | Out-Null

Write-Host "registered: $TaskName (daily at $At)" -ForegroundColor Green
Write-Host ("  {0} -DataDir `"{1}`" -Keep {2}" -f $ScriptPath, $DataDir, $Keep)
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State | Format-List
