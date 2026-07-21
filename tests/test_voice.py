import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

from homebot.agent.context import ContextBuilder
from homebot.bus.queue import MessageBus
from homebot.channels.voice import VoiceChannel, VoiceConfig
from homebot.voice.tts_streaming import StreamingTTS
from homebot.voice.state import VoiceState


class FakeSTT:
    def __init__(self) -> None:
        self.starts = 0
        self.reset_calls = 0
        self.silence_timer_resets = 0
        self.silence_timeouts: list[float | None] = []

    def start(self, *, silence_timeout: float | None = None) -> int:
        self.starts += 1
        self.silence_timeouts.append(silence_timeout)
        return self.starts

    def reset(self) -> None:
        self.reset_calls += 1

    def reset_silence_timer(self) -> None:
        self.silence_timer_resets += 1


class FakeTTS:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.flush_calls = 0
        self.stop_calls = 0
        self.start_calls = 0

    def feed_text(self, text: str) -> None:
        self.texts.append(text)

    def flush(self) -> None:
        self.flush_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1

    def start(self) -> None:
        self.start_calls += 1


_JSON_META = {"_stream_delta": True, "_stream_id": "stream-1", "_voice_json_response": True}
_JSON_END = {"_stream_end": True, "_stream_id": "stream-1", "_voice_json_response": True}


class VoiceAudioDeviceConfigTest(unittest.TestCase):
    def test_audio_device_config_uses_camel_case_aliases(self) -> None:
        config = VoiceConfig.model_validate(
            {"inputDevice": "USB Microphone", "outputDevice": "USB Speaker"}
        )

        self.assertEqual(config.input_device, "USB Microphone")
        self.assertEqual(config.output_device, "USB Speaker")
        self.assertEqual(
            config.model_dump(by_alias=True)["inputDevice"], "USB Microphone"
        )
        self.assertEqual(
            config.model_dump(by_alias=True)["outputDevice"], "USB Speaker"
        )

    def test_kws_defaults_match_voice_configuration(self) -> None:
        config = VoiceConfig()
        self.assertEqual(config.kws_score, 2.5)
        self.assertEqual(config.kws_threshold, 0.002)
        self.assertEqual(config.kws_max_active_paths, 12)

    def test_streaming_tts_passes_configured_output_device(self) -> None:
        tts = StreamingTTS(api_key="key", output_device="USB Speaker")
        self.assertEqual(tts._output_device, "USB Speaker")


class VoiceChannelTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.bus = MessageBus()
        self.channel = VoiceChannel(VoiceConfig(), self.bus)
        self.channel._stt = FakeSTT()
        self.channel._tts = FakeTTS()
        self.channel._state = VoiceState.RECOGNIZING
        self.channel._current_chat_id = "activation"
        self.channel._session_key = "voice:activation"
        self.channel._recognition_generation = 1

    async def test_wav_prompt_uses_configured_output_device(self) -> None:
        channel = VoiceChannel(VoiceConfig(output_device="USB Speaker"), MessageBus())
        with patch("sounddevice.play") as play:
            await channel._play_file(Path("homebot/voice/assets/audio/wake_reply.wav"))

        self.assertEqual(play.call_args.kwargs["device"], "USB Speaker")

    async def test_wav_prompt_uses_configured_output_device(self) -> None:
        channel = VoiceChannel(VoiceConfig(output_device="USB Speaker"), MessageBus())
        with patch("sounddevice.play") as play:
            await channel._play_file(Path("homebot/voice/assets/audio/wake_reply.wav"))

        self.assertEqual(play.call_args.kwargs["device"], "USB Speaker")

    def test_voice_contract_is_system_prompt_not_user_history(self) -> None:
        with TemporaryDirectory() as workspace:
            messages = ContextBuilder(Path(workspace)).build_messages(
                history=[],
                current_message="查天气",
                channel="voice",
                chat_id="activation",
            )

        self.assertIn("用户正在通过语音与你交互", messages[0]["content"])
        self.assertIn('"dialogue_state":"end|continuous|follow_up"', messages[0]["content"])
        self.assertIn("默认使用 `end`", messages[0]["content"])
        self.assertIn("我爱你", messages[0]["content"])
        self.assertIn("明确提出想进行较长时间的多轮讨论", messages[0]["content"])
        self.assertIn("最后必须带一个自然、简短的追问", messages[0]["content"])
        self.assertNotIn("用户正在通过语音与你交互", messages[1]["content"])
        self.assertTrue(messages[1]["content"].endswith("查天气"))

    async def _publish_query(self, text: str) -> None:
        await self.channel._handle_query(text, self.channel._recognition_generation)
        message = self.bus.inbound.get_nowait()
        self.assertFalse(message.ephemeral)
        self.assertEqual(message.chat_id, "activation")
        self.assertEqual(message.session_key_override, "voice:activation")
        self.assertTrue(message.metadata["_new_turn"])
        self.assertTrue(message.metadata["_voice_json_response"])
        self.assertEqual(message.metadata["_response_format"], {"type": "json_object"})

    async def test_cancel_interaction_resets_to_wake_word_listening(self) -> None:
        self.channel._state = VoiceState.THINKING
        await self.channel.cancel_interaction()

        self.assertEqual(self.channel._state, VoiceState.LISTENING)
        self.assertIsNone(self.channel._current_chat_id)
        self.assertEqual(self.channel._stt.reset_calls, 1)
        self.assertEqual(self.channel._tts.stop_calls, 1)
        self.assertEqual(self.channel._tts.start_calls, 1)

    async def test_reply_is_spoken_before_json_stream_ends(self) -> None:
        await self._publish_query("查天气")
        await self.channel.send_delta("activation", '{"reply":"今天晴天。', _JSON_META)

        self.assertEqual(self.channel._tts.texts, ["今天晴天。"])
        self.assertEqual(self.channel._tts.flush_calls, 0)

        await self.channel.send_delta(
            "activation", '明天有雨。","dialogue_state":"end"}', _JSON_META
        )

        self.assertEqual(self.channel._tts.texts, ["今天晴天。", "明天有雨。"])
        self.assertEqual(self.channel._state, VoiceState.PLAYING)

        await self.channel.send_delta("activation", "", _JSON_END)

        self.assertEqual(self.channel._tts.flush_calls, 1)
        self.assertEqual(self.channel._state, VoiceState.LISTENING)

    async def test_reply_field_can_follow_dialogue_state(self) -> None:
        await self._publish_query("查天气")
        await self.channel.send_delta(
            "activation",
            '{"dialogue_state":"end","reply":"字段顺序也可以。"}',
            _JSON_META,
        )

        self.assertEqual(self.channel._tts.texts, ["字段顺序也可以。"])
        await self.channel.send_delta("activation", "", _JSON_END)
        self.assertEqual(self.channel._state, VoiceState.LISTENING)

    async def test_reply_key_and_escaped_text_can_cross_chunks(self) -> None:
        await self._publish_query("读一句话")
        for delta in ('{"re', 'ply":"第一行\\n第二行，', '\\u4f60\\u597d。","dialogue_state":"end"}'):
            await self.channel.send_delta("activation", delta, _JSON_META)

        self.assertEqual(self.channel._tts.texts, ["第一行", "第二行，你好。"])
        await self.channel.send_delta("activation", "", _JSON_END)

    async def test_continuous_is_fully_llm_driven_without_turn_limit(self) -> None:
        for index in range(5):
            await self._publish_query(f"第 {index + 1} 轮")
            stream_id = f"stream-{index + 1}"
            metadata = {**_JSON_META, "_stream_id": stream_id}
            end = {**_JSON_END, "_stream_id": stream_id}
            await self.channel.send_delta(
                "activation",
                '{"reply":"请继续。","dialogue_state":"continuous"}',
                metadata,
            )
            await self.channel.send_delta("activation", "", end)

        self.assertEqual(self.channel._state, VoiceState.RECOGNIZING)
        self.assertEqual(self.channel._current_chat_id, "activation")
        self.assertEqual(self.channel._stt.starts, 5)

    async def test_follow_up_beeps_while_listening_for_next_turn(self) -> None:
        self.channel._play_file = AsyncMock()

        await self.channel.send_delta(
            "activation",
            '{"reply":"请告诉我提醒时间。","dialogue_state":"follow_up"}',
            _JSON_META,
        )
        await self.channel.send_delta("activation", "", _JSON_END)

        self.assertEqual(self.channel._state, VoiceState.RECOGNIZING)
        self.assertEqual(self.channel._stt.starts, 1)
        self.assertEqual(self.channel._stt.silence_timer_resets, 2)
        self.channel._play_file.assert_awaited_once_with(
            Path("~/.homebot/workspace/voice/audio/beep.wav").expanduser().resolve()
        )

    async def test_follow_up_keeps_listening_until_task_ends(self) -> None:
        await self.channel.send_delta(
            "activation",
            '{"reply":"请告诉我提醒时间。","dialogue_state":"follow_up"}',
            _JSON_META,
        )
        await self.channel.send_delta("activation", "", _JSON_END)

        self.assertEqual(self.channel._state, VoiceState.RECOGNIZING)
        self.assertFalse(self.channel._continuous_dialogue)

        await self._publish_query("明天早上八点")
        metadata = {**_JSON_META, "_stream_id": "stream-2"}
        end = {**_JSON_END, "_stream_id": "stream-2"}
        await self.channel.send_delta(
            "activation", '{"reply":"已设置提醒。","dialogue_state":"end"}', metadata
        )
        await self.channel.send_delta("activation", "", end)

        self.assertEqual(self.channel._state, VoiceState.LISTENING)

    async def test_continuous_session_ignores_later_end_but_exits_on_timeout(self) -> None:
        await self.channel.send_delta(
            "activation",
            '{"reply":"继续聊。","dialogue_state":"continuous"}',
            _JSON_META,
        )
        await self.channel.send_delta("activation", "", _JSON_END)
        await self._publish_query("换个话题")

        metadata = {**_JSON_META, "_stream_id": "stream-2"}
        end = {**_JSON_END, "_stream_id": "stream-2"}
        await self.channel.send_delta(
            "activation", '{"reply":"好的。","dialogue_state":"end"}', metadata
        )
        await self.channel.send_delta("activation", "", end)

        self.assertEqual(self.channel._state, VoiceState.RECOGNIZING)
        self.assertEqual(self.channel._stt.silence_timeouts[-1], 30.0)

        await self.channel._on_timeout()

        self.assertEqual(self.channel._state, VoiceState.LISTENING)
        self.assertIsNone(self.channel._current_chat_id)

    async def test_end_closes_previous_continuous_dialogue(self) -> None:
        await self.channel.send_delta(
            "activation",
            '{"reply":"继续聊。","dialogue_state":"continuous"}',
            _JSON_META,
        )
        await self.channel.send_delta("activation", "", _JSON_END)

        self.assertEqual(self.channel._state, VoiceState.RECOGNIZING)

        await self._publish_query("结束这一轮")
        metadata = {**_JSON_META, "_stream_id": "stream-2"}
        end = {**_JSON_END, "_stream_id": "stream-2"}
        await self.channel.send_delta(
            "activation", '{"reply":"好的。","dialogue_state":"end"}', metadata
        )
        await self.channel.send_delta("activation", "", end)

        self.assertEqual(self.channel._state, VoiceState.RECOGNIZING)
        self.assertEqual(self.channel._current_chat_id, "activation")

    async def test_tool_segment_is_discarded_before_final_reply(self) -> None:
        await self._publish_query("查天气")
        await self.channel.send_delta(
            "activation",
            '{"reply":"不应播报。","dialogue_state":"continuous"}',
            _JSON_META,
        )
        await self.channel.send_delta(
            "activation",
            "",
            {**_JSON_END, "_resuming": True},
        )

        self.assertEqual(self.channel._tts.texts, ["不应播报。"])
        self.assertEqual(self.channel._tts.flush_calls, 0)
        self.assertEqual(self.channel._state, VoiceState.PLAYING)

        metadata = {**_JSON_META, "_stream_id": "stream-2"}
        end = {**_JSON_END, "_stream_id": "stream-2"}
        await self.channel.send_delta(
            "activation", '{"reply":"查询完成。","dialogue_state":"end"}', metadata
        )
        await self.channel.send_delta("activation", "", end)

        self.assertEqual(self.channel._tts.texts, ["不应播报。", "查询完成。"])
        self.assertEqual(self.channel._state, VoiceState.LISTENING)

    async def test_invalid_final_json_ends_after_already_streamed_reply(self) -> None:
        await self._publish_query("查天气")
        await self.channel.send_delta("activation", '{"reply":"已开始播报。"', _JSON_META)

        self.assertEqual(self.channel._tts.texts, ["已开始播报。"])
        await self.channel.send_delta("activation", "", _JSON_END)

        self.assertEqual(self.channel._tts.flush_calls, 1)
        self.assertEqual(self.channel._state, VoiceState.LISTENING)

    async def test_timeout_plays_bye_prompt(self) -> None:
        self.channel._play_file = AsyncMock()

        await self.channel._on_timeout()

        self.assertEqual(self.channel._state, VoiceState.LISTENING)
        self.assertIsNone(self.channel._current_chat_id)
        self.channel._play_file.assert_awaited_once_with(
            Path("~/.homebot/workspace/voice").expanduser().resolve() / "audio" / "bye.wav"
        )


if __name__ == "__main__":
    unittest.main()
