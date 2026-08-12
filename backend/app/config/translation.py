"""Configuration for contextual subtitle translation."""

import json
import os
from typing import Mapping


DEFAULT_BATCH_SIZE = 15
DEFAULT_CONTEXT_SIZE = 5
DEFAULT_GLOBAL_TRANSCRIPT_MAX_SEGMENTS = 80


def translation_batch_size() -> int:
    """Return the configured current-batch size."""
    return _positive_int("TRANSLATION_BATCH_SIZE", DEFAULT_BATCH_SIZE)


def translation_context_size() -> int:
    """Return the number of neighboring cues supplied as read-only context."""
    return _nonnegative_int("TRANSLATION_CONTEXT_SIZE", DEFAULT_CONTEXT_SIZE)


def translation_global_transcript_max_segments() -> int:
    """Return the largest track sent in full with every translation batch."""
    return _positive_int(
        "TRANSLATION_GLOBAL_TRANSCRIPT_MAX_SEGMENTS",
        DEFAULT_GLOBAL_TRANSCRIPT_MAX_SEGMENTS,
    )


def translation_review_enabled() -> bool:
    """Return whether an additional DeepSeek proofreading pass is enabled."""
    return os.getenv("TRANSLATION_REVIEW_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def load_translation_glossary() -> dict[str, str]:
    """Load a general source-to-target glossary from a JSON object environment value."""
    raw = os.getenv("TRANSLATION_GLOSSARY_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("TRANSLATION_GLOSSARY_JSON must be valid JSON.") from exc
    if not isinstance(parsed, dict) or any(
        not isinstance(source, str)
        or not source.strip()
        or not isinstance(target, str)
        or not target.strip()
        for source, target in parsed.items()
    ):
        raise ValueError(
            "TRANSLATION_GLOSSARY_JSON must be an object of non-empty string pairs."
        )
    return {source.strip(): target.strip() for source, target in parsed.items()}


def normalize_glossary(glossary: Mapping[str, str] | None) -> dict[str, str]:
    """Normalize an explicitly supplied glossary or load the configured one."""
    if glossary is None:
        return load_translation_glossary()
    if any(not str(source).strip() or not str(target).strip() for source, target in glossary.items()):
        raise ValueError("Glossary entries must contain non-empty source and target text.")
    return {str(source).strip(): str(target).strip() for source, target in glossary.items()}


def _positive_int(name: str, default: int) -> int:
    value = _nonnegative_int(name, default)
    if value == 0:
        raise ValueError(f"{name} must be greater than zero.")
    return value


def _nonnegative_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value < 0:
        raise ValueError(f"{name} must not be negative.")
    return value
