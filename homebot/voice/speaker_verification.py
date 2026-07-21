"""Local speaker enrollment and verification helpers."""

from __future__ import annotations

import re
import wave
from pathlib import Path
from typing import Any

import numpy as np

SAMPLE_RATE = 16_000


def member_id(name: str, index: int) -> str:
    """Return a stable filesystem-safe member identifier."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or f"member-{index}"


def load_wav(path: Path) -> np.ndarray:
    """Load a 16-bit, 16 kHz WAV into normalized mono samples."""
    with wave.open(str(path), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        frames = wav_file.readframes(wav_file.getnframes())
    if sample_width != 2:
        raise ValueError(f"{path} must be 16-bit PCM WAV")
    if sample_rate != SAMPLE_RATE:
        raise ValueError(f"{path} must be {SAMPLE_RATE} Hz")
    audio = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return np.ascontiguousarray(audio)


def record_wav(path: Path, device: str | int | None = None) -> None:
    """Interactively record a 16-bit, mono, 16 kHz WAV."""
    import sounddevice as sd

    selected_device = sd.query_devices(device, "input")
    print(f"使用麦克风：{selected_device['name']}")
    input("按回车开始录音……")
    chunks: list[np.ndarray] = []

    def collect_audio(indata: np.ndarray, _frames: int, _time: Any, status: Any) -> None:
        if status:
            print(f"录音状态：{status}")
        chunks.append(indata.copy())

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        device=device,
        callback=collect_audio,
    ):
        input("正在录音，朗读完成后按回车结束……")

    if not chunks:
        raise RuntimeError("没有录制到音频")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(np.concatenate(chunks).tobytes())


def cosine_similarity(first: np.ndarray, second: np.ndarray) -> float:
    """Return cosine similarity for two speaker embeddings."""
    denominator = np.linalg.norm(first) * np.linalg.norm(second)
    if denominator == 0:
        raise ValueError("speaker embedding is empty")
    return float(np.dot(first, second) / denominator)


class SpeakerVerifier:
    """CAM++ speaker verifier backed by enrollment embeddings."""

    def __init__(self, model_path: Path, profiles: dict[str, list[Path]], threshold: float) -> None:
        import sherpa_onnx

        if not model_path.is_file():
            raise FileNotFoundError(f"speaker model not found: {model_path}")
        self._threshold = threshold
        self._profiles = {
            member: [
                np.asarray(np.load(path), dtype=np.float32)
                for path in paths
                if path.is_file()
            ]
            for member, paths in profiles.items()
        }
        self._profiles = {member: embeddings for member, embeddings in self._profiles.items() if embeddings}
        config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(model_path), num_threads=1, debug=False
        )
        self._extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)

    @classmethod
    def enrollment_path(cls, wav_path: Path) -> Path:
        return wav_path.with_suffix(".npy")

    def embedding(self, audio: np.ndarray) -> np.ndarray:
        stream = self._extractor.create_stream()
        stream.accept_waveform(SAMPLE_RATE, np.ascontiguousarray(audio, dtype=np.float32))
        stream.input_finished()
        return np.asarray(self._extractor.compute(stream), dtype=np.float32)

    def enroll_wav(self, wav_path: Path) -> Path:
        embedding_path = self.enrollment_path(wav_path)
        np.save(embedding_path, self.embedding(load_wav(wav_path)))
        return embedding_path

    def identify(self, audio: np.ndarray) -> tuple[str, float]:
        if not self._profiles:
            return "guest", 0.0
        embedding = self.embedding(audio)
        member, score = max(
            (
                (member, max(cosine_similarity(embedding, sample) for sample in samples))
                for member, samples in self._profiles.items()
            ),
            key=lambda result: result[1],
        )
        return (member, score) if score >= self._threshold else ("guest", score)
