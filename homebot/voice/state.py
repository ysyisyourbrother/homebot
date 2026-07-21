"""Voice channel state machine."""

from enum import Enum


class VoiceState(Enum):
    """States for the voice channel audio pipeline."""

    LISTENING = "listening"      # Waiting for wake word
    PLAYING = "playing"          # TTS playback in progress
    RECOGNIZING = "recognizing"  # STT capturing user speech
    THINKING = "thinking"        # Agent processing
    STOPPED = "stopped"          # Channel shut down
