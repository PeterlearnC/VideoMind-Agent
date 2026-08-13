"""Provider-independent subtitle translation services."""

from abc import ABC, abstractmethod
from collections import Counter
from decimal import Decimal, InvalidOperation
import logging
import re
from typing import Any, Iterable, Mapping

from app.config.languages import require_supported_language
from app.config.translation import (
    normalize_glossary,
    translation_batch_size,
    translation_context_size,
    translation_global_transcript_max_segments,
    translation_id_retry_count,
    translation_review_enabled,
)
from app.services.performance_metrics import get_active_run


DEEPSEEK_KEY_PLACEHOLDERS = {
    "your_api_key_here",
    "你的DeepSeek_API_KEY",
}
translation_logger = logging.getLogger("uvicorn.error.translation")

_NUMBER_PATTERN = re.compile(
    r"(?<![\w.])(?P<number>[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
    r"\s*(?P<unit>thousand|million|billion|percent|dollars?|minutes?|hours?|"
    r"years?|GB|MB|KB|十亿|百万|美元|分钟|小时|亿|万|千|年|%|mm|cm|km|m)?",
    re.IGNORECASE,
)

_UNIT_NORMALIZATION: dict[str, tuple[str, Decimal]] = {
    "thousand": ("number", Decimal("1000")),
    "千": ("number", Decimal("1000")),
    "million": ("number", Decimal("1000000")),
    "百万": ("number", Decimal("1000000")),
    "万": ("number", Decimal("10000")),
    "billion": ("number", Decimal("1000000000")),
    "十亿": ("number", Decimal("1000000000")),
    "亿": ("number", Decimal("100000000")),
    "percent": ("percent", Decimal("0.01")),
    "%": ("percent", Decimal("0.01")),
    "dollar": ("usd", Decimal("1")),
    "dollars": ("usd", Decimal("1")),
    "美元": ("usd", Decimal("1")),
    "minute": ("minutes", Decimal("1")),
    "minutes": ("minutes", Decimal("1")),
    "分钟": ("minutes", Decimal("1")),
    "hour": ("minutes", Decimal("60")),
    "hours": ("minutes", Decimal("60")),
    "小时": ("minutes", Decimal("60")),
    "gb": ("bytes", Decimal("1000000000")),
    "mb": ("bytes", Decimal("1000000")),
    "kb": ("bytes", Decimal("1000")),
    "mm": ("millimetres", Decimal("1")),
    "cm": ("millimetres", Decimal("10")),
    "m": ("millimetres", Decimal("1000")),
    "km": ("millimetres", Decimal("1000000")),
    "year": ("year", Decimal("1")),
    "years": ("year", Decimal("1")),
    "年": ("year", Decimal("1")),
}


class TranslationError(RuntimeError):
    """Raised when subtitle translation fails."""


class TranslationConfigurationError(TranslationError):
    """Raised when a translator is not configured correctly."""


class TranslationIdMismatch(TranslationError):
    """Structured batch-ID mismatch used for local recovery."""

    def __init__(self, diagnostics: Mapping[str, Any]) -> None:
        super().__init__("Translator returned mismatched segment ids.")
        self.diagnostics = dict(diagnostics)


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
    validation_warnings_by_id: dict[Any, str] = {}
    metrics = get_active_run()
    if metrics:
        metrics.set_stage_details(
            "translation",
            translation_validation_warning_count=0,
            translation_validation_retry_count=0,
            translation_validation_failure_count=0,
            translation_id_mismatch_count=0,
            translation_id_retry_batches=0,
            translation_id_retry_successes=0,
            translation_id_split_batches=0,
            translation_id_fallback_segments=0,
            translation_id_failed_segments=0,
            completed_batch_count=0,
        )
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
        batch_index = offset // batch_size + 1
        previous_context = nonempty[max(0, offset - context_size) : offset]
        next_context = nonempty[
            offset + batch_size : offset + batch_size + context_size
        ]
        context = dict(
            previous_context=previous_context,
            next_context=next_context,
            global_transcript=global_transcript,
            global_context=global_context,
            glossary=glossary_items,
        )
        translated_batch, warnings = _translate_batch_with_id_recovery(
            translator,
            batch,
            context,
            glossary_items,
            batch_index,
            metrics,
        )
        for warning in warnings:
            validation_warnings_by_id[warning["id"]] = warning["reason"]
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
        if metrics:
            metrics.set_stage_details(
                "translation", completed_batch_count=batch_index
            )

    for segment in prepared:
        if not segment["text"]:
            translated_by_id[segment["id"]] = ""

    result = [
        {
            "id": segment.get("id", index),
            "start": segment["start"],
            "end": segment["end"],
            "text": translated_by_id[segment.get("id", index)],
            **(
                {
                    "validation_warning": True,
                    "validation_warning_reason": validation_warnings_by_id[
                        segment.get("id", index)
                    ],
                }
                if segment.get("id", index) in validation_warnings_by_id
                else {}
            ),
        }
        for index, segment in enumerate(source_segments)
    ]
    validate_timeline(source_segments, result)
    return result


