"""Configuration for full-context ASR transcript correction."""

import os


DEFAULT_CORRECTION_BATCH_SIZE = 40
DEFAULT_CORRECTION_CONTEXT_SIZE = 5
DEFAULT_GLOBAL_CONTEXT_THRESHOLD = 150
DEFAULT_GLOBAL_CONTEXT_MAX_CHARS = 12000


def transcript_correction_enabled() -> bool:
    """Return whether DeepSeek ASR correction is enabled."""
    return os.getenv("TRANSCRIPT_CORRECTION_ENABLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def transcript_correction_batch_size() -> int:
    """Return the number of current segments corrected per request."""
    return _configured_int(
        "TRANSCRIPT_CORRECTION_BATCH_SIZE", DEFAULT_CORRECTION_BATCH_SIZE, 1
    )


def transcript_correction_context_size() -> int:
    """Return the number of neighboring segments supplied on each side."""
    return _configured_int(
        "TRANSCRIPT_CORRECTION_CONTEXT_SIZE", DEFAULT_CORRECTION_CONTEXT_SIZE, 0
    )


def transcript_global_context_threshold() -> int:
    """Return the segment count above which compact global context is attempted."""
    return _configured_int(
        "TRANSCRIPT_GLOBAL_CONTEXT_THRESHOLD",
        DEFAULT_GLOBAL_CONTEXT_THRESHOLD,
        1,
    )


def transcript_global_context_max_chars() -> int:
    """Return the maximum full-transcript characters sent with correction batches."""
    return _configured_int(
        "TRANSCRIPT_GLOBAL_CONTEXT_MAX_CHARS",
        DEFAULT_GLOBAL_CONTEXT_MAX_CHARS,
        1,
    )


def _configured_int(name: str, default: int, minimum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return value
