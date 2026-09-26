<#
.SYNOPSIS
    给 homebot 数据目录做滚动快照，并校验压缩包是否可用。

.DESCRIPTION
    默认快照整个 %USERPROFILE%\.homebot（配置、workspace、语音模型），排除 backups
    目录本身与 Chrome profile —— 这两者都可以重建。

    写完立即校验压缩包：可读、非空、含 config.json、含 workspace\。校验失败就删掉
    压缩包并以退出码 1 结束，所以坏备份不会被误当成好备份。

    滚动窗口：每个集合只保留最新 Keep 份，且三个集合各自滚动，所以连续重试更新
    不会把每日快照挤掉。

      集合        文件名                            谁在写
      每日        homebot-<时间戳>.zip              计划任务（见 install-backup-task.ps1）
      更新前      homebot-preupdate-<时间戳>.zip    update-homebot.ps1
      恢复前      homebot-prerestore-<时间戳>.zip   restore-homebot.ps1

.PARAMETER DataDir
    homebot 数据目录，默认 $env:USERPROFILE\.homebot。

.PARAMETER List
    只列出已有快照，不做备份。

.PARAMETER Label
    集合名（仅小写字母与数字），例如 preupdate、prerestore。省略即为每日集合。

.PARAMETER Keep
    每个集合保留的份数，默认 3，最小 2。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\windows\backup-homebot.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\windows\backup-homebot.ps1 -List

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\windows\backup-homebot.ps1 -Label preupdate -Keep 5
#>
[CmdletBinding()]
param(
    [string]$DataDir = (Join-Path $env:USERPROFILE '.homebot'),
    [switch]$List,
    [string]$Label = '',
    [int]$Keep = 3
)

$ErrorActionPreference = 'Continue'

$source = $DataDir
$dest   = Join-Path $source 'backups'

if ($Keep -lt 2) { $Keep = 2 }
if ($Label -and $Label -notmatch '^[a-z0-9]+$') {
    Write-Host "invalid -Label '$Label' (仅小写字母与数字)"
    exit 1
}
if (-not (Test-Path $source)) {
    Write-Host "data directory not found: $source"
    exit 1
}

function Get-Snapshots([string]$setLabel) {
    if (-not (Test-Path $dest)) { return @() }
    if ($setLabel) { $pattern = "^homebot-$setLabel-\d{8}-\d{6}\.zip$" }
    else           { $pattern = '^homebot-\d{8}-\d{6}\.zip$' }
    @(Get-ChildItem -Path $dest -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match $pattern } |
        Sort-Object LastWriteTime -Descending)
}

if ($List) {
    $rows = @()
    foreach ($set in @('', 'preupdate', 'prerestore')) {
        $setName = if ($set) { $set } else { 'daily' }
        foreach ($f in Get-Snapshots $set) {
            $rows += [pscustomobject]@{
                Set     = $setName
                Name    = $f.Name
                MB      = [math]::Round($f.Length / 1MB, 1)
                Created = $f.LastWriteTime
            }
        }
    }
    if ($rows.Count -eq 0) { Write-Host "no snapshots yet in $dest" }
    else { $rows | Sort-Object Created -Descending | Format-Table -AutoSize }
    if (Test-Path $dest) {
        $total = (Get-ChildItem -Path $dest -File | Measure-Object Length -Sum).Sum
        Write-Host ("folder {0}: {1:N1} MB total" -f $dest, ($total / 1MB))
    }
    exit 0
}

New-Item -ItemType Directory -Force -Path $dest | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
if ($Label) { $name = "homebot-$Label-$stamp.zip" } else { $name = "homebot-$stamp.zip" }
$zip     = Join-Path $dest $name
$setName = if ($Label) { $Label } else { 'daily' }

# 全新安装的数据目录可以很小（只有 config.json，workspace 还没生成），所以校验
# 只看结构而不看体积：能打开、含 config.json、且（如果源里有 workspace）含 workspace\ 内容。
$needsWorkspace = Test-Path (Join-Path $source 'workspace')

$staging = Join-Path $env:TEMP "homebot-backup-$stamp"
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Force -Path $staging | Out-Null

# robocopy 复制到文件时返回 1，那属于成功；它的退出码刻意忽略，因为下面会校验压缩包本身。
robocopy $source $staging /E /XD (Join-Path $source 'backups') (Join-Path $source 'workspace\browser') /NFL /NDL /NJH /NJS /NP | Out-Null
Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $zip -Force
Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue

# 校验压缩包真的带上了两样无法凭空重建的东西：配置（API Key、音频设备）与用户数据。
$fail = $null
if (-not (Test-Path $zip)) {
    $fail = 'archive was not created'
} else {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    try {
        $z = [System.IO.Compression.ZipFile]::OpenRead($zip)
        $entries = @($z.Entries | ForEach-Object { $_.FullName })
        $z.Dispose()
    } catch {
        $entries = @()
        $fail = "archive is unreadable ($($_.Exception.Message))"
    }
    if (-not $fail) {
        if ($entries -notcontains 'config.json') {
            $fail = 'config.json is missing from the archive'
        } elseif ($needsWorkspace -and -not (@($entries | Where-Object { $_ -like 'workspace\*' }).Count)) {
            $fail = 'workspace\ is missing from the archive'
        }
    }
}

if ($fail) {
    Write-Host "backup FAILED: $fail"
    if (Test-Path $zip) { Remove-Item $zip -Force }
    exit 1
}

$sizeMB = (Get-Item $zip).Length / 1MB
Write-Host ("backup -> {0} ({1:N1} MB)" -f $zip, $sizeMB)
if ($sizeMB -lt 5) {
    Write-Host '  note: under 5 MB - normal on a fresh install, worth a look on a mature one'
}

$removed = 0
foreach ($old in @(Get-Snapshots $Label | Select-Object -Skip $Keep)) {
    Remove-Item $old.FullName -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path $old.FullName)) { $removed++ }
}
$kept = @(Get-Snapshots $Label)
Write-Host ("rolling set '{0}': kept {1}/{2}, dropped {3} older" -f $setName, $kept.Count, $Keep, $removed)
exit 0
