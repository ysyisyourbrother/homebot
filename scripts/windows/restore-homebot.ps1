<#
.SYNOPSIS
    用快照恢复 homebot 数据目录（加性覆盖，永不删除现存文件）。

.DESCRIPTION
      1/5 选压缩包（-Archive；省略则取所有集合里最新的一份）
      2/5 校验它（可读、非空、含 config.json）
      3/5 停网关，并等到进程真的退出
      4/5 把当前状态先快照成滚动集合 prerestore（所以恢复本身也能撤回），
          再把压缩包覆盖回数据目录
      5/5 重启网关并等 /health

    覆盖是加性的：现在存在、而压缩包里没有的文件保持原样，所以恢复不会删数据。

.PARAMETER Archive
    要恢复的压缩包路径，省略则取最新的一份快照。

.PARAMETER List
    只列出可恢复的候选，不做恢复。

.PARAMETER Yes
    跳过确认提示（无人值守时用）。

.PARAMETER RepoRoot
    源码目录，默认取本脚本上两级目录；用于识别属于本项目的网关进程。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\windows\restore-homebot.ps1 -List

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\windows\restore-homebot.ps1
#>
[CmdletBinding()]
param(
    [string]$Archive = '',
    [switch]$List,
    [switch]$Yes,
    # 空值表示"取本脚本上两级目录"。不能在 param 默认值里用 $PSScriptRoot：
    # 带 [CmdletBinding()] 的脚本在绑定参数时 $PSScriptRoot 还是空的。
    [string]$RepoRoot = '',
    [string]$DataDir = (Join-Path $env:USERPROFILE '.homebot'),
    [string]$TaskName = 'homebot-Gateway',
    [string]$HealthUrl = 'http://127.0.0.1:18790/health',
    [int]$Keep = 3
)

$ErrorActionPreference = 'Stop'

if (-not $RepoRoot) { $RepoRoot = Join-Path $PSScriptRoot '..\..' }
$backup = Join-Path $PSScriptRoot 'backup-homebot.ps1'
$restart = Join-Path $PSScriptRoot 'restart-homebot.ps1'
$repo   = (Resolve-Path $RepoRoot).Path
$data   = $DataDir
$dest   = Join-Path $data 'backups'

function Get-Snapshots([string]$setLabel) {
    if (-not (Test-Path $dest)) { return @() }
    if ($setLabel) { $pattern = "^homebot-$setLabel-\d{8}-\d{6}\.zip$" }
    else           { $pattern = '^homebot-\d{8}-\d{6}\.zip$' }
    @(Get-ChildItem -Path $dest -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match $pattern } |
        Sort-Object LastWriteTime -Descending)
}

function Get-AllSnapshots {
    @(Get-Snapshots '') + @(Get-Snapshots 'preupdate') + @(Get-Snapshots 'prerestore') |
        Sort-Object LastWriteTime -Descending
}

function Get-GatewayProcesses {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -like "$repo\.venv\*" }
}

function Fail([string]$message) {
    Write-Host ''
    Write-Host "STOPPED: $message" -ForegroundColor Yellow
    exit 1
}

if ($List) {
    $all = @(Get-AllSnapshots)
    if ($all.Count -eq 0) { Write-Host "no snapshots in $dest"; exit 0 }
    $all | Select-Object Name, @{n='MB';e={[math]::Round($_.Length / 1MB, 1)}}, LastWriteTime |
        Format-Table -AutoSize
    exit 0
}

if (-not $Archive) {
    $newest = @(Get-AllSnapshots) | Select-Object -First 1
    if (-not $newest) { Fail "no snapshots in $dest - nothing to restore from" }
    $Archive = $newest.FullName
}
if (-not (Test-Path $Archive)) { Fail "archive not found: $Archive" }
$Archive = (Resolve-Path $Archive).Path

Write-Host '=== 1/5 archive ==='
Write-Host ("  {0} ({1:N1} MB, {2})" -f $Archive, ((Get-Item $Archive).Length / 1MB), (Get-Item $Archive).LastWriteTime)

Write-Host '=== 2/5 verify the archive ==='
Add-Type -AssemblyName System.IO.Compression.FileSystem
try {
    $z = [System.IO.Compression.ZipFile]::OpenRead($Archive)
    $entries = @($z.Entries | ForEach-Object { $_.FullName })
    $z.Dispose()
} catch {
    Fail "the archive is unreadable ($($_.Exception.Message))"
}
if ($entries -notcontains 'config.json') { Fail 'config.json is missing from the archive' }
$fileCount = @($entries | Where-Object { $_ -notlike '*\' }).Count
if ($fileCount -eq 0) { Fail 'the archive carries no files' }
Write-Host ("  ok: {0} entries, {1} files" -f $entries.Count, $fileCount)

if (-not $Yes) {
    Write-Host ''
    Write-Host "This overwrites files in $data (the current state is snapshotted first)."
    $answer = Read-Host 'Continue? [y/N]'
    if ($answer -ne 'y' -and $answer -ne 'Y') { Write-Host 'aborted, nothing was changed'; exit 1 }
}

Write-Host '=== 3/5 stop the gateway ==='
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$alive = $null
foreach ($i in 1..30) {
    $alive = @(Get-GatewayProcesses)
    if ($alive.Count -eq 0) { break }
    Start-Sleep -Seconds 1
}
if ($alive.Count -gt 0) {
    Write-Host '  the launcher left a process behind - stopping it explicitly'
    $alive | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}
Write-Host '  gateway stopped'

Write-Host '=== 4/5 snapshot current state, then copy the archive over it ==='
& powershell -NoProfile -ExecutionPolicy Bypass -File $backup -DataDir $data -Label 'prerestore' -Keep $Keep
if ($LASTEXITCODE -ne 0) {
    Fail "the safety snapshot failed - the data folder was NOT touched (start the gateway again: $restart)"
}

$tmp = Join-Path $env:TEMP ('homebot-restore-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
Expand-Archive -Path $Archive -DestinationPath $tmp -Force
robocopy $tmp $data /E /NFL /NDL /NJH /NJS /NP | Out-Null
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
Write-Host '  files restored'

Write-Host '=== 5/5 restart the gateway ==='
& powershell -NoProfile -ExecutionPolicy Bypass -File $restart -TaskName $TaskName -HealthUrl $HealthUrl -DataDir $data
if ($LASTEXITCODE -eq 0) {
    Write-Host ''
    Write-Host 'restore finished' -ForegroundColor Green
    exit 0
}

Write-Host ''
Write-Host 'the gateway is not answering after the restore - look at the log:' -ForegroundColor Yellow
Write-Host ("  Get-Content {0} -Tail 30 -Encoding UTF8" -f (Join-Path $data 'logs\gateway.log'))
exit 1
