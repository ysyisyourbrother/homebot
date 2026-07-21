"""Voice subsystem: wake word detection, speech-to-text, and streaming text-to-speech.

Voice dependencies are imported lazily so the channel can be discovered and configured
without initializing audio or model components during package import.
"""

from homebot.voice.state import VoiceState  # noqa: E402

__all__ = ["VoiceState"]
