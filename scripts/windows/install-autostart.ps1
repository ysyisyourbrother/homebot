<#
.SYNOPSIS
    把 homebot 网关注册成 Windows 登录自启任务。

.DESCRIPTION
    做三件事：
      1. 在 %USERPROFILE%\.homebot\ 生成自看护启动脚本 run-gateway.cmd
      2. 注册计划任务（默认名 homebot-Gateway），用户登录时启动，窗口隐藏
      3. 网关进程退出后由启动脚本自动重新拉起（10 秒后）

    之所以不用 Windows 服务：音频设备属于交互式用户会话，Session 0 里
    的服务访问不到麦克风。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\windows\install-autostart.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\windows\install-autostart.ps1 -Uninstall
#>
param(
    # homebot 源码目录；默认取本脚本上两级目录
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$TaskName = "homebot-Gateway",
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

$dataDir  = Join-Path $env:USERPROFILE ".homebot"
$launcher = Join-Path $dataDir "run-gateway.cmd"
$logFile  = Join-Path $dataDir "logs\gateway.log"

if ($Uninstall) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Remove-Item $launcher -ErrorAction SilentlyContinue
    Write-Host "已移除计划任务 $TaskName 与启动脚本。" -ForegroundColor Green
    Write-Host "日志与数据保留在 $dataDir"
    exit 0
}

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "找不到虚拟环境解释器：$python" -ForegroundColor Red
    Write-Host "请先在仓库目录执行：" -ForegroundColor Yellow
    Write-Host "    python -m venv .venv"
    Write-Host "    .venv\Scripts\python -m pip install -e ."
    exit 1
}

New-Item -ItemType Directory -Force -Path (Join-Path $dataDir "logs") | Out-Null

# 启动脚本：设置 UTF-8、写日志、看护循环
@"
@echo off
REM 由 scripts\windows\install-autostart.ps1 生成，可安全删除后重新生成。
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set LOG=$logFile

:loop
for %%A in ("%LOG%") do if %%~zA GTR 10485760 move /y "%LOG%" "%LOG%.1" >nul
for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH:mm:ss"') do set STAMP=%%t
echo. >> "%LOG%"
echo ===== %STAMP% starting ===== >> "%LOG%"
cd /d "$RepoRoot"
"$python" -u -m homebot gateway >> "%LOG%" 2>&1
echo ===== %STAMP% exited with code %ERRORLEVEL%, restarting in 10s ===== >> "%LOG%"
ping -n 11 127.0.0.1 >nul
goto loop
"@ | Set-Content -Path $launcher -Encoding ASCII

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# 用 PowerShell 隐藏窗口启动；任务跟踪 PowerShell 进程，随网关一起存活
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument ("-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command `"& '{0}'`"" -f $launcher) `
    -WorkingDirectory $RepoRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:COMPUTERNAME\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -MultipleInstances IgnoreNew -Hidden
$principal = New-ScheduledTaskPrincipal -UserId "$env:COMPUTERNAME\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "homebot gateway（登录自启，用户会话内运行以访问音频设备）" | Out-Null

Write-Host "已注册计划任务：$TaskName" -ForegroundColor Green
Write-Host "启动脚本：$launcher"
Write-Host "日志文件：$logFile"
Write-Host ""
Write-Host "现在启动它：" -ForegroundColor Cyan
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 20
try {
    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:18790/health" -UseBasicParsing -TimeoutSec 5
    Write-Host ("网关已就绪：" + $resp.Content) -ForegroundColor Green
} catch {
    Write-Host "网关尚未响应，请查看日志：$logFile" -ForegroundColor Yellow
}
