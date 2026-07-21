"""Real-time speech-to-text via DashScope paraformer-realtime-v2."""

import threading
import time

import dashscope
from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult
from loguru import logger


class RealtimeSTT:
    """Streaming speech recognition backed by DashScope paraformer-realtime-v2."""

    def __init__(
        self,
        api_key: str,
        *,
        sample_rate: int = 16000,
        max_sentence_silence: int = 2000,
        silence_timeout: float = 5.0,
        on_sentence_end: callable = None,
    ):
        dashscope.api_key = api_key
        self._sample_rate = sample_rate
        self._max_sentence_silence = max_sentence_silence
        self._silence_timeout = silence_timeout
        self._on_sentence_end = on_sentence_end

        self._recognition: Recognition | None = None
        self._ready = False
        self._speech_started = False
        self._lock = threading.Lock()
        self._last_voice_time = 0.0
        self._pending_audio: list[bytes] = []
        self._pending_lock = threading.Lock()
        self._callback = None
        self._generation = 0

    class _STTCallback(RecognitionCallback):
        def __init__(self, parent: "RealtimeSTT", generation: int):
            self._parent = parent
            self._generation = generation

        def on_open(self) -> None:
            if self._generation == self._parent._generation:
                self._parent._ready = True

        def on_close(self) -> None:
            if self._generation == self._parent._generation:
                self._parent._ready = False

        def on_event(self, result: RecognitionResult) -> None:
            if self._generation != self._parent._generation:
                return
            sentence = result.get_sentence()
            if not sentence:
                return
            text = sentence.get("text", "")
            if not text:
                return
            self._parent._speech_started = True
            if sentence.get("sentence_end"):
                final = text.strip()
                logger.info("Voice STT final: {}", final)
                if self._parent._on_sentence_end:
                    self._parent._on_sentence_end(final, self._generation)

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def is_silence_timeout(self) -> bool:
        if self._speech_started:
            return False
        return time.time() - self._last_voice_time > self._silence_timeout

    def start(self, *, silence_timeout: float | None = None) -> int:
        if silence_timeout is not None:
            self._silence_timeout = silence_timeout
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._ready = False
            self._speech_started = False
            with self._pending_lock:
                self._pending_audio.clear()
            self._callback = self._STTCallback(self, generation)
            self._recognition = Recognition(
                model="paraformer-realtime-v2",
                format="pcm",
                sample_rate=self._sample_rate,
                callback=self._callback,
                max_sentence_silence=self._max_sentence_silence,
                semantic_punctuation_enabled=False,
                language_hints=["zh"],
            )
            self._recognition.start()
            return generation

    def stop(self) -> None:
        with self._lock:
            self._ready = False
            with self._pending_lock:
                self._pending_audio.clear()
            try:
                if self._recognition:
                    self._recognition.stop()
                    self._recognition = None
            except Exception as e:
                logger.debug("STT stop error (can be ignored): {}", e)

    def reset(self) -> None:
        self.stop()

    def reset_silence_timer(self) -> None:
        """Reset the silence timeout clock. Call when user should start speaking."""
        self._last_voice_time = time.time()

    def send_audio_frame(self, pcm_bytes: bytes) -> None:
        with self._pending_lock:
            if not self._ready or not self._recognition:
                self._pending_audio.append(pcm_bytes)
                return
            if self._pending_audio:
                for pending in self._pending_audio:
                    try:
                        self._recognition.send_audio_frame(pending)
                    except Exception:
                        pass
                self._pending_audio.clear()
        try:
            self._recognition.send_audio_frame(pcm_bytes)
        except Exception as e:
            logger.warning("Voice STT: send_audio_frame failed: {}", e)
