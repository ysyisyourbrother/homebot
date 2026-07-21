"""Wake word detection using sherpa-onnx KeywordSpotter."""

from pathlib import Path

import numpy as np
import sherpa_onnx


class WakeWordDetector:
    """Wraps sherpa-onnx KeywordSpotter for wake word detection."""

    def __init__(
        self,
        model_dir: str,
        keywords_file: str,
        *,
        num_threads: int = 1,
        provider: str = "cpu",
        max_active_paths: int = 8,
        keywords_score: float = 1.0,
        keywords_threshold: float = 0.02,
        num_trailing_blanks: int = 1,
    ):
        model_path = Path(model_dir)
        tokens = str(model_path / "tokens.txt")
        encoder = str(model_path / "encoder-epoch-13-avg-2-chunk-8-left-64.onnx")
        decoder = str(model_path / "decoder-epoch-13-avg-2-chunk-8-left-64.onnx")
        joiner = str(model_path / "joiner-epoch-13-avg-2-chunk-8-left-64.onnx")

        for path in [tokens, encoder, decoder, joiner, keywords_file]:
            if not Path(path).is_file():
                raise FileNotFoundError(f"KWS model file not found: {path}")

        self._spotter = sherpa_onnx.KeywordSpotter(
            tokens=tokens,
            encoder=encoder,
            decoder=decoder,
            joiner=joiner,
            num_threads=num_threads,
            provider=provider,
            max_active_paths=max_active_paths,
            keywords_file=keywords_file,
            keywords_score=keywords_score,
            keywords_threshold=keywords_threshold,
            num_trailing_blanks=num_trailing_blanks,
        )
        self._stream = self._spotter.create_stream()

    def reset(self) -> None:
        """Reset the KWS stream for a new detection cycle."""
        self._spotter.reset_stream(self._stream)

    @property
    def sample_rate(self) -> int:
        return 16000

    def detect(self, samples: np.ndarray) -> str | None:
        """Feed audio samples and return the detected keyword string, or None."""
        float_samples = samples.astype(np.float32)
        self._stream.accept_waveform(self.sample_rate, float_samples)

        while self._spotter.is_ready(self._stream):
            self._spotter.decode_stream(self._stream)

        result = self._spotter.get_result(self._stream)
        if result:
            self.reset()
        return result if result else None
