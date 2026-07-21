import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from homebot.skills.mijia import driver


class MijiaDriverTest(unittest.TestCase):
    def test_batch_call_sends_each_operation_once(self) -> None:
        operations = [
            {"domain": "light", "service": "turn_off", "entity_id": "light.living_room"},
            {"domain": "climate", "service": "turn_off", "entity_id": "climate.bedroom"},
        ]

        with patch("homebot.skills.mijia.driver.call_service", return_value={"ok": True}) as call_service:
            result = driver.batch_call("http://localhost:8123", "token", operations)

        self.assertEqual(result, [{"ok": True}, {"ok": True}])
        self.assertEqual(
            call_service.call_args_list,
            [
                (("http://localhost:8123", "token", "light", "turn_off", ["light.living_room"], {}),),
                (("http://localhost:8123", "token", "climate", "turn_off", ["climate.bedroom"], {}),),
            ],
        )

    def test_build_skill_limits_daily_control_to_one_cli_command(self) -> None:
        states = [
            {
                "entity_id": "light.living_room",
                "state": "on",
                "attributes": {"friendly_name": "客厅灯"},
            },
            {
                "entity_id": "climate.bedroom",
                "state": "off",
                "attributes": {"friendly_name": "主卧空调"},
            },
            {"entity_id": "sensor.temperature", "state": "26", "attributes": {}},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "mijia" / "SKILL.md"
            output.parent.mkdir()
            driver.build_skill(states, output)
            content = output.read_text(encoding="utf-8")

        self.assertIn("\"always\":true", content)
        self.assertIn("本 Skill 已随系统提示完整加载", content)
        self.assertIn("禁止再次调用 `read_file`", content)
        self.assertIn("`glob`、`find`、`ls`、`cat`、`grep`", content)
        self.assertIn("直接调用一次 `exec`", content)
        self.assertIn("固定脚本路径和 `--config` 路径均为可直接执行的参数", content)
        self.assertIn("一个动作使用 `call`；两个及以上动作合并成一个 `batch`", content)
        self.assertIn("调用 `exec` 后必须先检查本轮实际返回结果", content)
        self.assertIn("`Exit code: 0`", content)
        self.assertIn("严禁使用已打开、已关闭、已完成等完成性表述", content)
        self.assertIn("前序操作可能已生效、后续操作未确认", content)
        self.assertIn("不重试、不补发命令", content)
        self.assertIn("`climate.set_temperature`", content)
        self.assertIn("driver.py", content)
        self.assertIn("多个动作", content)
        self.assertIn("`light.living_room`", content)
        self.assertIn("`climate.bedroom`", content)
        self.assertNotIn("sensor.temperature", content)
        self.assertNotIn("### 已生成的直接命令", content)
        self.assertEqual(content.count("```bash"), 2)

    def test_batch_command_prints_json(self) -> None:
        operations = [{"domain": "light", "service": "turn_off", "entity_id": "light.living_room"}]

        with patch("homebot.skills.mijia.driver.load_config", return_value=("http://localhost", "token")), patch(
            "homebot.skills.mijia.driver.batch_call", return_value=[{"ok": True}]
        ), patch("sys.argv", ["driver.py", "--config", "config.json", "batch", "--operations", json.dumps(operations)]), patch(
            "builtins.print"
        ) as print_mock:
            driver.main()

        self.assertEqual(json.loads(print_mock.call_args.args[0]), [{"ok": True}])


if __name__ == "__main__":
    unittest.main()