def validate_translation_batch(
    source: list[dict[str, Any]],
    translated: list[dict[str, Any]],
    glossary: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Validate identity, completeness, text, terminology, and numeric fidelity."""
    expected = [item["id"] for item in source]
    try:
        actual = [item["id"] for item in translated]
        texts = [str(item["text"]).strip() for item in translated]
    except (KeyError, TypeError) as exc:
        raise TranslationError("Translator returned invalid translation objects.") from exc
    if any(set(item) != {"id", "text"} for item in translated):
        raise TranslationError("Translator may return only id and translated text.")
    diagnostics = analyze_translation_ids(expected, actual)
    if diagnostics["has_mismatch"]:
        raise TranslationIdMismatch(diagnostics)
    if any(not text for text in texts):
        raise TranslationError("Translator returned an empty translation.")
    translated_by_id = {
        item["id"]: str(item["text"]).strip() for item in translated
    }
    warnings: list[dict[str, Any]] = []
    metrics = get_active_run()
    for source_item in source:
        source_text = str(source_item["text"])
        translated_text = translated_by_id[source_item["id"]]
        numeric_validation = validate_numeric_fidelity(source_text, translated_text)
        if numeric_validation["status"] == "failed":
            if metrics:
                metrics.increment_stage(
                    "translation", "translation_validation_failure_count"
                )
            raise TranslationError(
                f"Translation changed numbers or units for segment {source_item['id']!r}."
            )
        if numeric_validation["status"] == "warning":
            warning = {
                "id": source_item["id"],
                "reason": numeric_validation["reason"],
            }
            warnings.append(warning)
            if metrics:
                metrics.increment_stage(
                    "translation", "translation_validation_warning_count"
                )
            translation_logger.warning(
                "[TranslationValidation] warning segment_id=%s reason=%s",
                source_item["id"],
                numeric_validation["reason"],
            )
        for term, preferred in (glossary or {}).items():
            if term.casefold() in source_text.casefold() and preferred not in translated_text:
                raise TranslationError(
                    f"Translation did not apply glossary term {term!r}."
                )
    return warnings


def analyze_translation_ids(
    expected_ids: list[Any], returned_ids: list[Any]
) -> dict[str, Any]:
    """Classify translation ID errors without logging subtitle content."""
    expected_set = set(expected_ids)
    well_formed = [
        item for item in returned_ids if isinstance(item, (int, str))
        and not isinstance(item, bool)
    ]
    malformed_ids = [
        repr(item) for item in returned_ids
        if not isinstance(item, (int, str)) or isinstance(item, bool)
    ]
    counts = Counter(well_formed)
    duplicate_ids = [item for item, count in counts.items() if count > 1]
    returned_set = set(well_formed)
    missing_ids = [item for item in expected_ids if item not in returned_set]
    extra_ids = [item for item in well_formed if item not in expected_set]
    reordered = (
        not missing_ids
        and not extra_ids
        and not duplicate_ids
        and not malformed_ids
        and well_formed != expected_ids
    )
    mismatch = bool(missing_ids or extra_ids or duplicate_ids or malformed_ids)
    return {
        "expected_ids": list(expected_ids),
        "returned_ids": list(returned_ids),
        "missing_ids": missing_ids,
        "extra_ids": extra_ids,
        "duplicate_ids": duplicate_ids,
        "malformed_ids": malformed_ids,
        "reordered_ids": reordered,
        "has_mismatch": mismatch,
        "expected_segment_count": len(expected_ids),
        "returned_segment_count": len(returned_ids),
    }


def _ordered_validated_batch(
    source: list[dict[str, Any]],
    translated: list[dict[str, Any]],
    glossary: Mapping[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    warnings = validate_translation_batch(source, translated, glossary)
    translated_by_id = {item["id"]: item for item in translated}
    return [translated_by_id[item["id"]] for item in source], warnings


def _request_translation_batch(
    translator: Translator,
    batch: list[dict[str, Any]],
    context: Mapping[str, Any],
    *,
    retry_prompt: bool,
) -> list[dict[str, Any]]:
    retry_method = getattr(translator, "translate_segments_retry", None)
    if retry_prompt and callable(retry_method):
        return retry_method(batch, **context)
    return translator.translate_segments(batch, **context)


def _record_id_mismatch(metrics, batch_index: int, details: Mapping[str, Any]) -> None:
    translation_logger.warning(
        "[TranslationID] mismatch batch=%s expected=%s returned=%s "
        "missing=%s extra=%s duplicate=%s malformed=%s reordered=%s",
        batch_index,
        details["expected_ids"],
        details["returned_ids"],
        details["missing_ids"],
        details["extra_ids"],
        details["duplicate_ids"],
        details["malformed_ids"],
        details["reordered_ids"],
    )
    if metrics:
        metrics.increment_stage("translation", "translation_id_mismatch_count")
        metrics.set_stage_details(
            "translation",
            failed_batch_index=batch_index,
            expected_segment_count=details["expected_segment_count"],
            returned_segment_count=details["returned_segment_count"],
            missing_id_count=len(details["missing_ids"]),
            extra_id_count=len(details["extra_ids"]),
            duplicate_id_count=len(details["duplicate_ids"]),
            malformed_id_count=len(details["malformed_ids"]),
        )


def _translate_batch_with_id_recovery(
    translator: Translator,
    batch: list[dict[str, Any]],
    context: Mapping[str, Any],
    glossary: Mapping[str, str],
    batch_index: int,
    metrics,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    last_mismatch: TranslationIdMismatch | None = None
    attempts = translation_id_retry_count() + 1
    for attempt in range(attempts):
        translated = _request_translation_batch(
            translator, batch, context, retry_prompt=attempt > 0
        )
        try:
            ordered, warnings = _ordered_validated_batch(batch, translated, glossary)
            if attempt and metrics:
                metrics.increment_stage(
                    "translation", "translation_id_retry_successes"
                )
            return ordered, warnings
        except TranslationIdMismatch as exc:
            last_mismatch = exc
            _record_id_mismatch(metrics, batch_index, exc.diagnostics)
            if attempt + 1 < attempts and metrics:
                metrics.increment_stage(
                    "translation", "translation_id_retry_batches"
                )

    if len(batch) > 1:
        if metrics:
            metrics.increment_stage("translation", "translation_id_split_batches")
        midpoint = (len(batch) + 1) // 2
        combined: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        for part in (batch[:midpoint], batch[midpoint:]):
            try:
                translated = _request_translation_batch(
                    translator, part, context, retry_prompt=True
                )
                ordered, part_warnings = _ordered_validated_batch(
                    part, translated, glossary
                )
                combined.extend(ordered)
                warnings.extend(part_warnings)
            except TranslationIdMismatch as exc:
                _record_id_mismatch(metrics, batch_index, exc.diagnostics)
                for segment in part:
                    if metrics:
                        metrics.increment_stage(
                            "translation", "translation_id_fallback_segments"
                        )
                    try:
                        single = _request_translation_batch(
                            translator, [segment], context, retry_prompt=True
                        )
                        ordered, single_warnings = _ordered_validated_batch(
                            [segment], single, glossary
                        )
                        combined.extend(ordered)
                        warnings.extend(single_warnings)
                    except TranslationIdMismatch as single_exc:
                        _record_id_mismatch(metrics, batch_index, single_exc.diagnostics)
                        if metrics:
                            metrics.increment_stage(
                                "translation", "translation_id_failed_segments"
                            )
                        last_mismatch = single_exc
        if len(combined) == len(batch):
            by_id = {item["id"]: item for item in combined}
            return [by_id[item["id"]] for item in batch], warnings

    raise last_mismatch or TranslationError(
        "Translator returned mismatched segment ids after recovery."
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
    """Return raw number/unit expressions for validation diagnostics."""
    return [match.group(0).strip() for match in _NUMBER_PATTERN.finditer(text)]


def _numeric_quantities(text: str) -> list[dict[str, Any]]:
    quantities: list[dict[str, Any]] = []
    for match in _NUMBER_PATTERN.finditer(text):
        raw_number = match.group("number")
        raw_unit = match.group("unit") or ""
        try:
            number = Decimal(raw_number.replace(",", ""))
        except InvalidOperation:
            continue
        category, multiplier = _UNIT_NORMALIZATION.get(
            raw_unit.casefold(), ("number", Decimal("1"))
        )
        if category == "year":
            category = "number"
        quantities.append({
            "raw": match.group(0).strip(),
            "number": str(number),
            "unit": raw_unit or None,
            "category": category,
            "normalized_value": str((number * multiplier).normalize()),
        })
    return quantities


def _quantity_counter(quantities: list[dict[str, Any]]) -> Counter[tuple[str, str]]:
    return Counter(
        (item["category"], item["normalized_value"]) for item in quantities
    )


def validate_numeric_fidelity(source_text: str, translated_text: str) -> dict[str, Any]:
    """Compare semantic quantities, failing only proven numeric changes."""
    source = _numeric_quantities(source_text)
    translated = _numeric_quantities(translated_text)
    result = {
        "source_tokens": _numeric_tokens(source_text),
        "translated_tokens": _numeric_tokens(translated_text),
        "source_numbers": [item["number"] for item in source],
        "translated_numbers": [item["number"] for item in translated],
        "source_units": [item["unit"] for item in source],
        "translated_units": [item["unit"] for item in translated],
        "source_quantities": source,
        "translated_quantities": translated,
        "status": "passed",
        "reason": None,
    }
    if _quantity_counter(source) == _quantity_counter(translated):
        return result
    source_categories = Counter(item["category"] for item in source)
    translated_categories = Counter(item["category"] for item in translated)
    if len(source) == len(translated) and source_categories == translated_categories:
        result.update(status="failed", reason="normalized_numeric_value_changed")
    else:
        result.update(status="warning", reason="numeric_expression_not_comparable")
    return result


def _legacy_numeric_tokens(text: str) -> list[str]:
    return re.findall(
        r"\d+(?:[.,]\d+)?(?:\s?(?:%|°[CF]?|[A-Za-zµμΩ]+(?:/[A-Za-z]+)?))?",
        text,
    )
