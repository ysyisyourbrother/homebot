"""Regression tests for the voice channel's self-healing watchdog.

Both failure modes here are silent in production: the process stays healthy and
the log stays empty, while the assistant simply stops responding.  They are
easy to regress, so they get explicit tests.
"""

import asyncio
import time
import unittest
from unittest.mock import patch

from homebot.bus.queue import MessageBus
from homebot.channels.voice import VoiceChannel, VoiceConfig
from homebot.voice.state import VoiceState


class VoiceWatchdogTest(unittest.IsolatedAsyncioTestCase):
    def make_channel(self) -> VoiceChannel:
        channel = VoiceChannel(VoiceConfig(), MessageBus())
        channel._running = True
        now = time.monotonic()
        channel._last_callback_at = now
        channel._last_signal_at = now
        channel._stream_opened_at = now
        channel._state = VoiceState.LISTENING
        return channel

    async def test_stuck_state_is_forced_back_to_listening(self) -> None:
        channel = self.make_channel()
        channel._state = VoiceState.PLAYING
        channel._state_since = time.monotonic() - (channel._STATE_STUCK_SECONDS + 10)

        with patch.object(channel, "_reopen_input_stream") as reopen:
            await channel._watchdog_tick()

        self.assertEqual(channel._state, VoiceState.LISTENING)
        reopen.assert_not_called()

    async def test_missing_callbacks_reopen_the_stream(self) -> None:
        channel = self.make_channel()
        channel._last_callback_at = time.monotonic() - (
            channel._CALLBACK_STALL_SECONDS + 5
        )

        with patch.object(channel, "_reopen_input_stream") as reopen:
            await channel._watchdog_tick()

        reopen.assert_called_once()

    async def test_digital_silence_recycles_and_then_backs_off(self) -> None:
        channel = self.make_channel()
        channel._last_signal_at = time.monotonic() - (
            channel._DIGITAL_SILENCE_SECONDS + 100
        )

        with patch.object(channel, "_reopen_input_stream") as reopen:
            await channel._watchdog_tick()
        self.assertEqual(reopen.call_count, 1)
        self.assertEqual(channel._silent_recycles, 1)

        # Backoff doubles the window (5 min -> 10 min) and the mocked reopen did
        # not refresh the timestamps, so the same silence no longer triggers.
        channel._last_recycle_at = 0.0
        with patch.object(channel, "_reopen_input_stream") as reopen_again:
            await channel._watchdog_tick()
        reopen_again.assert_not_called()

    async def test_signal_resets_the_silence_backoff(self) -> None:
        channel = self.make_channel()
        channel._silent_recycles = 3
        # PLAYING keeps the callback off the KWS path (no detector in a unit test)
        # while still exercising the peak/silence accounting.
        channel._state = VoiceState.PLAYING

        channel._audio_callback(
            __import__("numpy").ones((1600, 1), dtype="float32") * 0.05, 1600, None, None
        )

        self.assertEqual(channel._silent_recycles, 0)

    async def test_old_stream_is_recycled_even_when_quiet(self) -> None:
        """A home with nobody talking must still get a fresh stream."""
        channel = self.make_channel()
        now = time.monotonic()
        channel._stream_opened_at = now - (channel._STREAM_MAX_AGE_SECONDS + 60)
        channel._last_signal_at = now - 30  # silence is normal, not suspicious

        with patch.object(channel, "_reopen_input_stream") as reopen:
            await channel._watchdog_tick()

        reopen.assert_called_once()


class GuardedCoroutineTest(unittest.IsolatedAsyncioTestCase):
    def make_channel(self) -> VoiceChannel:
        channel = VoiceChannel(VoiceConfig(), MessageBus())
        channel._running = True
        return channel

    async def test_failure_returns_the_channel_to_listening(self) -> None:
        channel = self.make_channel()
        channel._state = VoiceState.PLAYING

        async def boom() -> None:
            raise RuntimeError("stt connect failed")

        await channel._guarded("test", boom())

        self.assertEqual(channel._state, VoiceState.LISTENING)

    async def test_cancellation_is_not_swallowed(self) -> None:
        channel = self.make_channel()

        async def cancelled() -> None:
            raise asyncio.CancelledError()

        with self.assertRaises(asyncio.CancelledError):
            await channel._guarded("test", cancelled())


if __name__ == "__main__":
    unittest.main()
