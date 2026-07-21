import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

from homebot.cli.config import (
    _configure_kws_settings,
    _configure_mijia,
    _configure_skills,
    _configure_tools,
    _configure_voice,
    _configure_voice_audio_devices,
    _configure_user_recognition,
    _discover_speaker_profiles,
    _finalize_voice_config,
    _generate_keywords_via_llm,
    _save_config,
)
from homebot.config.schema import Config


class VoiceAudioDevicesCliTest(unittest.TestCase):
    def test_selects_input_and_output_devices(self) -> None:
        section = {}
        devices = [
            {"name": "Built-in Microphone", "max_input_channels": 1, "max_output_channels": 0},
            {"name": "USB Speaker", "max_input_channels": 1, "max_output_channels": 2},
            {"name": "Built-in Speaker", "max_input_channels": 0, "max_output_channels": 2},
        ]

        with (
            patch("sounddevice.query_devices", return_value=devices),
            patch("builtins.input", side_effect=["2", "1"]),
        ):
            _configure_voice_audio_devices(section)

        self.assertEqual(section["inputDevice"], "USB Speaker")
        self.assertEqual(section["outputDevice"], "USB Speaker")

    def test_selects_system_default_devices(self) -> None:
        section = {"inputDevice": "USB Microphone", "outputDevice": "USB Speaker"}
        devices = [{"name": "USB Device", "max_input_channels": 1, "max_output_channels": 2}]

        with (
            patch("sounddevice.query_devices", return_value=devices),
            patch("builtins.input", side_effect=["0", "0"]),
        ):
            _configure_voice_audio_devices(section)

        self.assertEqual(section["inputDevice"], "")
        self.assertEqual(section["outputDevice"], "")


    def test_configures_browser_session_refresh(self) -> None:
        config = Config()
        answers = iter([
            "",       # Web Fetch enable
            "",       # Web Search enable
            "",       # Shell Exec enable
            "yes",    # Browser enable
            "",       # Browser executable path (keep default)
            "",       # User Data Directory (keep default)
            "",       # Browser profile (keep default "Homebot")
            "https://y.qq.com/, https://www.xiaohongshu.com/",  # Session refresh URLs
            "48",     # Session refresh interval hours
        ])

        with patch("builtins.input", side_effect=lambda _prompt: next(answers)):
            _configure_tools(config)

        self.assertTrue(config.tools.browser.enable)
        self.assertEqual(config.tools.browser.executable_path, "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        self.assertEqual(config.tools.browser.user_data_dir, str(Path.home() / ".homebot" / "workspace" / "browser"))
        self.assertEqual(config.tools.browser.profile, "Homebot")
        self.assertEqual(
            config.tools.browser.session_refresh.urls,
            ["https://y.qq.com/", "https://www.xiaohongshu.com/"],
        )
        self.assertEqual(config.tools.browser.session_refresh.interval_hours, 48)

    def test_clears_browser_session_refresh_urls(self) -> None:
        config = Config()
        config.tools.browser.session_refresh.urls = ["https://y.qq.com/"]
        answers = iter(["", "", "", "", "", "", "", "none", ""])

        with patch("builtins.input", side_effect=lambda _prompt: next(answers)):
            _configure_tools(config)

        self.assertEqual(config.tools.browser.session_refresh.urls, [])
        self.assertEqual(config.tools.browser.session_refresh.interval_hours, 72)

    def test_configures_mijia_in_workspace_and_refreshes_skill(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch("builtins.input", side_effect=["http://mijia.local:8123", "test-token"]), patch(
            "homebot.skills.mijia.driver.request", return_value=[]
        ) as request_mock:
            _configure_mijia(Path(temp_dir))

            skill_dir = Path(temp_dir) / "skills" / "mijia"
            self.assertEqual(
                json.loads((skill_dir / "config.json").read_text(encoding="utf-8")),
                {"base_url": "http://mijia.local:8123", "access_token": "test-token"},
            )
            self.assertTrue((skill_dir / "SKILL.md").exists())

        request_mock.assert_called_once_with("http://mijia.local:8123", "test-token", "/api/states")

    def test_skills_menu_opens_mijia_configuration(self) -> None:
        with patch("homebot.cli.config._configure_mijia") as configure_mijia, patch(
            "builtins.input", side_effect=["1", "0"]
        ):
            _configure_skills(Path("/tmp/workspace"))

        configure_mijia.assert_called_once_with(Path("/tmp/workspace"))

    def test_enabling_voice_downloads_model_and_saves_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            voice_dir = Path(temp_dir) / "voice"
            config = Config()
            config.channels.voice = {"voiceDir": str(voice_dir)}

            with (
                patch("homebot.cli.config._download_kws_model", return_value=True) as download_model,
                patch("homebot.cli.config._sync_voice_assets"),
                patch("homebot.cli.config.save_config") as save,
                patch("homebot.utils.helpers.sync_workspace_templates"),
                patch("builtins.input", side_effect=["1", "", "", "", "", "", "", "0"]),
            ):
                _configure_voice(config)

            self.assertTrue(config.channels.voice["enabled"])
            download_model.assert_called_once_with(voice_dir.resolve())
            save.assert_called_once_with(config)

    def test_finalize_rejects_missing_model_without_downloading(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            voice_dir = Path(temp_dir) / "voice"
            config = Config()
            config.channels.voice = {
                "enabled": True,
                "voiceDir": str(voice_dir),
                "wakeWords": [],
            }

            with patch("homebot.cli.config._download_kws_model") as download_model:
                self.assertFalse(_finalize_voice_config(config))

            download_model.assert_not_called()

    def test_save_is_blocked_when_required_model_is_not_downloaded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config()
            config.channels.voice = {
                "enabled": True,
                "voiceDir": str(Path(temp_dir) / "voice"),
                "wakeWords": [],
            }

            with (
                patch("homebot.cli.config._download_kws_model", return_value=False),
                patch("homebot.cli.config.save_config") as save,
                patch("builtins.input", return_value="yes"),
            ):
                self.assertFalse(_save_config(config, prepare_voice=True))

            save.assert_not_called()

    def test_save_generates_keywords_after_voice_setup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            voice_dir = Path(temp_dir) / "voice"
            (voice_dir / "model" / "sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20").mkdir(parents=True)
            config = Config()
            config.providers.deepseek.api_key = "test-key"
            config.providers.deepseek.api_base = "https://api.example.test/v1"
            config.channels.voice = {
                "enabled": True,
                "voiceDir": str(voice_dir),
                "wakeWords": ["大虾米"],
            }

            with (
                patch("homebot.cli.config._sync_voice_assets", return_value=[]),
                patch("homebot.cli.config._generate_keywords_via_llm", return_value=True) as generate_keywords,
                patch("homebot.cli.config.save_config") as save,
                patch("homebot.utils.helpers.sync_workspace_templates"),
            ):
                self.assertTrue(_save_config(config, prepare_voice=True))

            generate_keywords.assert_called_once()
            save.assert_called_once_with(config)

    def test_changed_wake_words_regenerates_existing_keywords(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            voice_dir = Path(temp_dir) / "voice"
            (voice_dir / "model" / "sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20").mkdir(parents=True)
            (voice_dir / "keywords.txt").write_text("old keywords\n", encoding="utf-8")
            config = Config()
            config.providers.deepseek.api_key = "test-key"
            config.providers.deepseek.api_base = "https://api.example.test/v1"
            config.channels.voice = {
                "enabled": True,
                "voiceDir": str(voice_dir),
                "wakeWords": ["小助手"],
            }
            previous_voice = {"enabled": True, "wakeWords": ["大虾米"]}

            with (
                patch("homebot.cli.config._sync_voice_assets", return_value=[]),
                patch("homebot.cli.config._generate_keywords_via_llm", return_value=True) as generate_keywords,
                patch("homebot.cli.config.save_config"),
                patch("homebot.utils.helpers.sync_workspace_templates"),
            ):
                self.assertTrue(
                    _save_config(
                        config,
                        prepare_voice=True,
                        previous_voice_section=previous_voice,
                    )
                )

            self.assertTrue(generate_keywords.call_args.kwargs["force"])

    def test_unchanged_wake_words_reuses_existing_keywords(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            voice_dir = Path(temp_dir) / "voice"
            (voice_dir / "model" / "sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20").mkdir(parents=True)
            (voice_dir / "keywords.txt").write_text("existing keywords\n", encoding="utf-8")
            config = Config()
            config.providers.deepseek.api_key = "test-key"
            config.providers.deepseek.api_base = "https://api.example.test/v1"
            config.channels.voice = {
                "enabled": True,
                "voiceDir": str(voice_dir),
                "wakeWords": ["大虾米"],
            }
            previous_voice = {"enabled": True, "wakeWords": ["大虾米"]}

            with (
                patch("homebot.cli.config._sync_voice_assets", return_value=[]),
                patch("homebot.cli.config._generate_keywords_via_llm", return_value=True) as generate_keywords,
                patch("homebot.cli.config.save_config"),
                patch("homebot.utils.helpers.sync_workspace_templates"),
            ):
                self.assertTrue(
                    _save_config(
                        config,
                        prepare_voice=True,
                        previous_voice_section=previous_voice,
                    )
                )

            self.assertFalse(generate_keywords.call_args.kwargs["force"])

    def test_kws_defaults_are_added_when_opening_voice_menu(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config()
            config.channels.voice = {"voiceDir": str(Path(temp_dir) / "voice")}

            with patch("builtins.input", return_value="0"):
                _configure_voice(config)

            self.assertEqual(config.channels.voice["kwsScore"], 2.5)
            self.assertEqual(config.channels.voice["kwsThreshold"], 0.002)
            self.assertEqual(config.channels.voice["kwsMaxActivePaths"], 12)

    def test_kws_settings_updates_values(self) -> None:
        section = {}
        defaults = __import__("homebot.channels.voice", fromlist=["VoiceConfig"]).VoiceConfig()

        with patch("builtins.input", side_effect=["3", "0.001", "16"]):
            _configure_kws_settings(section, defaults)

        self.assertEqual(section, {
            "kwsScore": 3.0,
            "kwsThreshold": 0.001,
            "kwsMaxActivePaths": 16,
        })

    def test_voice_menu_discovers_profiles_from_speaker_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            voice_dir = Path(temp_dir) / "voice"
            (voice_dir / "speakers" / "brandon").mkdir(parents=True)
            config = Config()
            config.channels.voice = {
                "voiceDir": str(voice_dir),
                "speakerVerificationEnabled": True,
            }
            output = io.StringIO()

            with patch("builtins.input", return_value="0"), redirect_stdout(output):
                _configure_voice(config)

            self.assertIn("User recognition: enabled (1 users)", output.getvalue())
            self.assertEqual(config.channels.voice["speakerProfiles"][0]["id"], "brandon")

    def test_discovers_profiles_from_speaker_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            voice_dir = Path(temp_dir) / "voice"
            brandon_dir = voice_dir / "speakers" / "brandon"
            brandon_dir.mkdir(parents=True)
            (brandon_dir / "1.wav").write_bytes(b"wav")
            (brandon_dir / "2.wav").write_bytes(b"wav")

            self.assertEqual(
                _discover_speaker_profiles(voice_dir),
                [{
                    "id": "brandon",
                    "name": "Brandon",
                    "enrollmentWavs": [str(brandon_dir / "1.wav"), str(brandon_dir / "2.wav")],
                }],
            )

    def test_first_keywords_generation_shows_progress_messages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            voice_dir = Path(temp_dir) / "voice"
            voice_dir.mkdir()
            response = MagicMock()
            response.read.return_value = json.dumps({
                "choices": [{"message": {"content": "d à @大虾米"}}],
            }).encode()
            response.__enter__.return_value = response
            output = io.StringIO()

            with patch("urllib.request.urlopen", return_value=response), redirect_stdout(output):
                self.assertTrue(
                    _generate_keywords_via_llm(
                        voice_dir,
                        ["大虾米"],
                        "test-key",
                        "https://api.example.test/v1",
                        "test-model",
                    )
                )

            self.assertIn("正在访问大模型生成 keywords.txt", output.getvalue())
            self.assertIn("keywords.txt 已生成", output.getvalue())
            self.assertTrue((voice_dir / "keywords.txt").is_file())

    def test_basic_settings_returns_after_creating_keywords(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            voice_dir = Path(temp_dir) / "voice"
            (voice_dir / "model" / "sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20").mkdir(parents=True)
            config = Config()
            config.providers.deepseek.api_key = "test-key"
            config.providers.deepseek.api_base = "https://api.example.test/v1"
            config.channels.voice = {"enabled": True, "voiceDir": str(voice_dir)}

            with (
                patch("homebot.cli.config._sync_voice_assets", return_value=[]),
                patch("homebot.cli.config._generate_keywords_via_llm", return_value=True),
                patch("homebot.cli.config.save_config") as save,
                patch("homebot.utils.helpers.sync_workspace_templates"),
                patch("builtins.input", side_effect=["2", "", "", "", "", "大虾米", ""]),
            ):
                _configure_voice(config)

            self.assertEqual(config.channels.voice["wakeWords"], ["大虾米"])
            save.assert_called_once_with(config)

    def test_profile_management_is_available_when_recognition_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config()
            config.agents.defaults.workspace = str(Path(temp_dir) / "workspace")
            config.channels.voice = {"voiceDir": str(Path(temp_dir) / "voice")}

            with (
                patch("homebot.cli.config._configure_family_members") as manage_profiles,
                patch("homebot.cli.config.save_config"),
                patch("homebot.utils.helpers.sync_workspace_templates"),
                patch("builtins.input", side_effect=["2", "0"]),
            ):
                _configure_user_recognition(config)

            manage_profiles.assert_called_once_with(config)
