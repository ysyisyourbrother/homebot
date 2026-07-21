import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

from homebot.agent.context import ContextBuilder
from homebot.channels.voice import (
    SPEAKER_MODEL_NAME,
    VoiceChannel,
    VoiceConfig,
    _speaker_model_path,
    _speaker_profiles,
)
from homebot.bus.queue import MessageBus
from homebot.cli.config import (
    _configure_family_members,
    _configure_user_recognition,
    _download_speaker_model,
)
from homebot.config.schema import Config
from homebot.voice.speaker_verification import SpeakerVerifier, member_id


class SpeakerModelDownloadTest(unittest.TestCase):
    def test_existing_model_is_reused_without_network_download(self) -> None:
        with TemporaryDirectory() as temp_dir:
            voice_dir = Path(temp_dir) / "voice"
            model_path = voice_dir / "model" / SPEAKER_MODEL_NAME
            model_path.parent.mkdir(parents=True)
            model_path.write_bytes(b"model")

            with patch("urllib.request.urlretrieve") as download:
                self.assertEqual(_download_speaker_model(voice_dir), model_path)

            download.assert_not_called()

    def test_downloads_model_to_workspace_voice_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            voice_dir = Path(temp_dir) / "voice"

            def download(_url: str, destination: str, progress) -> None:
                progress(1, 1, 1)
                Path(destination).write_bytes(b"model")

            with patch("urllib.request.urlretrieve", side_effect=download):
                model_path = _download_speaker_model(voice_dir)

            self.assertEqual(model_path, voice_dir / "model" / SPEAKER_MODEL_NAME)
            self.assertEqual(model_path.read_bytes(), b"model")


    def test_member_id_is_safe_and_stable(self) -> None:
        self.assertEqual(member_id("Alice Smith", 1), "alice-smith")
        self.assertEqual(member_id("王小明", 2), "member-2")

    def test_identify_uses_threshold_and_best_profile(self) -> None:
        verifier = object.__new__(SpeakerVerifier)
        verifier._profiles = {
            "alice": [
                np.array([1.0, 0.0], dtype=np.float32),
                np.array([0.2, 0.8], dtype=np.float32),
            ],
            "bob": [np.array([0.0, 1.0], dtype=np.float32)],
        }
        verifier._threshold = 0.8
        verifier.embedding = lambda _audio: np.array([0.9, 0.1], dtype=np.float32)

        self.assertEqual(verifier.identify(np.array([0.0], dtype=np.float32))[0], "alice")
        verifier._threshold = 1.01
        self.assertEqual(verifier.identify(np.array([0.0], dtype=np.float32))[0], "guest")


