#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def load_config(path: Path) -> Tuple[str, str]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
        base_url = config["base_url"].rstrip("/")
        access_token = config["access_token"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as error:
        raise RuntimeError("未找到有效的 Mijia 配置") from error

    if not access_token:
        raise RuntimeError("access_token 未配置")
    if not base_url.startswith(("http://", "https://")):
        raise RuntimeError("base_url 必须是 HTTP(S) 地址")
    return base_url, access_token


def request(base_url: str, access_token: str, path: str, data: Optional[Dict[str, Any]] = None) -> Any:
    body = json.dumps(data).encode() if data is not None else None
    headers = {"Authorization": f"Bearer {access_token}"}
    if body is not None:
        headers["Content-Type"] = "application/json"

    try:
        with urlopen(Request(f"{base_url}{path}", data=body, headers=headers), timeout=15) as response:
            return json.loads(response.read())
    except HTTPError as error:
        if error.code == 401:
            raise RuntimeError("米家网关返回 401：access_token 无效、已撤销或不属于当前服务") from error
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"米家网关返回 HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(f"无法连接米家网关: {error.reason}") from error


def call_service(
    base_url: str,
    access_token: str,
    domain: str,
    service: str,
    entity_ids: List[str],
    data: Optional[Dict[str, Any]] = None,
) -> Any:
    service_data = dict(data or {})
    service_data["entity_id"] = entity_ids if len(entity_ids) > 1 else entity_ids[0]
    return request(base_url, access_token, f"/api/services/{domain}/{service}", service_data)


def batch_call(base_url: str, access_token: str, operations: Any) -> List[Any]:
    if not isinstance(operations, list) or not operations:
        raise RuntimeError("--operations 必须是非空 JSON 数组")

    results = []
    for operation in operations:
        if not isinstance(operation, dict):
            raise RuntimeError("--operations 的每项必须是 JSON 对象")
        domain = operation.get("domain")
        service = operation.get("service")
        entity_id = operation.get("entity_id")
        data = operation.get("data", {})
        if not isinstance(domain, str) or not isinstance(service, str):
            raise RuntimeError("每个操作必须包含 domain 和 service")
        if isinstance(entity_id, str):
            entity_ids = [entity_id]
        elif isinstance(entity_id, list) and all(isinstance(value, str) for value in entity_id):
            entity_ids = entity_id
        else:
            raise RuntimeError("每个操作必须包含 entity_id 字符串或数组")
        if not isinstance(data, dict):
            raise RuntimeError("每个操作的 data 必须是 JSON 对象")
        results.append(call_service(base_url, access_token, domain, service, entity_ids, data))
    return results

def build_skill(states: List[Dict[str, Any]], output_path: Path) -> None:
    controllable_domains = {"light", "switch", "climate", "fan", "cover", "humidifier", "vacuum", "media_player"}
    devices = [
        state
        for state in states
        if state["entity_id"].split(".", 1)[0] in controllable_domains and state["state"] != "unavailable"
    ]
    config_path = output_path.parent / "config.json"
    executor_path = Path(__file__).resolve()

    lines = [
        "---",
        "name: mijia",
        "description: 通过米家控制已配置的家庭灯、空调、浴霸和其他智能设备。当用户要求开关或调节家庭设备时使用。",
        "metadata: {\"homebot\":{\"always\":true,\"requires\":{\"bins\":[\"python3\"]}}}",
        "---",
        "",
        "# 家庭设备控制（已激活）",
        "",
        "本 Skill 已随系统提示完整加载。处理家居控制请求时，直接使用本页的设备表、命令格式与绝对路径；禁止再次调用 `read_file` 读取任何 `SKILL.md`，禁止用 `glob`、`find`、`ls`、`cat`、`grep` 或 `exec` 搜索 Skill、设备、脚本或配置。",
        "",
        "## 执行规则",
        "",
        "1. 对明确的控制请求，直接调用一次 `exec` 执行下方的 `python3 ... driver.py ... call` 或 `batch` 命令。不得先读文件、搜索路径、检查环境、查询状态或解释操作方案。",
        "2. 固定脚本路径和 `--config` 路径均为可直接执行的参数；逐字复制到命令即可。`config.json` 是私有配置，严禁读取、检查、提取或推断其内容。",
        "3. 一个动作使用 `call`；两个及以上动作合并成一个 `batch`。在同一请求中仅允许一次 `exec`，不拆分、重试或预查询。实体 ID 只能取自下方设备表。",
        "4. 调用 `exec` 后必须先检查本轮实际返回结果。只有结果明确包含 `Exit code: 0` 时，才可回复命令已成功执行或已向米家网关成功提交；不得仅因已生成命令、已发起 `exec` 或看见部分输出就声称设备已打开、已关闭或操作已完成。网关成功不等同于已确认设备物理状态。",
        "5. 若未调用 `exec`，或结果为错误、超时、被拦截、缺少退出码或退出码非零，必须说明操作未确认成功并简短转述原因；严禁使用已打开、已关闭、已完成等完成性表述，不重试、不补发命令。`batch` 出现上述结果时不得声称全部完成，需说明前序操作可能已生效、后续操作未确认。",
        "6. 仅当用户明确询问设备当前状态、可用设备或要求刷新设备清单时，才执行一次 `discover`。",
        "",
        "## 服务映射",
        "",
        "- 开灯/开开关/开空调：`turn_on`；关灯/关开关/关空调：`turn_off`。",
        "- 空调设温：`climate.set_temperature`，参数 `--data '{\"temperature\":24}'`。空调模式：`climate.set_hvac_mode`，参数 `--data '{\"hvac_mode\":\"cool\"}'`。",
        "- 组合请求示例：打开客厅空调并调至 24°C，再打开客厅灯，构造一个 `batch`，按顺序使用 `climate.turn_on`、`climate.set_temperature`、`light.turn_on`。",
        "",
        "## 命令模板",
        "",
        "单个动作：",
        "```bash",
        f"python3 {executor_path} --config {config_path} call <domain> <service> --entity-id <entity_id> [--data '<JSON>']",
        "```",
        "",
        "多个动作：",
        "```bash",
        f"python3 {executor_path} --config {config_path} batch --operations '[{{\"domain\":\"light\",\"service\":\"turn_off\",\"entity_id\":\"light.example_one\"}},{{\"domain\":\"climate\",\"service\":\"turn_off\",\"entity_id\":\"climate.example_two\"}}]'",
        "```",
        "",
        "## 已发现的可控设备",
        "",
        "| 名称 | 实体 ID | 当前状态 | 可用操作 |",
        "|---|---|---|---|",
    ]

    for state in devices:
        entity_id = state["entity_id"]
        domain = entity_id.split(".", 1)[0]
        name = state.get("attributes", {}).get("friendly_name") or entity_id
        operations = {
            "light": "开、关；亮度、色温",
            "switch": "开、关",
            "climate": "开、关；模式、温度、风速",
            "fan": "开、关；风速",
            "cover": "打开、关闭、停止",
            "humidifier": "开、关；湿度",
            "vacuum": "启动、暂停、回充",
            "media_player": "播放、暂停、音量",
        }[domain]
        lines.append(f"| {name} | `{entity_id}` | {state['state']} | {operations} |")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="米家设备驱动")
    parser.add_argument("--config", required=True, type=Path, help="包含 base_url 和 access_token 的 JSON 文件")
    subparsers = parser.add_subparsers(dest="command", required=True)

    call_parser = subparsers.add_parser("call", help="控制一个米家设备服务")
    call_parser.add_argument("domain")
    call_parser.add_argument("service")
    call_parser.add_argument("--entity-id", action="append", required=True)
    call_parser.add_argument("--data", default="{}", help="额外服务参数 JSON")

    batch_parser = subparsers.add_parser("batch", help="顺序执行多个米家设备控制")
    batch_parser.add_argument("--operations", required=True, help="操作 JSON 数组")

    discover_parser = subparsers.add_parser("discover", help="列出实体，用于首次配置或新增设备")
    discover_parser.add_argument("--domain", action="append", help="仅显示指定 domain，可重复传入")

    build_parser = subparsers.add_parser("build-skill", help="从已配置设备生成工作区 Mijia SKILL.md")
    build_parser.add_argument("--output", required=True, type=Path, help="生成的 SKILL.md 路径")

    args = parser.parse_args()
    base_url, access_token = load_config(args.config)

    if args.command == "batch":
        try:
            operations = json.loads(args.operations)
        except json.JSONDecodeError as error:
            raise RuntimeError("--operations 必须是 JSON 数组") from error
        print(json.dumps(batch_call(base_url, access_token, operations), ensure_ascii=False, indent=2))
        return

    if args.command == "discover":
        states = request(base_url, access_token, "/api/states")
        if args.domain:
            states = [state for state in states if state["entity_id"].split(".", 1)[0] in args.domain]
        output = [
            {
                "entity_id": state["entity_id"],
                "state": state["state"],
                "friendly_name": state.get("attributes", {}).get("friendly_name"),
            }
            for state in states
        ]
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    if args.command == "build-skill":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        build_skill(request(base_url, access_token, "/api/states"), args.output)
        print(f"已生成 {args.output}")
        return

    try:
        data = json.loads(args.data)
    except json.JSONDecodeError as error:
        raise RuntimeError("--data 必须是 JSON 对象") from error
    if not isinstance(data, dict):
        raise RuntimeError("--data 必须是 JSON 对象")

    data["entity_id"] = args.entity_id if len(args.entity_id) > 1 else args.entity_id[0]
    print(json.dumps(request(base_url, access_token, f"/api/services/{args.domain}/{args.service}", data), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"错误：{error}", file=sys.stderr)
        sys.exit(1)
