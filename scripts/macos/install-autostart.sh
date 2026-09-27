#!/usr/bin/env bash
#
# 把 homebot 网关注册成 macOS 登录自启服务（launchd LaunchAgent）。
#
# 与 Windows 版（scripts/windows/install-autostart.ps1）共享同一套契约：
#   * 启动脚本：$HOME/.homebot/run-gateway.sh（自看护循环，进程退出后 10 秒重启）
#   * 日志：$HOME/.homebot/logs/gateway.log（超过 10 MB 轮转为 gateway.log.1）
#   * 卸载：install-autostart.sh --uninstall
#
# 不共享实现：Windows 用计划任务，macOS 用 launchd —— 这正是"契约共享、
# 实现分离"的落点，改一边不会影响另一边。
#
# 用法（仓库根目录执行，加不加 chmod +x 都行）：
#     bash scripts/macos/install-autostart.sh
#     bash scripts/macos/install-autostart.sh --uninstall

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LABEL="com.homebot.gateway"
DATA_DIR="$HOME/.homebot"
LAUNCHER="$DATA_DIR/run-gateway.sh"
LOG_DIR="$DATA_DIR/logs"
LOG_FILE="$LOG_DIR/gateway.log"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PYTHON="$REPO_ROOT/.venv/bin/python"

if [[ "${1:-}" == "--uninstall" ]]; then
  launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST" "$LAUNCHER"
  echo "已移除 launchd 服务 $LABEL 与启动脚本。"
  echo "日志与数据保留在 $DATA_DIR"
  exit 0
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "找不到虚拟环境解释器：$PYTHON" >&2
  echo "请先在仓库目录执行：" >&2
  echo "    python3 -m venv .venv" >&2
  echo "    .venv/bin/python -m pip install -e ." >&2
  exit 1
fi

mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"

# 启动脚本：写日志 + 自看护循环（与 Windows 版行为一致）
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
# 由 scripts/macos/install-autostart.sh 生成；改这里不如改那个脚本。
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
LOG_DIR="$LOG_DIR"
LOG_FILE="$LOG_FILE"
mkdir -p "\$LOG_DIR"
cd "$REPO_ROOT"
while true; do
  if [[ -f "\$LOG_FILE" && \$(wc -c < "\$LOG_FILE") -gt 10485760 ]]; then
    mv -f "\$LOG_FILE" "\$LOG_FILE.1"
  fi
  printf '\n===== %s starting =====\n' "\$(date '+%Y-%m-%d_%H:%M:%S')" >> "\$LOG_FILE"
  "$PYTHON" -u -m homebot gateway >> "\$LOG_FILE" 2>&1
  rc=\$?
  printf '===== %s exited with code %s, restarting in 10s =====\n' \\
    "\$(date '+%Y-%m-%d_%H:%M:%S')" "\$rc" >> "\$LOG_FILE"
  sleep 10
done
EOF
chmod +x "$LAUNCHER"

# launchd 只负责"登录时启动 + 挂了再拉起"，具体重启节奏交给上面的循环
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$LAUNCHER</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOG_FILE</string>
  <key>StandardErrorPath</key><string>$LOG_FILE</string>
  <key>ProcessType</key><string>Interactive</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$PLIST" || launchctl load "$PLIST"

echo "已注册 launchd 服务 $LABEL"
echo "  启动脚本：$LAUNCHER"
echo "  日志：$LOG_FILE"
echo "  健康检查：http://127.0.0.1:18790/health"
echo "  卸载：bash scripts/macos/install-autostart.sh --uninstall"
