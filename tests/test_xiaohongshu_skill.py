import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from homebot.agent.context import ContextBuilder
SCRIPT = Path(__file__).parents[1] / "homebot" / "skills" / "xiaohongshu" / "scripts" / "xiaohongshu.py"
SKILL = SCRIPT.parents[1] / "SKILL.md"


class XiaohongshuSkillTest(unittest.TestCase):
    def test_skill_prompt_uses_only_listed_absolute_path(self) -> None:
        workspace = Path("/tmp/homebot-workspace")
        builtin_skills = Path(__file__).parents[1] / "homebot" / "skills"

        with patch("homebot.agent.skills.BUILTIN_SKILLS_DIR", builtin_skills):
            prompt = ContextBuilder(workspace).build_system_prompt()

        self.assertIn("只能用 read_file 工具读取下方该技能列出的绝对路径", prompt)
        self.assertIn("不要再次读取该文件、猜测其他路径，或用 exec 重复读取", prompt)
        self.assertNotIn("/skills/{skill-name}/SKILL.md", prompt)

    def test_skill_uses_default_opencli_context_without_browsertool(self) -> None:
        content = SKILL.read_text(encoding="utf-8")

        self.assertIn("脚本直接使用 OpenCLI default context", content)
        self.assertNotIn("opencli --profile homebot", content)
        self.assertIn("正常流程不要调用 Homebot `browser` 工具", content)
        self.assertNotIn("用 `browser` 工具 `open`", content)

    def run_skill(
        self,
        *args: str,
        exit_code: int = 0,
        stderr: str = "Browser Bridge 未连接",
    ) -> tuple[subprocess.CompletedProcess[str], list[str]]:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            argv_path = temp_path / "argv.json"
            fake_opencli = temp_path / "opencli"
            fake_opencli.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "Path(os.environ['FAKE_OPENCLI_ARGV']).write_text(json.dumps(sys.argv[1:], ensure_ascii=False))\n"
                "code = int(os.environ.get('FAKE_OPENCLI_EXIT', '0'))\n"
                "if code:\n"
                "    print(os.environ['FAKE_OPENCLI_STDERR'], file=sys.stderr)\n"
                "else:\n"
                "    command = sys.argv[1:3]\n"
                "    output = os.environ['FAKE_OPENCLI_SEARCH_OUTPUT'] if command == ['xiaohongshu', 'search'] else os.environ['FAKE_OPENCLI_NOTE_OUTPUT'] if command == ['xiaohongshu', 'note'] else os.environ['FAKE_OPENCLI_OUTPUT']\n"
                "    print(output)\n"
                "sys.exit(code)\n",
                encoding="utf-8",
            )
            fake_opencli.chmod(fake_opencli.stat().st_mode | stat.S_IXUSR)
            fake_chrome = temp_path / "chrome"
            fake_chrome.write_text("#!/bin/sh\n", encoding="utf-8")
            fake_chrome.chmod(fake_chrome.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{temp_dir}{os.pathsep}{env['PATH']}",
                    "HOMEBOT_CHROME_BIN": str(fake_chrome),
                    "FAKE_OPENCLI_ARGV": str(argv_path),
                    "FAKE_OPENCLI_EXIT": str(exit_code),
                    "FAKE_OPENCLI_OUTPUT": '{"answer":"测试结果"}',
                    "FAKE_OPENCLI_SEARCH_OUTPUT": '[{"title":"广州早茶","url":"https://www.xiaohongshu.com/search_result/note?xsec_token=test"}]',
                    "FAKE_OPENCLI_NOTE_OUTPUT": '[{"field":"content","value":"测试正文"}]',
                    "FAKE_OPENCLI_STDERR": stderr,
                }
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), *args],
                capture_output=True,
                text=True,
                env=env,
            )
            argv = json.loads(argv_path.read_text(encoding="utf-8")) if argv_path.exists() else []
            return result, argv

    def test_search_forwards_arguments_and_output(self) -> None:
        result, argv = self.run_skill("search", "广州早茶", "--limit", "5")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "query": "广州早茶",
                "notes": [
                    {
                        "search": {
                            "title": "广州早茶",
                            "url": "https://www.xiaohongshu.com/search_result/note?xsec_token=test",
                        },
                        "content": [{"field": "content", "value": "测试正文"}],
                    }
                ],
            },
        )
        self.assertEqual(
            argv,
            [
                "xiaohongshu",
                "note",
                "https://www.xiaohongshu.com/search_result/note?xsec_token=test",
                "-f",
                "json",
            ],
        )

    def test_ask_forwards_arguments_and_output(self) -> None:
        result, argv = self.run_skill(
            "ask",
            "广州周末适合去哪里？",
            "--timeout",
            "60",
            "--source-limit",
            "3",
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '{"answer":"测试结果"}\n')
        self.assertEqual(
            argv,
            [
                "xiaohongshu",
                "ask",
                "广州周末适合去哪里？\n\n请用简洁、清晰的纯文本直接回答，避免过度展开说明；不要生成图片、表情或 emoji。",
                "--timeout",
                "60",
                "--source-limit",
                "3",
                "-f",
                "json",
            ],
        )

    def test_profile_cannot_be_overridden(self) -> None:
        result, argv = self.run_skill("--profile", "family", "search", "露营")

        self.assertEqual(result.returncode, 2)
        self.assertEqual(argv, [])
        self.assertIn("invalid choice", result.stderr)

    def test_opencli_error_is_propagated(self) -> None:
        result, _ = self.run_skill("search", "露营", exit_code=7)

        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, "")
        self.assertIn("Browser Bridge 未连接", result.stderr)

    def test_profile_disconnected_has_actionable_error(self) -> None:
        result, _ = self.run_skill(
            "ask",
            "怎么露营？",
            exit_code=7,
            stderr="profile_disconnected: Browser profile is unavailable",
        )

        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, "")
        self.assertIn("小红书浏览器未连接，请确认 Homebot 专用 Google Chrome 中的 OpenCLI 扩展已启用。", result.stderr)

    def test_browser_connect_starts_homebot_chrome_without_extra_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            count_path = temp_path / "count.txt"
            chrome_argv_path = temp_path / "chrome-argv.json"
            fake_opencli = temp_path / "opencli"
            fake_opencli.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys, time\n"
                "from pathlib import Path\n"
                "path = Path(os.environ['FAKE_OPENCLI_COUNT'])\n"
                "count = int(path.read_text()) + 1 if path.exists() else 1\n"
                "path.write_text(str(count))\n"
                "if count == 1:\n"
                "    print('code: BROWSER_CONNECT', file=sys.stderr)\n"
                "    sys.exit(69)\n"
                "chrome_path = Path(os.environ['FAKE_CHROME_ARGV'])\n"
                "for _ in range(50):\n"
                "    if chrome_path.exists():\n"
                "        break\n"
                "    time.sleep(0.01)\n"
                "if sys.argv[2] == 'search':\n"
                "    print('[{\"title\":\"潮州\",\"url\":\"https://www.xiaohongshu.com/search_result/note?xsec_token=test\"}]')\n"
                "else:\n"
                "    print('[{\"field\":\"content\",\"value\":\"测试正文\"}]')\n",
                encoding="utf-8",
            )
            fake_opencli.chmod(fake_opencli.stat().st_mode | stat.S_IXUSR)
            fake_chrome = temp_path / "chrome"
            fake_chrome.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "Path(os.environ['FAKE_CHROME_ARGV']).write_text(json.dumps(sys.argv[1:]))\n",
                encoding="utf-8",
            )
            fake_chrome.chmod(fake_chrome.stat().st_mode | stat.S_IXUSR)
            fake_pgrep = temp_path / "pgrep"
            fake_pgrep.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            fake_pgrep.chmod(fake_pgrep.stat().st_mode | stat.S_IXUSR)
            env = os.environ.copy()
            env.update(
                {
                    "HOME": temp_dir,
                    "PATH": f"{temp_dir}{os.pathsep}{env['PATH']}",
                    "HOMEBOT_CHROME_BIN": str(fake_chrome),
                    "FAKE_OPENCLI_COUNT": str(count_path),
                    "FAKE_CHROME_ARGV": str(chrome_argv_path),
                }
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "search", "潮州", "--limit", "1"],
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(count_path.read_text(), "3")
            chrome_argv = json.loads(chrome_argv_path.read_text())
            self.assertEqual(len(chrome_argv), 3)
            self.assertTrue(chrome_argv[0].endswith("/.homebot/workspace/browser"))
            self.assertEqual(chrome_argv[1], "--profile-directory=Homebot")
            self.assertEqual(chrome_argv[2], "--no-startup-window")
            self.assertNotIn("https://www.xiaohongshu.com/", chrome_argv)
            self.assertNotIn("about:blank", chrome_argv)

    def test_non_positive_values_are_rejected_before_opencli(self) -> None:
        for args in (
            ("search", "露营", "--limit", "0"),
            ("ask", "怎么露营？", "--timeout", "0"),
            ("ask", "怎么露营？", "--source-limit", "-1"),
        ):
            with self.subTest(args=args):
                result, argv = self.run_skill(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(argv, [])
                self.assertIn("必须是正整数", result.stderr)


if __name__ == "__main__":
    unittest.main()
