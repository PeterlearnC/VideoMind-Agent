"""Whisper-based speech recognition service."""

from functools import lru_cache
from os import PathLike
from typing import Any


@lru_cache(maxsize=1)
def _get_model() -> Any:
    """Load and reuse the Whisper base model."""
    import whisper

    return whisper.load_model("base")


def transcribe_audio(audio_path: str | PathLike[str]) -> dict[str, Any]:
    """Transcribe an audio file and return its detected language and segments."""
    result = _get_model().transcribe(str(audio_path), fp16=False)

    return {
        "language": result["language"],
        "segments": result["segments"],
    }
