"""Canonical language codes and display metadata."""

from typing import Any


SUPPORTED_LANGUAGES: dict[str, dict[str, str]] = {
    "zh": {"name": "中文", "english_name": "Simplified Chinese"},
    "en": {"name": "English", "english_name": "English"},
    "ja": {"name": "日本語", "english_name": "Japanese"},
    "ko": {"name": "한국어", "english_name": "Korean"},
    "ru": {"name": "Русский", "english_name": "Russian"},
}

LANGUAGE_ALIASES = {
    "chinese": "zh",
    "zh-cn": "zh",
    "zh-hans": "zh",
    "english": "en",
    "japanese": "ja",
    "korean": "ko",
    "russian": "ru",
}


def normalize_language_code(value: Any) -> str:
    """Normalize a Whisper/API language value to one canonical code."""
    normalized = str(value).strip().lower().replace("_", "-")
    return LANGUAGE_ALIASES.get(normalized, normalized.split("-", 1)[0])


def require_supported_language(value: Any, role: str) -> str:
    """Return a canonical supported code or raise a clear validation error."""
    code = normalize_language_code(value)
    if code not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported {role} language: {code or value}")
    return code


def language_name(code: str) -> str:
    """Return the English prompt name for a canonical language code."""
    return SUPPORTED_LANGUAGES[code]["english_name"]


def default_target_language(source_language: str) -> str:
    """Preserve English-to-Chinese defaults and use English otherwise."""
    return "zh" if source_language == "en" else "en"
