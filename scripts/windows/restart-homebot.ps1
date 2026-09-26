<#
.SYNOPSIS
    重启 homebot 网关，并等它真的恢复响应。

.DESCRIPTION
    停掉计划任务会连带杀掉整棵启动链（含自看护循环），所以不会残留孤儿进程。
    停 → 等 4 秒 → 启动 → 轮询 /health，直到响应或超时。

.PARAMETER TaskName
    托管网关的计划任务名，默认 homebot-Gateway。

.PARAMETER HealthUrl
    健康检查地址，默认 http://127.0.0.1:18790/health。

.PARAMETER TimeoutSeconds
    等待健康检查的总秒数，默认 60。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\windows\restart-homebot.ps1
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'homebot-Gateway',
    [string]$HealthUrl = 'http://127.0.0.1:18790/health',
    [int]$TimeoutSeconds = 60,
    [string]$DataDir = (Join-Path $env:USERPROFILE '.homebot')
)

$ErrorActionPreference = 'Continue'

Write-Host 'stopping homebot ...'
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Start-Sleep -Seconds 4

Write-Host 'starting homebot ...'
Start-ScheduledTask -TaskName $TaskName

Write-Host 'waiting for the gateway to answer ...'
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    try {
        $r = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 4
        Write-Host ("  health: {0}" -f $r.Content)
        exit 0
    } catch {
        Start-Sleep -Seconds 2
    }
}

Write-Host '  the gateway did not answer in time - look at the log:' -ForegroundColor Yellow
Write-Host ("  Get-Content {0} -Tail 30 -Encoding UTF8" -f (Join-Path $DataDir 'logs\gateway.log'))
exit 1