class FamilyMembersConfigTest(unittest.TestCase):
    def test_enrollment_creates_profiles_and_config(self) -> None:
        with TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            voice_dir = Path(temp_dir) / "voice"
            config = Config()
            config.agents.defaults.workspace = str(workspace)
            config.channels.voice = {
                "voiceDir": str(voice_dir),
                "speakerVerificationEnabled": True,
            }

            class FakeVerifier:
                def __init__(self, *_args) -> None:
                    pass

                def enroll_wav(self, wav_path: Path) -> Path:
                    embedding = wav_path.with_suffix(".npy")
                    embedding.write_bytes(b"embedding")
                    return embedding

            def fake_record(path: Path, _device: str | None) -> None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"wav")

            with (
                patch("homebot.cli.config._download_speaker_model", return_value=voice_dir / "model" / SPEAKER_MODEL_NAME) as download_model,
                patch("homebot.voice.speaker_verification.SpeakerVerifier", FakeVerifier),
                patch("homebot.voice.speaker_verification.record_wav", fake_record),
                patch("builtins.input", side_effect=["1", "Alice", "0"]),
            ):
                _configure_family_members(config)

            download_model.assert_called_once_with(voice_dir.resolve())
            section = config.channels.voice
            self.assertEqual(section["speakerModelPath"], str(voice_dir / "model" / SPEAKER_MODEL_NAME))
            self.assertTrue(section["speakerVerificationEnabled"])
            self.assertEqual(section["speakerProfiles"][0]["id"], "alice")
            self.assertEqual(len(section["speakerProfiles"][0]["enrollmentWavs"]), 3)
            for sample_index in range(1, 4):
                self.assertTrue((voice_dir / "speakers" / "alice" / f"{sample_index}.wav").is_file())
                self.assertTrue((voice_dir / "speakers" / "alice" / f"{sample_index}.npy").is_file())
            self.assertTrue((workspace / "members" / "alice" / "USER.md").is_file())
            self.assertTrue((workspace / "members" / "guest" / "USER.md").is_file())

    def test_speaker_model_path_uses_voice_directory_by_default(self) -> None:
        with TemporaryDirectory() as temp_dir:
            voice_dir = Path(temp_dir) / "voice"
            self.assertEqual(
                _speaker_model_path(VoiceConfig(), voice_dir),
                voice_dir / "model" / SPEAKER_MODEL_NAME,
            )

    def test_speaker_profiles_load_from_user_directories(self) -> None:
        with TemporaryDirectory() as temp_dir:
            voice_dir = Path(temp_dir) / "voice"
            brandon_dir = voice_dir / "speakers" / "brandon"
            brandon_dir.mkdir(parents=True)
            (brandon_dir / "1.wav").write_bytes(b"wav")
            (brandon_dir / "1.npy").write_bytes(b"embedding")

            self.assertEqual(
                _speaker_profiles(voice_dir, []),
                {"brandon": [brandon_dir / "1.npy"]},
            )

        config = VoiceConfig(speaker_model_path="~/models/custom-speaker.onnx")
        self.assertEqual(
            _speaker_model_path(config, Path("/workspace/voice")),
            Path("~/models/custom-speaker.onnx").expanduser(),
        )

    def test_explicit_speaker_model_path_skips_download(self) -> None:
        with TemporaryDirectory() as temp_dir:
            custom_model = Path(temp_dir) / "custom.onnx"
            custom_model.write_bytes(b"model")
            config = Config()
            config.agents.defaults.workspace = str(Path(temp_dir) / "workspace")
            config.channels.voice = {"speakerModelPath": str(custom_model)}

            with patch("homebot.voice.speaker_verification.SpeakerVerifier") as verifier, patch(
                "homebot.cli.config._download_speaker_model"
            ) as download_model, patch("builtins.input", return_value="0"):
                _configure_family_members(config)

            download_model.assert_not_called()
            verifier.assert_called_once_with(custom_model, {}, 0.60)

    def test_enabling_recognition_downloads_model_without_profiles(self) -> None:
        with TemporaryDirectory() as temp_dir:
            voice_dir = Path(temp_dir) / "voice"
            config = Config()
            config.channels.voice = {"voiceDir": str(voice_dir)}

            with patch(
                "homebot.cli.config._download_speaker_model",
                return_value=voice_dir / "model" / SPEAKER_MODEL_NAME,
            ) as download_model, patch("homebot.cli.config.save_config"), patch(
                "homebot.utils.helpers.sync_workspace_templates"
            ), patch("builtins.input", side_effect=["1", "no", "0"]):
                _configure_user_recognition(config)

            download_model.assert_called_once_with(voice_dir.resolve())
            self.assertTrue(config.channels.voice["speakerVerificationEnabled"])
            self.assertEqual(
                config.channels.voice["speakerModelPath"],
                str(voice_dir / "model" / SPEAKER_MODEL_NAME),
            )

    def test_disabling_recognition_preserves_profiles(self) -> None:
        with TemporaryDirectory() as temp_dir:
            voice_dir = Path(temp_dir) / "voice"
            profile_dir = voice_dir / "speakers" / "alice"
            profile_dir.mkdir(parents=True)
            (profile_dir / "1.wav").write_bytes(b"wav")
            config = Config()
            config.channels.voice = {
                "voiceDir": str(voice_dir),
                "speakerVerificationEnabled": True,
                "speakerProfiles": [{"id": "alice", "name": "Alice", "enrollmentWavs": []}],
            }

            with patch("homebot.cli.config.save_config"), patch(
                "homebot.utils.helpers.sync_workspace_templates"
            ), patch("builtins.input", side_effect=["1", "0"]):
                _configure_user_recognition(config)

            self.assertFalse(config.channels.voice["speakerVerificationEnabled"])
            self.assertEqual(config.channels.voice["speakerProfiles"][0]["id"], "alice")
            self.assertTrue(profile_dir.is_dir())

    def test_deleting_profile_removes_recordings_and_keeps_recognition_enabled(self) -> None:
        with TemporaryDirectory() as temp_dir:
            voice_dir = Path(temp_dir) / "voice"
            wav_path = voice_dir / "speakers" / "alice" / "1.wav"
            wav_path.parent.mkdir(parents=True)
            wav_path.write_bytes(b"wav")
            wav_path.with_suffix(".npy").write_bytes(b"embedding")
            model_path = voice_dir / "model" / SPEAKER_MODEL_NAME
            config = Config()
            config.agents.defaults.workspace = str(Path(temp_dir) / "workspace")
            config.channels.voice = {
                "voiceDir": str(voice_dir),
                "speakerVerificationEnabled": True,
                "speakerModelPath": str(model_path),
                "speakerProfiles": [{"id": "alice", "name": "Alice", "enrollmentWavs": [str(wav_path)]}],
            }

            with patch("homebot.voice.speaker_verification.SpeakerVerifier"), patch(
                "builtins.input", side_effect=["1", "2", "0"]
            ):
                _configure_family_members(config)

            self.assertTrue(config.channels.voice["speakerVerificationEnabled"])
            self.assertEqual(config.channels.voice["speakerProfiles"], [])
            self.assertFalse(wav_path.exists())
            self.assertFalse(wav_path.with_suffix(".npy").exists())

    def test_voice_uses_only_selected_member_profile(self) -> None:
        with TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "USER.md").write_text("root profile", encoding="utf-8")
            member = workspace / "members" / "alice"
            member.mkdir(parents=True)
            (member / "USER.md").write_text("alice profile", encoding="utf-8")
            guest = workspace / "members" / "guest"
            guest.mkdir(parents=True)
            (guest / "USER.md").write_text("guest profile", encoding="utf-8")

            builder = ContextBuilder(workspace)
            member_prompt = builder.build_messages([], "hello", channel="voice", voice_member_id="alice")[0]["content"]
            guest_prompt = builder.build_messages([], "hello", channel="voice", voice_member_id="../../root")[0]["content"]
            direct_prompt = builder.build_messages([], "hello")[0]["content"]

        self.assertIn("alice profile", member_prompt)
        self.assertNotIn("root profile", member_prompt)
        self.assertIn("guest profile", guest_prompt)
        self.assertIn("root profile", direct_prompt)


class VoiceIdentityMetadataTest(unittest.IsolatedAsyncioTestCase):
    async def test_voice_query_publishes_cached_member_id(self) -> None:
        channel = VoiceChannel(VoiceConfig(), MessageBus())
        channel._voice_member_id = "alice"
        channel._state = __import__("homebot.voice.state", fromlist=["VoiceState"]).VoiceState.RECOGNIZING
        channel._current_chat_id = "activation"
        channel._session_key = "voice:activation"
        channel._recognition_generation = 1

        class STT:
            def reset(self) -> None:
                pass

        channel._stt = STT()
        await channel._handle_query("查天气", 1)
        message = channel.bus.inbound.get_nowait()
        self.assertEqual(message.metadata["voice_member_id"], "alice")
