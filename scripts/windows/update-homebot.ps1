<#
.SYNOPSIS
    从 GitHub 更新源码安装的 homebot（origin/main），顺序保证可回滚。

.DESCRIPTION
    顺序是刻意的：数据快照先落盘并校验通过，才动工作区，所以任何坏版本都有退路。

      1/6 工作区不干净则直接停下（部署机只部署，不该有本地改动）
      2/6 强制快照 ~/.homebot → 滚动集合 preupdate（写失败就不动代码）
      3/6 记录当前提交号 → git fetch + git pull --ff-only
      4/6 pip install -e 刷新依赖（捕捉依赖变化）
      5/6 重启网关并轮询 /health
      6/6 不健康：打印精确的回滚命令并以退出码 1 结束

    全程只读数据、只写备份，不会删除数据目录里的任何文件。

.PARAMETER RepoRoot
    homebot 源码目录，默认取本脚本上两级目录。

.PARAMETER DataDir
    数据目录，默认 $env:USERPROFILE\.homebot。

.PARAMETER TaskName
    托管网关的计划任务名，默认 homebot-Gateway。

.PARAMETER HealthUrl
    健康检查地址，默认 http://127.0.0.1:18790/health。

.PARAMETER Proxy
    可选，git 与 pip 使用的 HTTP/HTTPS 代理，例如 http://127.0.0.1:7890。
    只有在需要时才设置环境变量；省略则沿用系统/环境里已有的代理。

.PARAMETER PipIndexUrl
    可选，pip 的 --index-url，用于局域网镜像源。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\windows\update-homebot.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\windows\update-homebot.ps1 -Proxy http://127.0.0.1:7890
#>
[CmdletBinding()]
param(
    # 空值表示"取本脚本上两级目录"。注意不能在 param 默认值里用 $PSScriptRoot：
    # 带 [CmdletBinding()] 的脚本在绑定参数时 $PSScriptRoot 还是空的（PowerShell 5.1 实测）。
    [string]$RepoRoot = '',
    [string]$DataDir = (Join-Path $env:USERPROFILE '.homebot'),
    [string]$TaskName = 'homebot-Gateway',
    [string]$HealthUrl = 'http://127.0.0.1:18790/health',
    [string]$Proxy = '',
    [string]$PipIndexUrl = '',
    [int]$Keep = 3
)

$ErrorActionPreference = 'Stop'

if (-not $RepoRoot) { $RepoRoot = Join-Path $PSScriptRoot '..\..' }
$repo   = (Resolve-Path $RepoRoot).Path
$backup = Join-Path $PSScriptRoot 'backup-homebot.ps1'
$restart = Join-Path $PSScriptRoot 'restart-homebot.ps1'
$python = Join-Path $repo '.venv\Scripts\python.exe'

function Fail([string]$message) {
    Write-Host ''
    Write-Host "STOPPED: $message" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path (Join-Path $repo '.git'))) { Fail "not a git checkout: $repo" }
if (-not (Test-Path $python)) { Fail "virtual environment not found: $python (create it first, see the deployment guide)" }

if ($Proxy) {
    $env:HTTP_PROXY  = $Proxy
    $env:HTTPS_PROXY = $Proxy
}

Write-Host '=== 1/6 working tree ==='
& git -C $repo status --short --branch
if ((& git -C $repo status --porcelain)) {
    Fail 'the working tree is dirty - this machine only deploys, so discard the local changes before updating'
}
$before = (& git -C $repo rev-parse HEAD).Trim()
Write-Host "  now at: $before"

Write-Host '=== 2/6 data snapshot (mandatory) ==='
& powershell -NoProfile -ExecutionPolicy Bypass -File $backup -DataDir $DataDir -Label 'preupdate' -Keep $Keep
if ($LASTEXITCODE -ne 0) { Fail 'the backup failed, so nothing was changed - fix the backup first' }
$snap = Get-ChildItem -Path (Join-Path $DataDir 'backups') -File |
    Where-Object { $_.Name -match '^homebot-preupdate-\d{8}-\d{6}\.zip$' } |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $snap) { Fail 'the snapshot that was just written could not be found' }
Write-Host ("  restore point: {0} ({1:N1} MB)" -f $snap.FullName, ($snap.Length / 1MB))

Write-Host '=== 3/6 fetch + pull ==='
& git -C $repo fetch origin --prune
if ($LASTEXITCODE -ne 0) { Fail "fetch failed - still at $before, nothing was changed" }
& git -C $repo pull --ff-only
if ($LASTEXITCODE -ne 0) {
    Fail "the pull was not a fast-forward - still at $before, nothing was changed (the snapshot above can simply rotate out)"
}
$after = (& git -C $repo rev-parse HEAD).Trim()
& git -C $repo log -1 --pretty='  now at %h %ad %s' --date=short
if ($after -eq $before) { Write-Host '  no new commits - refreshing the install and restarting anyway' }
else { Write-Host "  $before -> $after" }

Write-Host '=== 4/6 reinstall package (picks up dependency changes) ==='
$pipArgs = @('-m', 'pip', 'install', '-q', '-e', $repo)
if ($PipIndexUrl) { $pipArgs += @('--index-url', $PipIndexUrl) }
& $python @pipArgs
if ($LASTEXITCODE -ne 0) { Fail 'pip install failed - the gateway has NOT been restarted yet' }
Write-Host '  done'

Write-Host '=== 5/6 restart the gateway ==='
& powershell -NoProfile -ExecutionPolicy Bypass -File $restart -TaskName $TaskName -HealthUrl $HealthUrl -DataDir $DataDir
if ($LASTEXITCODE -eq 0) {
    Write-Host ''
    Write-Host "update finished: $before -> $after" -ForegroundColor Green
    exit 0
}

Write-Host ''
Write-Host '=== 6/6 the new revision is NOT healthy ===' -ForegroundColor Yellow
Write-Host '  last log lines:'
Get-Content (Join-Path $DataDir 'logs\gateway.log') -Tail 20 -Encoding UTF8 -ErrorAction SilentlyContinue |
    ForEach-Object { Write-Host "    $_" }
Write-Host ''
Write-Host 'roll the code back with:'
Write-Host "  git -C $repo reset --hard $before"
Write-Host "  powershell -ExecutionPolicy Bypass -File $restart -TaskName $TaskName"
Write-Host ''
Write-Host 'only if the data itself was damaged, restore the snapshot (this stops the gateway first):'
Write-Host "  powershell -ExecutionPolicy Bypass -File $(Join-Path $PSScriptRoot 'restore-homebot.ps1') -DataDir `"$DataDir`" -Archive `"$($snap.FullName)`""
exit 1
