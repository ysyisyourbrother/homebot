"""Voice channel: wake-word-activated voice assistant.

Integrates wake word detection (sherpa-onnx), real-time speech-to-text
(DashScope paraformer-realtime-v2), and streaming text-to-speech
(DashScope CosyVoice) into the homebot message bus as a standard channel.

Runs alongside Telegram / Feishu / CLI in gateway mode.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from loguru import logger
from pydantic import BaseModel as PydanticBaseModel, Field

from homebot.bus.events import InboundMessage, OutboundMessage
from homebot.bus.queue import MessageBus
from homebot.channels.base import BaseChannel
from homebot.config.schema import Base
from homebot.voice.state import VoiceState

if TYPE_CHECKING:
    from homebot.voice.kws import WakeWordDetector
    from homebot.voice.stt import RealtimeSTT
    from homebot.voice.tts_streaming import StreamingTTS

SAMPLE_RATE = 16000
BLOCK_SIZE = 1600  # 100ms @ 16kHz

# Path to package assets (keywords, audio files)
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "voice" / "assets"
_MODEL_NAME = "sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20"
SPEAKER_MODEL_NAME = "3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx"
_LEGACY_SPEAKER_MODEL_PATH = _ASSETS_DIR / "model" / SPEAKER_MODEL_NAME

_REMINDER_WAV = _ASSETS_DIR / "audio" / "reminder_bg.wav"
_BEEP_WAV = _ASSETS_DIR / "audio" / "beep.wav"


def _sync_voice_asset(voice_dir: Path, rel_path: str) -> Path:
    """Copy a voice asset from package to voice_dir if missing. Returns the dest path."""
    src = _ASSETS_DIR / rel_path
    dest = voice_dir / rel_path
    if not dest.exists() and src.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(src, dest)
    return dest


def _resolve_voice_dir(config: VoiceConfig) -> Path:
    """Resolve and create the voice directory from config."""
    return Path(config.voice_dir).expanduser().resolve()


def _speaker_model_path(config: VoiceConfig, voice_dir: Path) -> Path:
    """Resolve the workspace speaker model unless a custom path is configured."""
    configured_path = Path(config.speaker_model_path).expanduser()
    if configured_path == _LEGACY_SPEAKER_MODEL_PATH:
        return voice_dir / "model" / SPEAKER_MODEL_NAME
    return configured_path


def _speaker_profiles(voice_dir: Path, configured_profiles: list[SpeakerProfileConfig]) -> dict[str, list[Path]]:
    """Load enrollment WAVs from the user directories under speakers/."""
    speakers_dir = voice_dir / "speakers"
    if speakers_dir.is_dir():
        return {
            profile_dir.name: [wav_path.with_suffix(".npy") for wav_path in sorted(profile_dir.glob("*.wav"))]
            for profile_dir in speakers_dir.iterdir()
            if profile_dir.is_dir()
        }
    return {
        profile.id: [
            Path(wav_path).expanduser()
            for wav_path in (profile.enrollment_wavs or [profile.enrollment_wav])
            if wav_path
        ]
        for profile in configured_profiles
    }


def _load_reminder_wav() -> tuple[Any, int] | None:
    """Load reminder background audio into memory."""
    import wave

    import numpy as np

    if not _REMINDER_WAV.exists():
        return None
    with wave.open(str(_REMINDER_WAV), "rb") as f:
        nframes = f.getnframes()
        nchannels = f.getnchannels()
        raw = np.frombuffer(f.readframes(nframes), dtype=np.int16).copy()
        if nchannels == 2:
            raw = raw.reshape(-1, 2)
        return raw, f.getframerate()


_REMINDER_PCM: tuple[Any, int] | None = None  # (ndarray, sample_rate)


class VoiceReply(PydanticBaseModel):
    reply: str
    dialogue_state: Literal["end", "continuous", "follow_up"]


class ReplyStreamParser:
    """Incrementally decode the top-level JSON ``reply`` string."""

    _ESCAPES = {
        '"': '"',
        "\\": "\\",
        "/": "/",
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
    }

    def __init__(self) -> None:
        self._json = ""
        self._position: int | None = None
        self._escaped = False
        self._unicode_escape: str | None = None
        self._complete = False

    @property
    def raw_json(self) -> str:
        return self._json

    def feed(self, delta: str) -> str:
        self._json += delta
        if self._complete:
            return ""
        if self._position is None:
            match = re.search(r'"reply"\s*:\s*"', self._json)
            if not match:
                return ""
            self._position = match.end()

        decoded: list[str] = []
        while self._position < len(self._json):
            char = self._json[self._position]
            self._position += 1
            if self._unicode_escape is not None:
                self._unicode_escape += char
                if len(self._unicode_escape) == 4:
                    try:
                        decoded.append(chr(int(self._unicode_escape, 16)))
                    except ValueError:
                        pass
                    self._unicode_escape = None
                continue
            if self._escaped:
                self._escaped = False
                if char == "u":
                    self._unicode_escape = ""
                elif char in self._ESCAPES:
                    decoded.append(self._ESCAPES[char])
                continue
            if char == "\\":
                self._escaped = True
            elif char == '"':
                self._complete = True
                break
            else:
                decoded.append(char)
        return "".join(decoded)


class SpeakerProfileConfig(Base):
    """One enrolled household member."""

    id: str
    name: str
    enrollment_wavs: list[str] = Field(default_factory=list)
    enrollment_wav: str | None = None


class VoiceConfig(Base):
    """Configuration for the voice channel."""

    enabled: bool = False
    allow_from: list[str] = Field(default_factory=lambda: ["*"])
    voice_dir: str = "~/.homebot/workspace/voice"  # Workspace voice assets root
    input_device: str | None = None  # sounddevice input device name
    output_device: str | None = None  # sounddevice output device name
    stt_api_key: str = ""  # DashScope API key for STT
    tts_api_key: str = ""  # DashScope API key for TTS (CosyVoice)
    tts_model: str = "cosyvoice-v3-flash"
    tts_voice: str = "longxiaochun_v3"
    wake_words: list[str] = Field(default_factory=list)  # Configured by user during init
    silence_timeout: float = 10.0  # Seconds of silence before auto-cancel
    continuous_silence_timeout: float = 30.0  # Seconds of silence before ending a continuous dialogue
    kws_score: float = 2.5  # Wake word detection score threshold
    kws_threshold: float = 0.002  # Wake word token threshold
    kws_num_trailing_blanks: int = 1  # Blank frames required after wake word
    kws_max_active_paths: int = 12  # Decoder paths retained during KWS
    speaker_verification_enabled: bool = False
    speaker_model_path: str = str(_LEGACY_SPEAKER_MODEL_PATH)
    speaker_threshold: float = 0.60
    speaker_min_seconds: float = 1.5
    speaker_max_seconds: float = 8.0
    speaker_profiles: list[SpeakerProfileConfig] = Field(default_factory=list)

    exit_commands: list[str] = Field(
        default_factory=lambda: ["退出", "再见", "拜拜"]
    )


class VoiceChannel(BaseChannel):
    """Wake-word-driven voice assistant channel."""

    name = "voice"
    display_name = "Voice"

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        return VoiceConfig().model_dump(by_alias=True)

    def __init__(self, config: Any, bus: MessageBus):
        if isinstance(config, dict):
            config = VoiceConfig.model_validate(config)
        super().__init__(config, bus)
        self.config: VoiceConfig = config

        # Audio pipeline components (initialized in start())
        self._kws: WakeWordDetector | None = None
        self._stt: RealtimeSTT | None = None
        self._tts: StreamingTTS | None = None
        self._speaker_verifier: Any | None = None
        self._speaker_audio: list[Any] = []
        self._voice_member_id: str | None = None

        # Reminder background audio (loaded once at init)
        global _REMINDER_PCM
        if _REMINDER_PCM is None:
            _REMINDER_PCM = _load_reminder_wav()
        self._reminder_pcm = _REMINDER_PCM

        # Thread bridge
        self._loop: asyncio.AbstractEventLoop | None = None

        # State
        self._state = VoiceState.STOPPED
        self._stream: Any = None  # sounddevice.InputStream
        self._current_chat_id: str | None = None
        self._session_key: str | None = None
        self._recognition_generation: int | None = None
        self._continuous_dialogue = False
        self._stream_id: str | None = None
        self._closed_stream_ids: set[str] = set()
        self._buf: str = ""
        self._reply_parser = ReplyStreamParser()

    @property
    def supports_streaming(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Channel lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialize audio pipeline and begin listening for wake word."""
        _check_dependencies()

        self._loop = asyncio.get_running_loop()

        # Validate config
        stt_api_key = self.config.stt_api_key
        if not stt_api_key:
            logger.error(
                "Voice: sttApiKey is required. Set it in config.json channels.voice.sttApiKey."
            )
            return
        tts_api_key = self.config.tts_api_key
        if not tts_api_key:
            logger.error(
                "Voice: ttsApiKey is required. Set it in config.json channels.voice.ttsApiKey."
            )
            return

        # Resolve voice directory
        voice_root = _resolve_voice_dir(self.config)
        voice_root.mkdir(parents=True, exist_ok=True)
        logger.info("Voice: assets directory: {}", voice_root)

        # Sync audio assets from package to voice_dir if missing
        for audio_name in ("wake_reply.wav", "bye.wav", "beep.wav"):
            _sync_voice_asset(voice_root, f"audio/{audio_name}")

        # Resolve KWS model directory
        model_dir = voice_root / "model" / _MODEL_NAME
        if not model_dir.is_dir():
            logger.error(
                "Voice: KWS model not found at {}. "
                "Run 'python -m homebot config' to configure voice and download the model.",
                model_dir,
            )
            return

        # Resolve keywords file (generated by 'python -m homebot config')
        keywords_file = str(voice_root / "keywords.txt")
        if not Path(keywords_file).is_file():
            logger.error(
                "Voice: keywords.txt not found at {}. "
                "Run 'python -m homebot config' to configure your wake word.",
                keywords_file,
            )
            return

        # Initialize components
        try:
            from homebot.voice.kws import WakeWordDetector
            self._kws = WakeWordDetector(
                str(model_dir),
                keywords_file,
                keywords_score=self.config.kws_score,
                keywords_threshold=self.config.kws_threshold,
                num_trailing_blanks=self.config.kws_num_trailing_blanks,
                max_active_paths=self.config.kws_max_active_paths,
            )
            logger.info("Voice: wake word detector loaded from {}", model_dir)
        except Exception as e:
            logger.error("Voice: failed to load KWS model: {}", e)
            return

        from homebot.voice.stt import RealtimeSTT
        self._stt = RealtimeSTT(
            stt_api_key,
            silence_timeout=self.config.silence_timeout,
            on_sentence_end=self._on_sentence_end,
        )
        from homebot.voice.tts_streaming import StreamingTTS
        self._tts = StreamingTTS(
            api_key=self.config.tts_api_key,
            model=self.config.tts_model,
            voice=self.config.tts_voice,
            output_device=self.config.output_device,
        )
        self._tts.start()

        if self.config.speaker_verification_enabled:
            try:
                from homebot.voice.speaker_verification import SpeakerVerifier

                profiles = _speaker_profiles(voice_root, self.config.speaker_profiles)
                speaker_model_path = _speaker_model_path(self.config, voice_root)
                self._speaker_verifier = SpeakerVerifier(
                    speaker_model_path,
                    profiles,
                    self.config.speaker_threshold,
                )
                logger.info("Voice: loaded {} speaker profile(s)", len(profiles))
            except Exception as e:
                logger.warning("Voice: speaker verification disabled: {}", e)

        self._running = True
        self._state = VoiceState.LISTENING

        # Start audio stream in a background thread (PortAudio callback runs in C thread)
        import sounddevice as sd

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            device=self.config.input_device or None,
            callback=self._audio_callback,
            blocksize=BLOCK_SIZE,
        )
        self._stream.start()
        logger.info("Voice: listening for wake words: {}", ", ".join(self.config.wake_words))

    async def stop(self) -> None:
        """Stop audio capture and release resources."""
        self._running = False
        self._clear_interaction()
        self._state = VoiceState.STOPPED

        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.debug("Voice: audio stream cleanup: {}", e)
            self._stream = None

        if self._tts:
            self._tts.stop()
            self._tts = None

        logger.info("Voice: channel stopped")

    async def cancel_interaction(self) -> None:
        """Silently end the active interaction and resume wake-word detection."""
        if not self._current_chat_id:
            return
        if self._tts:
            await asyncio.to_thread(self._tts.stop)
            self._tts.start()
        self._clear_interaction()
        self._state = VoiceState.LISTENING
        logger.info("Voice: back to listening (interaction cancelled)")

    async def send(self, msg: OutboundMessage) -> None:
        """Speak a non-streaming outbound message via TTS."""
        if not self._tts or not msg.content:
            return

        if msg.chat_id == self._current_chat_id:
            self._state = VoiceState.PLAYING
            await asyncio.to_thread(self._tts.feed_text, msg.content)
            await asyncio.to_thread(self._tts.flush)
            await self._finish_turn("end")
            return

        repeat = (msg.metadata or {}).get("_reminder_repeat", 0)
        try:
            self._state = VoiceState.PLAYING
            for _ in range(repeat + 1):
                await asyncio.to_thread(self._tts.feed_text, msg.content)
                await asyncio.to_thread(self._tts.flush)
                await self._play_reminder_audio()
        finally:
            self._state = VoiceState.LISTENING

    async def _play_reminder_audio(self) -> None:
        """Play a 5 s segment of the reminder background music via sounddevice."""
        if self._reminder_pcm is None:
            return
        import sounddevice as sd
        data, sr = self._reminder_pcm
        chunk_len = int(5 * sr)
        chunk = data[:chunk_len]
        try:
            await asyncio.to_thread(
                sd.play,
                chunk,
                sr,
                device=self.config.output_device or None,
                blocking=True,
            )
        except Exception as e:
            logger.warning("Voice: sd.play reminder audio failed: {}", e)

    async def send_delta(self, chat_id: str, delta: str, metadata: dict[str, Any] | None = None) -> None:
        """Receive streaming output for the active voice interaction."""
        if chat_id != self._current_chat_id:
            return

        metadata = metadata or {}
        stream_id = metadata.get("_stream_id")
        if stream_id:
            if stream_id in self._closed_stream_ids:
                return
            if self._stream_id is None:
                self._stream_id = stream_id
            elif stream_id != self._stream_id:
                return

        if metadata.get("_voice_json_response"):
            reply_delta = self._reply_parser.feed(delta)
            if reply_delta:
                await self._feed_reply_delta(reply_delta)
            if not metadata.get("_stream_end"):
                return

            if metadata.get("_resuming", False):
                self._stream_id = None
                self._buf = ""
                self._reply_parser = ReplyStreamParser()
                return

            if stream_id:
                self._closed_stream_ids.add(stream_id)
            try:
                reply = VoiceReply.model_validate_json(self._reply_parser.raw_json)
            except ValueError:
                logger.warning(
                    "Voice: invalid JSON response: {}",
                    self._reply_parser.raw_json[:200],
                )
                dialogue_state = "end"
            else:
                dialogue_state = reply.dialogue_state
            await self._finish_streamed_reply(dialogue_state)
            return

        if metadata.get("_stream_end"):
            resuming = metadata.get("_resuming", False)
            if self._buf.strip():
                if self._state != VoiceState.PLAYING:
                    self._state = VoiceState.PLAYING
                await asyncio.to_thread(self._tts.feed_text, self._buf)
                self._buf = ""
            if not resuming:
                if stream_id:
                    self._closed_stream_ids.add(stream_id)
                await asyncio.to_thread(self._tts.flush)
                await self._finish_turn("continuous")
            else:
                self._stream_id = None
            return

        if not delta:
            return

        self._buf += delta
        parts = re.split(r"(?<=[。！？\n.!?])", self._buf)
        *complete, self._buf = parts

        for sentence in complete:
            sentence = sentence.strip()
            if not sentence:
                continue
            if self._state != VoiceState.PLAYING:
                self._state = VoiceState.PLAYING
                logger.info("Voice: started streaming TTS playback")
            await asyncio.to_thread(self._tts.feed_text, sentence)

    async def _feed_reply_delta(self, delta: str) -> None:
        self._buf += delta
        parts = re.split(r"(?<=[。！？\n.!?])", self._buf)
        *complete, self._buf = parts
        for sentence in complete:
            sentence = sentence.strip()
            if not sentence:
                continue
            if self._state != VoiceState.PLAYING:
                self._state = VoiceState.PLAYING
                logger.info("Voice: started streaming TTS playback")
            await asyncio.to_thread(self._tts.feed_text, sentence)

    async def _finish_streamed_reply(self, dialogue_state: str) -> None:
        if self._buf.strip():
            self._state = VoiceState.PLAYING
            await asyncio.to_thread(self._tts.feed_text, self._buf.strip())
        self._buf = ""
        self._reply_parser = ReplyStreamParser()
        await asyncio.to_thread(self._tts.flush)
        await self._finish_turn(dialogue_state)

    # ------------------------------------------------------------------
    # Audio callback (runs in PortAudio C thread)
    # ------------------------------------------------------------------

    def _audio_callback(self, indata: np.ndarray, _frames: int, _time: Any, status: Any) -> None:
        """Route audio to KWS or STT based on current state."""
        if status:
            logger.debug("Voice: audio status: {}", status)

        state = self._state

        if state == VoiceState.LISTENING:
            self._kws_detect(indata)
        elif state == VoiceState.RECOGNIZING:
            self._stt_feed(indata)
        # THINKING / PLAYING / STOPPED: discard audio

    def _kws_detect(self, indata: np.ndarray) -> None:
        """Run wake word detection on incoming audio."""
        samples = indata[:, 0] if indata.ndim > 1 else indata
        keyword = self._kws.detect(samples)
        if keyword:
            logger.info("Voice: wake word detected '{}'", keyword)
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self._on_wake(keyword), self._loop)

    def _stt_feed(self, indata: np.ndarray) -> None:
        """Feed audio to STT with VAD-based silence detection."""
        import numpy as np

        audio = indata[:, 0] if indata.ndim > 1 else indata
        pcm_bytes = (audio * 32767).astype(np.int16).tobytes()
        self._stt.send_audio_frame(pcm_bytes)
        if (
            self._speaker_verifier is not None
            and self._voice_member_id is None
            and sum(len(chunk) for chunk in self._speaker_audio) < SAMPLE_RATE * self.config.speaker_max_seconds
        ):
            self._speaker_audio.append(audio.copy())

        # VAD: reset the silence timer when audio energy exceeds the
        # noise floor so the 5s timeout measures actual silence rather
        # than DashScope processing latency.
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms > 0.02:  # ~ -34 dBFS — above room tone, below speech
            self._stt.reset_silence_timer()

        if self._stt.is_silence_timeout:
            timeout = (
                self.config.continuous_silence_timeout
                if self._continuous_dialogue
                else self.config.silence_timeout
            )
            logger.info("Voice: STT silence timeout ({:.0f}s)", timeout)
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self._on_timeout(), self._loop)

    # ------------------------------------------------------------------
    # Async event handlers
    # ------------------------------------------------------------------

    async def _on_wake(self, keyword: str) -> None:
        """Handle wake word detection: play sound, start STT."""
        if self._state != VoiceState.LISTENING:
            return

        self._current_chat_id = str(uuid.uuid4())
        self._session_key = f"voice:{self._current_chat_id}"
        self._stream_id = None
        self._closed_stream_ids.clear()
        self._buf = ""
        self._speaker_audio = []
        self._voice_member_id = None

        # Switch to PLAYING so mic input is discarded during wake sound
        self._state = VoiceState.PLAYING

        # Start STT first so it connects while the wake reply plays
        self._recognition_generation = self._stt.start(
            silence_timeout=self.config.silence_timeout
        )

        # Play wake reply from voice_dir (fall back to package assets)
        wake_reply = _resolve_voice_dir(self.config) / "audio" / "wake_reply.wav"
        if not wake_reply.exists():
            wake_reply = _ASSETS_DIR / "audio" / "wake_reply.wav"
        await self._play_file(wake_reply)

        # Start recording immediately — audio buffers locally until STT connects
        self._stt.reset_silence_timer()
        self._state = VoiceState.RECOGNIZING
        logger.info("Voice: listening for speech...")

    async def _on_timeout(self) -> None:
        """Handle STT silence timeout."""
        if self._state != VoiceState.RECOGNIZING:
            return
        self._clear_interaction()
        self._state = VoiceState.LISTENING
        bye = _resolve_voice_dir(self.config) / "audio" / "bye.wav"
        if not bye.exists():
            bye = _ASSETS_DIR / "audio" / "bye.wav"
        await self._play_file(bye)
        logger.info("Voice: back to listening (dialogue timeout)")

    # Called from STT callback thread
    def _on_sentence_end(self, text: str, generation: int) -> None:
        """STT callback: final sentence received. Bridge to asyncio."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._handle_query(text, generation), self._loop)

    async def _handle_query(self, text: str, generation: int) -> None:
        """Process recognized speech: check exit commands, publish to bus."""
        if (
            self._state != VoiceState.RECOGNIZING
            or generation != self._recognition_generation
            or not self._current_chat_id
        ):
            return

        # Stop STT (already got final result)
        self._stt.reset()
        self._recognition_generation = None

        # Check exit commands (exact match after stripping punctuation)
        clean = text.strip("，。！？、,.!? ")
        if clean in self.config.exit_commands:
            logger.info("Voice: exit command received '{}'", clean)
            self._clear_interaction()
            self._state = VoiceState.LISTENING
            bye = _resolve_voice_dir(self.config) / "audio" / "bye.wav"
            if not bye.exists():
                bye = _ASSETS_DIR / "audio" / "bye.wav"
            await self._play_file(bye)
            return

        self._stream_id = None
        self._buf = ""
        self._reply_parser = ReplyStreamParser()
        self._state = VoiceState.THINKING

        if self._voice_member_id is None:
            self._voice_member_id = await self._identify_speaker()

        # The voice output contract is part of the channel system prompt.
        content = text

        msg = InboundMessage(
            channel=self.name,
            sender_id="voice_user",
            chat_id=self._current_chat_id,
            content=content,
            ephemeral=False,
            session_key_override=self._session_key,
            metadata={
                "_wants_stream": True,
                "_new_turn": True,
                "_voice_json_response": True,
                "_response_format": {"type": "json_object"},
                "member_id": self._voice_member_id or "guest",
            },
        )

        logger.info("Voice: publishing query '{}'", text[:80])
        await self.bus.publish_inbound(msg)

    async def _identify_speaker(self) -> str:
        if self._speaker_verifier is None:
            return "guest"
        if not self._speaker_audio:
            return "guest"
        import numpy as np

        audio = np.concatenate(self._speaker_audio)
        if len(audio) < SAMPLE_RATE * self.config.speaker_min_seconds:
            logger.info("Voice: speaker sample too short; using guest profile")
            return "guest"
        try:
            member, score = await asyncio.to_thread(self._speaker_verifier.identify, audio)
        except Exception as e:
            logger.warning("Voice: speaker verification failed: {}", e)
            return "guest"
        logger.info("Voice: identified '{}' with score {:.3f}", member, score)
        return member

    async def _finish_turn(self, dialogue_state: str) -> None:
        """Apply the final reply's dialogue policy after playback."""
        self._stream_id = None
        self._buf = ""
        self._continuous_dialogue |= dialogue_state == "continuous"
        if dialogue_state == "end" and not self._continuous_dialogue:
            self._clear_interaction()
            self._state = VoiceState.LISTENING
            logger.info("Voice: back to listening (dialogue ended)")
            return

        timeout = (
            self.config.continuous_silence_timeout
            if self._continuous_dialogue
            else self.config.silence_timeout
        )
        self._recognition_generation = self._stt.start(silence_timeout=timeout)
        self._stt.reset_silence_timer()
        self._state = VoiceState.RECOGNIZING
        beep = _resolve_voice_dir(self.config) / "audio" / "beep.wav"
        if not beep.exists():
            beep = _BEEP_WAV
        await self._play_file(beep)
        self._stt.reset_silence_timer()
        logger.info("Voice: listening for next turn")

    def _clear_interaction(self) -> None:
        """Discard the current wake-word activation."""
        if self._stt:
            self._stt.reset()
        if self._session_key and self._session_cleanup:
            self._session_cleanup(self._session_key)
        self._current_chat_id = None
        self._session_key = None
        self._recognition_generation = None
        self._continuous_dialogue = False
        self._stream_id = None
        self._closed_stream_ids.clear()
        self._buf = ""
        self._reply_parser = ReplyStreamParser()
        self._speaker_audio = []
        self._voice_member_id = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _play_file(self, path: Path) -> None:
        """Play a WAV prompt on the configured output device."""
        if not path.exists():
            return
        import wave

        import numpy as np
        import sounddevice as sd

        with wave.open(str(path), "rb") as f:
            data = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).copy()
            channels = f.getnchannels()
            sample_rate = f.getframerate()
        if channels > 1:
            data = data.reshape(-1, channels)
        try:
            await asyncio.to_thread(
                sd.play,
                data,
                sample_rate,
                device=self.config.output_device or None,
                blocking=True,
            )
        except Exception as e:
            logger.warning("Voice: prompt playback failed: {}", e)


def _check_dependencies() -> None:
    """Log warnings for missing optional voice dependencies."""
    import importlib.util

    missing = []
    for mod in ("sounddevice", "numpy", "sherpa_onnx", "dashscope"):
        if importlib.util.find_spec(mod) is None:
            missing.append(mod)
    if missing:
        logger.warning(
            "Voice: missing dependencies: {}. Install with pip.", ", ".join(missing)
        )
