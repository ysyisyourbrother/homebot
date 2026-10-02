"""Tests for the wake-clip debug capture (rolling, newest three only)."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from homebot.bus.queue import MessageBus
from homebot.channels.voice import (
    _WAKE_CLIP_POST_BLOCKS,
    VoiceChannel,
    VoiceConfig,
    _prune_wake_clips,
    _write_wav,
)


class WakeClipFileTest(unittest.TestCase):
    def test_wav_round_trip(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "clip.wav"
            samples = np.sin(np.linspace(0, 50, 1600)).astype(np.float32) * 0.5

            _write_wav(path, samples)

            import wave

            with wave.open(str(path), "rb") as handle:
                self.assertEqual(handle.getnchannels(), 1)
                self.assertEqual(handle.getframerate(), 16000)
                self.assertEqual(handle.getnframes(), 1600)

    def test_prune_keeps_only_the_newest(self) -> None:
        with TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            for index in range(1, 6):
                (directory / f"wake-2026100{index}-120000.wav").write_bytes(b"x")

            removed = _prune_wake_clips(directory, keep=3)

            self.assertEqual(len(removed), 2)
            remaining = sorted(p.name for p in directory.glob("wake-*.wav"))
            self.assertEqual(
                remaining,
                [
                    "wake-20261003-120000.wav",
                    "wake-20261004-120000.wav",
                    "wake-20261005-120000.wav",
                ],
            )


class WakeClipCaptureTest(unittest.TestCase):
    def make_channel(self, clip_dir: Path) -> VoiceChannel:
        channel = VoiceChannel(VoiceConfig(), MessageBus())
        channel._wake_clip_dir = clip_dir
        return channel

    def test_capture_keeps_pre_roll_and_post_roll(self) -> None:
        with TemporaryDirectory() as temp_dir:
            channel = self.make_channel(Path(temp_dir))
            block = np.ones(1600, dtype=np.float32) * 0.1

            # ~1 s of context before the wake word
            for _ in range(10):
                channel._wake_ring.append(block.copy())
            channel._start_wake_capture("大虾米")
            for _ in range(_WAKE_CLIP_POST_BLOCKS):
                channel._wake_capture["blocks"].append(block.copy())
                channel._wake_capture["remaining"] -= 1
            channel._queue_wake_clip()

            path, blocks, keyword = channel._wake_clip_queue.get_nowait()
            self.assertEqual(keyword, "大虾米")
            self.assertTrue(path.name.startswith("wake-"))
            self.assertEqual(sum(len(b) for b in blocks), 20 * 1600)
            self.assertIsNone(channel._wake_capture)

    def test_second_detection_while_capturing_is_ignored(self) -> None:
        with TemporaryDirectory() as temp_dir:
            channel = self.make_channel(Path(temp_dir))
            channel._wake_ring.append(np.zeros(1600, dtype=np.float32))

            channel._start_wake_capture("大虾米")
            first = channel._wake_capture
            channel._start_wake_capture("大虾米")

            self.assertIs(channel._wake_capture, first)


if __name__ == "__main__":
    unittest.main()
