"""Streaming text-to-speech via DashScope CosyVoice with real-time PCM playback."""

import collections
import threading
import time

import dashscope
import numpy as np
import sounddevice as sd
from dashscope.audio.tts_v2 import AudioFormat, ResultCallback, SpeechSynthesizer
from loguru import logger


def _resolve_output_device(name: str | None) -> str | None:
    """Resolve an output device name, falling back to system default if unavailable."""
    if not name:
        return None
    try:
        sd.query_devices(device=name)
    except Exception:
        logger.warning(
            "StreamingTTS: configured output device '{}' not found, falling back to system default",
            name,
        )
        return None
    return name


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

        # One speaking turn runs from the first feed_text to the matching
        # flush.  Tracking it explicitly (instead of testing for a missing
        # synthesizer) keeps a mid-turn failure from looking like a brand new
        # turn and reconnecting over and over.
        self._turn_open = False
        self._retries = 2
        self._retry_delay = 1.0

    # ---- public API --------------------------------------------------

    def start(self) -> None:
        """Open the output audio stream.  Synthesizer is created lazily."""
        self._all_done.clear()
        self._error = None
        self._draining = False

        if self._stream is None:
            device = _resolve_output_device(self._output_device)
            self._stream = sd.OutputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="int16",
                device=device,
                callback=self._audio_callback,
                blocksize=1024,
            )
            self._stream.start()

    def feed_text(self, text: str) -> None:
        """Send a text chunk for synthesis.  Creates the synthesizer lazily."""
        if not self._turn_open:
            # New turn: start from a clean slate.  Without this a single
            # transient failure silenced every later reply until restart.
            self._turn_open = True
            self._error = None
            self._draining = False
            self._all_done.clear()

        if self._error:
            return

        for attempt in range(1, self._retries + 1):
            if self._synthesizer is None:
                self._synthesizer = SpeechSynthesizer(
                    model=self._model,
                    voice=self._voice,
                    format=AudioFormat.PCM_24000HZ_MONO_16BIT,
                    callback=_TTSCallback(self),
                )
            try:
                self._synthesizer.streaming_call(text)
                return
            except Exception as exc:
                logger.warning(
                    "StreamingTTS: streaming_call failed (attempt {}/{}): {}",
                    attempt,
                    self._retries,
                    exc,
                )
                self._discard_synthesizer()
                if attempt < self._retries:
                    time.sleep(self._retry_delay)
        self._error = "streaming_call failed after retries"

    def flush(self) -> None:
        """Signal end-of-input, wait for audio to drain, then close the synthesizer."""
        synthesizer = self._synthesizer
        try:
            if synthesizer is None:
                return
            if self._error:
                logger.warning("StreamingTTS: turn produced no audio: {}", self._error)
                return
            try:
                synthesizer.streaming_complete()
            except Exception as exc:
                msg = str(exc)
                if "has not been started" in msg:
                    return
                logger.warning("StreamingTTS: streaming_complete failed: {}", exc)
                return
            self._all_done.wait()
            if self._error:
                logger.warning("StreamingTTS: playback ended early: {}", self._error)
        finally:
            # Either way the turn is over: drop the synthesizer and forget the
            # per-turn error so the next reply starts from a clean slate.
            self._discard_synthesizer()
            self._turn_open = False
            self._error = None

    def _discard_synthesizer(self) -> None:
        """Drop the current synthesizer, closing it if it is still around."""
        synthesizer, self._synthesizer = self._synthesizer, None
        if synthesizer is None:
            return
        try:
            synthesizer.close()
        except Exception:
            pass

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
