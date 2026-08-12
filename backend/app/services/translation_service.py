"""Provider-independent subtitle translation services."""

from abc import ABC, abstractmethod
import re
from typing import Any, Iterable, Mapping

from app.config.languages import require_supported_language
from app.config.translation import (
    normalize_glossary,
    translation_batch_size,
    translation_context_size,
    translation_global_transcript_max_segments,
    translation_review_enabled,
)


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

    def translate_segments(
        self,
        segments: list[dict[str, Any]],
        previous_context: list[dict[str, Any]] | None = None,
        next_context: list[dict[str, Any]] | None = None,
        global_transcript: list[dict[str, Any]] | None = None,
        global_context: Mapping[str, Any] | None = None,
        glossary: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Translate id/text objects, optionally informed by context and glossary."""
        return [
            {"id": segment["id"], "text": self.translate(segment["text"])}
            for segment in segments
        ]

    def build_global_context(
        self,
        segments: list[dict[str, Any]],
        glossary: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Analyze a long transcript once without generating subtitle text."""
        return {
            "topic": "",
            "domain": "",
            "people": [],
            "places": [],
            "organizations": [],
            "terminology": [],
            "language_notes": [],
        }

    def review_translations(
        self,
        source_segments: list[dict[str, Any]],
        translations: list[dict[str, Any]],
        previous_context: list[dict[str, Any]] | None = None,
        next_context: list[dict[str, Any]] | None = None,
        global_transcript: list[dict[str, Any]] | None = None,
        global_context: Mapping[str, Any] | None = None,
        glossary: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Review translated text without changing segment identity."""
        return translations


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


def _get_translator(source_language: str, target_language: str) -> Translator:
    """Create the configured DeepSeek translator."""
    from app.services.deepseek_translator import DeepSeekTranslator

    return DeepSeekTranslator(
        source_language=source_language,
        target_language=target_language,
    )


def translate_segments(
    segments: Iterable[Mapping[str, Any]],
    source_language: str,
    target_language: str = "zh",
    glossary: Mapping[str, str] | None = None,
    review_enabled: bool | None = None,
) -> list[dict[str, Any]]:
    """Translate Whisper text by stable ids while preserving its timeline."""
    source_language = require_supported_language(source_language, "source")
    target_language = require_supported_language(target_language, "target")

    source_segments = list(segments)
    prepared = [
        {
            "id": segment.get("id", index),
            "text": str(segment["text"]).strip(),
        }
        for index, segment in enumerate(source_segments)
    ]
    ids = [segment["id"] for segment in prepared]
    if len(ids) != len(set(ids)):
        raise ValueError("Source segment ids must be unique.")

    if source_language == target_language:
        return [
            {
                "id": segment.get("id", index),
                "start": segment["start"],
                "end": segment["end"],
                "text": str(segment["text"]).strip(),
            }
            for index, segment in enumerate(source_segments)
        ]

    glossary_items = normalize_glossary(glossary)
    translator = _get_translator(source_language, target_language)
    batch_size = translation_batch_size()
    context_size = translation_context_size()
    global_transcript_limit = translation_global_transcript_max_segments()
    should_review = (
        translation_review_enabled() if review_enabled is None else review_enabled
    )
    translated_by_id: dict[Any, str] = {}
    nonempty = [segment for segment in prepared if segment["text"]]
    use_global_transcript = len(prepared) <= global_transcript_limit
    global_transcript = prepared if use_global_transcript else []
    global_context = (
        {}
        if use_global_transcript
        else translator.build_global_context(nonempty, glossary=glossary_items)
    )
    for offset in range(0, len(nonempty), batch_size):
        batch = nonempty[offset : offset + batch_size]
        previous_context = nonempty[max(0, offset - context_size) : offset]
        next_context = nonempty[
            offset + batch_size : offset + batch_size + context_size
        ]
        translated_batch = translator.translate_segments(
            batch,
            previous_context=previous_context,
            next_context=next_context,
            global_transcript=global_transcript,
            global_context=global_context,
            glossary=glossary_items,
        )
        validate_translation_batch(batch, translated_batch, glossary_items)
        if should_review:
            translated_batch = review_translations(
                translator,
                batch,
                translated_batch,
                previous_context=previous_context,
                next_context=next_context,
                global_transcript=global_transcript,
                global_context=global_context,
                glossary=glossary_items,
            )
        for item in translated_batch:
            translated_by_id[item["id"]] = str(item["text"]).strip()

    for segment in prepared:
        if not segment["text"]:
            translated_by_id[segment["id"]] = ""

    result = [
        {
            "id": segment.get("id", index),
            "start": segment["start"],
            "end": segment["end"],
            "text": translated_by_id[segment.get("id", index)],
        }
        for index, segment in enumerate(source_segments)
    ]
    validate_timeline(source_segments, result)
    return result


def validate_translation_batch(
    source: list[dict[str, Any]],
    translated: list[dict[str, Any]],
    glossary: Mapping[str, str] | None = None,
) -> None:
    """Validate identity, completeness, text, terminology, and numeric fidelity."""
    expected = [item["id"] for item in source]
    try:
        actual = [item["id"] for item in translated]
        texts = [str(item["text"]).strip() for item in translated]
    except (KeyError, TypeError) as exc:
        raise TranslationError("Translator returned invalid translation objects.") from exc
    if any(set(item) != {"id", "text"} for item in translated):
        raise TranslationError("Translator may return only id and translated text.")
    if len(actual) != len(set(actual)):
        raise TranslationError("Translator returned duplicate segment ids.")
    if set(actual) != set(expected) or len(actual) != len(expected):
        raise TranslationError("Translator returned mismatched segment ids.")
    if any(not text for text in texts):
        raise TranslationError("Translator returned an empty translation.")
    translated_by_id = {
        item["id"]: str(item["text"]).strip() for item in translated
    }
    for source_item in source:
        source_text = str(source_item["text"])
        translated_text = translated_by_id[source_item["id"]]
        if _numeric_tokens(source_text) != _numeric_tokens(translated_text):
            raise TranslationError(
                f"Translation changed numbers or units for segment {source_item['id']!r}."
            )
        for term, preferred in (glossary or {}).items():
            if term.casefold() in source_text.casefold() and preferred not in translated_text:
                raise TranslationError(
                    f"Translation did not apply glossary term {term!r}."
                )


def review_translations(
    translator: Translator,
    source_segments: list[dict[str, Any]],
    translations: list[dict[str, Any]],
    previous_context: list[dict[str, Any]] | None = None,
    next_context: list[dict[str, Any]] | None = None,
    global_transcript: list[dict[str, Any]] | None = None,
    global_context: Mapping[str, Any] | None = None,
    glossary: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Optionally proofread text and revalidate the immutable segment contract."""
    reviewed = translator.review_translations(
        source_segments,
        translations,
        previous_context=previous_context,
        next_context=next_context,
        global_transcript=global_transcript,
        global_context=global_context,
        glossary=glossary,
    )
    validate_translation_batch(source_segments, reviewed, glossary)
    return reviewed


def validate_timeline(
    source_segments: list[Mapping[str, Any]],
    translated_segments: list[Mapping[str, Any]],
) -> None:
    """Ensure final id/start/end values are copied exactly from Whisper."""
    if len(source_segments) != len(translated_segments):
        raise TranslationError("Translated segment count does not match Whisper.")
    for index, (source, translated) in enumerate(
        zip(source_segments, translated_segments)
    ):
        source_id = source.get("id", index)
        if translated.get("id") != source_id:
            raise TranslationError("Translated segment ids do not match Whisper.")
        if translated.get("start") != source.get("start") or translated.get(
            "end"
        ) != source.get("end"):
            raise TranslationError("Translated timeline does not match Whisper.")


def _numeric_tokens(text: str) -> list[str]:
    return re.findall(
        r"\d+(?:[.,]\d+)?(?:\s?(?:%|°[CF]?|[A-Za-zµμΩ]+(?:/[A-Za-z]+)?))?",
        text,
    )
