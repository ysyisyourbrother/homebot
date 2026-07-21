"""Streaming text-to-speech via DashScope CosyVoice with real-time PCM playback."""

import collections
import threading

import dashscope
import numpy as np
import sounddevice as sd
from dashscope.audio.tts_v2 import AudioFormat, ResultCallback, SpeechSynthesizer
from loguru import logger


class StreamingTTS:
    """DashScope CosyVoice streaming TTS with real-time audio playback.

    The ``sounddevice.OutputStream`` is opened once in :meth:`start` and kept
    alive for the channel lifetime.  The DashScope ``SpeechSynthesizer`` is
    created lazily on the first :meth:`feed_text` of each conversation turn,
    and closed after :meth:`flush`, so a fresh WebSocket handles the next turn.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "cosyvoice-v3-flash",
        voice: str = "longanyang",
        sample_rate: int = 24000,
        output_device: str | None = None,
    ):
        dashscope.api_key = api_key
        self._model = model
        self._voice = voice
        self._sample_rate = sample_rate
        self._output_device = output_device or None

        self._buffer: collections.deque[bytes] = collections.deque()
        self._lock = threading.Lock()
        self._all_done = threading.Event()
        self._error: str | None = None
        self._draining = False

        self._synthesizer: SpeechSynthesizer | None = None
        self._stream: sd.OutputStream | None = None

    # ---- public API --------------------------------------------------

    def start(self) -> None:
        """Open the output audio stream.  Synthesizer is created lazily."""
        self._all_done.clear()
        self._error = None
        self._draining = False

        if self._stream is None:
            self._stream = sd.OutputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="int16",
                device=self._output_device,
                callback=self._audio_callback,
                blocksize=1024,
            )
            self._stream.start()

    def feed_text(self, text: str) -> None:
        """Send a text chunk for synthesis.  Creates the synthesizer lazily."""
        if self._error:
            return

        if self._synthesizer is None:
            self._draining = False
            self._all_done.clear()
            self._synthesizer = SpeechSynthesizer(
                model=self._model,
                voice=self._voice,
                format=AudioFormat.PCM_24000HZ_MONO_16BIT,
                callback=_TTSCallback(self),
            )

        synthesizer = self._synthesizer
        try:
            synthesizer.streaming_call(text)
        except Exception as exc:
            logger.warning("StreamingTTS: streaming_call failed: {}", exc)
            self._error = str(exc)

    def flush(self) -> None:
        """Signal end-of-input, wait for audio to drain, then close the synthesizer."""
        synthesizer = self._synthesizer
        if self._error or synthesizer is None:
            return

        try:
            synthesizer.streaming_complete()
        except Exception as exc:
            msg = str(exc)
            if "has not been started" in msg:
                return
            logger.warning("StreamingTTS: streaming_complete failed: {}", exc)
            self._error = msg
            return

        self._all_done.wait()
        synthesizer.close()
        if self._synthesizer is synthesizer:
            self._synthesizer = None  # will be recreated on next feed_text

    def stop(self) -> None:
        """Cancel synthesis and close both synthesizer and output stream."""
        self._all_done.set()
        if self._synthesizer:
            try:
                self._synthesizer.streaming_cancel()
            except Exception:
                pass
            try:
                self._synthesizer.close()
            except Exception:
                pass
            self._synthesizer = None
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        with self._lock:
            self._buffer.clear()

    @property
    def has_error(self) -> bool:
        return self._error is not None

    # ---- internal ----------------------------------------------------

    def _audio_callback(self, outdata: np.ndarray, frames: int, _time, status) -> None:
        """PortAudio callback — pull PCM bytes from ring buffer."""
        needed = frames * 2  # int16 mono
        data = bytearray()
        with self._lock:
            while self._buffer and len(data) < needed:
                data.extend(self._buffer.popleft())
        if len(data) >= needed:
            outdata[:, 0] = np.frombuffer(data[:needed], dtype=np.int16)
            if len(data) > needed:
                with self._lock:
                    self._buffer.appendleft(bytes(data[needed:]))
        else:
            outdata.fill(0)
            if self._draining:
                self._all_done.set()


class _TTSCallback(ResultCallback):
    """Bridge DashScope WebSocket events → StreamingTTS ring buffer."""

    def __init__(self, parent: StreamingTTS):
        super().__init__()
        self._parent = parent

    def on_open(self) -> None:
        logger.info("StreamingTTS: CosyVoice connected")

    def on_close(self) -> None:
        logger.info("StreamingTTS: CosyVoice disconnected")

    def on_data(self, data: bytes) -> None:
        with self._parent._lock:
            self._parent._buffer.append(data)

    def on_complete(self) -> None:
        logger.info("StreamingTTS: synthesis complete")
        self._parent._draining = True

    def on_error(self, message: str) -> None:
        logger.warning("StreamingTTS: error: {}", message)
        self._parent._error = message
        self._parent._all_done.set()
