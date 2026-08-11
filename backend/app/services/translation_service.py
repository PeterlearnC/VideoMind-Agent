"""Provider-independent subtitle translation services."""

from abc import ABC, abstractmethod
from typing import Any, Iterable, Mapping


BATCH_SIZE = 15
DEEPSEEK_KEY_PLACEHOLDERS = {
    "your_api_key_here",
    "你的DeepSeek_API_KEY",
}


class TranslationError(RuntimeError):
    """Raised when subtitle translation fails."""


class TranslationConfigurationError(TranslationError):
    """Raised when a translator is not configured correctly."""


class Translator(ABC):
    """Interface implemented by text translation providers."""

    @abstractmethod
    def translate(self, text: str) -> str:
        """Translate one subtitle string."""
        raise NotImplementedError

    def translate_batch(self, texts: list[str]) -> list[str]:
        """Translate multiple strings, with a per-item provider fallback."""
        return [self.translate(text) for text in texts]


class MockTranslator(Translator):
    """Deterministic fallback used when DeepSeek is not configured."""

    def __init__(self, translations: Mapping[str, str] | None = None) -> None:
        self.translations = dict(translations or {})

    def translate(self, text: str) -> str:
        """Return a configured translation or an explicit mock placeholder."""
        return self.translations.get(text, f"模拟翻译：{text}")


class LocalModelTranslator(Translator):
    """Extension point for a future local translation model."""

    def translate(self, text: str) -> str:
        """Translate text after a local model implementation is configured."""
        raise NotImplementedError("Local translation model is not configured.")


def _is_english(language: str) -> bool:
    normalized = language.strip().lower().replace("_", "-")
    return normalized == "english" or normalized.split("-", 1)[0] == "en"


def _get_translator(target_language: str) -> Translator:
    """Create the configured DeepSeek translator."""
    from app.services.deepseek_translator import DeepSeekTranslator

    return DeepSeekTranslator(target_language=target_language)


def translate_segments(
    segments: Iterable[Mapping[str, Any]],
    source_language: str,
    target_language: str = "zh",
) -> list[dict[str, Any]]:
    """Translate English Whisper segments while preserving their timestamps."""
    source_segments = list(segments)
    translator = _get_translator(target_language) if _is_english(source_language) else None
    translated_texts = [str(segment["text"]).strip() for segment in source_segments]

    if translator is not None:
        nonempty_indices = [
            index for index, text in enumerate(translated_texts) if text
        ]
        for offset in range(0, len(nonempty_indices), BATCH_SIZE):
            batch_indices = nonempty_indices[offset : offset + BATCH_SIZE]
            batch_texts = [translated_texts[index] for index in batch_indices]
            batch_translations = translator.translate_batch(batch_texts)
            if len(batch_translations) != len(batch_indices):
                raise TranslationError(
                    "Translator returned an unexpected number of translations."
                )
            for index, translation in zip(batch_indices, batch_translations):
                translated_texts[index] = translation

    return [
        {
            "id": segment.get("id", index),
            "start": segment["start"],
            "end": segment["end"],
            "text": translated_texts[index],
        }
        for index, segment in enumerate(source_segments)
    ]
