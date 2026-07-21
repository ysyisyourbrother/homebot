import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

_DEFAULT_EXECUTABLE_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


_DANDIAN_INSTRUCTIONS = "请用简洁、清晰的纯文本直接回答，避免过度展开说明；不要生成图片、表情或 emoji。"


class OpenCLIError(RuntimeError):
    def __init__(self, detail: str, returncode: int, should_wake_browser: bool = False) -> None:
        super().__init__(detail)
        self.returncode = returncode
        self.should_wake_browser = should_wake_browser


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("必须是正整数")
    return number


def _browser_config() -> tuple[str, Path, str]:
    """Return (executable_path, user_data_dir, profile) from homebot config."""
    config_path = Path.home() / ".homebot" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    browser_cfg = config.get("tools", {}).get("browser", {})
    executable_path = os.environ.get(
        "HOMEBOT_CHROME_BIN", browser_cfg.get("executablePath", _DEFAULT_EXECUTABLE_PATH)
    )
    configured_dir = browser_cfg.get("userDataDir", "")
    profile = browser_cfg.get("profile", "Homebot")
    user_data_dir = (
        Path(configured_dir).expanduser()
        if configured_dir
        else Path.home() / ".homebot" / "workspace" / "browser"
    )
    return executable_path, user_data_dir, profile


def browser_executable_path() -> str:
    return _browser_config()[0]


def browser_data_dir() -> Path:
    return _browser_config()[1]


def browser_profile() -> str:
    return _browser_config()[2]


def wake_homebot_chrome() -> None:
    subprocess.Popen(
        [
            browser_executable_path(),
            f"--user-data-dir={browser_data_dir()}",
            f"--profile-directory={browser_profile()}",
            "--no-startup-window",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def close_homebot_chrome() -> None:
    user_data_arg = f"--user-data-dir={browser_data_dir()}"
    profile_arg = f"--profile-directory={browser_profile()}"
    result = subprocess.run(
        ["pgrep", "-f", f"^{browser_executable_path()} .*{user_data_arg}.*{profile_arg}"],
        capture_output=True,
        text=True,
    )
    pids = [int(pid) for pid in result.stdout.split()]
    for pid in pids:
        os.kill(pid, 15)
    for _ in range(20):
        alive = []
        for pid in pids:
            try:
                os.kill(pid, 0)
                alive.append(pid)
            except ProcessLookupError:
                pass
        if not alive:
            break
        time.sleep(0.05)


def opencli(command: list[str], env: dict[str, str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, env=env)
    except FileNotFoundError as error:
        raise OpenCLIError("未找到 opencli，请先安装并确保它在 PATH 中。", 1) from error

    if result.returncode == 0:
        return result.stdout

    detail = result.stderr.strip() or result.stdout.strip() or "OpenCLI 调用失败"
    should_wake_browser = "BROWSER_CONNECT" in detail
    if should_wake_browser or "profile_disconnected" in detail:
        detail = "小红书浏览器未连接，请确认 Homebot 专用 Google Chrome 中的 OpenCLI 扩展已启用。"
    raise OpenCLIError(detail, result.returncode or 1, should_wake_browser)


def run_with_browser(command: list[str], env: dict[str, str]) -> str:
    try:
        return opencli(command, env)
    except OpenCLIError as error:
        if not error.should_wake_browser:
            raise
        wake_homebot_chrome()
        return opencli(command, env)


def search_results(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("results", "items", "data", "notes"):
            items = payload.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
    raise RuntimeError("OpenCLI 搜索结果格式异常，未找到笔记列表。")


def note_url(result: dict[str, object]) -> str:
    for key in ("url", "note_url", "link"):
        value = result.get(key)
        if isinstance(value, str) and value:
            return value
    raise RuntimeError("OpenCLI 搜索结果缺少笔记 URL，无法读取正文。")


def run_search(query: str, limit: int) -> int:
    env = os.environ.copy()
    env["OPENCLI_BROWSER_CONNECT_TIMEOUT"] = "10"
    notes = []
    try:
        wake_homebot_chrome()
        results = search_results(
            json.loads(
                run_with_browser(
                    ["opencli", "xiaohongshu", "search", query, "--limit", str(limit), "-f", "json"],
                    env,
                )
            )
        )
        for index, result in enumerate(results[:limit], start=1):
            content = json.loads(
                run_with_browser(
                    ["opencli", "xiaohongshu", "note", note_url(result), "-f", "json"],
                    env,
                )
            )
            notes.append({"search": result, "content": content})
        json.dump({"query": query, "notes": notes}, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0
    except OpenCLIError as error:
        print(error, file=sys.stderr)
        return error.returncode
    except (json.JSONDecodeError, RuntimeError) as error:
        print(error, file=sys.stderr)
        return 1
    finally:
        close_homebot_chrome()


def run_opencli(command: list[str]) -> int:
    env = os.environ.copy()
    env["OPENCLI_BROWSER_CONNECT_TIMEOUT"] = "10"
    try:
        wake_homebot_chrome()
        sys.stdout.write(run_with_browser(command, env))
        return 0
    except OpenCLIError as error:
        print(error, file=sys.stderr)
        return error.returncode
    finally:
        close_homebot_chrome()


def main() -> int:
    parser = argparse.ArgumentParser(description="通过 OpenCLI 查询小红书")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="搜索小红书笔记")
    search_parser.add_argument("query", help="搜索关键词")
    search_parser.add_argument("--limit", type=positive_int, default=1, help="读取并汇总的笔记数量，默认 1")

    ask_parser = subparsers.add_parser("ask", help="向小红书点点提问")
    ask_parser.add_argument("question", help="要问点点的问题")
    ask_parser.add_argument("--timeout", type=positive_int, default=90, help="等待回答的秒数，默认 90")
    ask_parser.add_argument("--source-limit", type=positive_int, default=10, help="最多返回的来源数，默认 10")

    args = parser.parse_args()
    if args.command == "search":
        return run_search(args.query, args.limit)

    command = [
        "opencli",
        "xiaohongshu",
        "ask",
        f"{args.question}\n\n{_DANDIAN_INSTRUCTIONS}",
        "--timeout",
        str(args.timeout),
        "--source-limit",
        str(args.source_limit),
        "-f",
        "json",
    ]
    return run_opencli(command)


if __name__ == "__main__":
    sys.exit(main())
