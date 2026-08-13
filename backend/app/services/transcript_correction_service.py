"""Observable, full-context DeepSeek correction for Whisper ASR transcripts."""

from dataclasses import dataclass
import json
import logging
import math
import os
import re
from typing import Any, Iterable, Mapping

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config.languages import language_name, require_supported_language
from app.config.transcript_correction import (
    transcript_correction_batch_size,
    transcript_correction_context_size,
    transcript_correction_enabled,
    transcript_global_context_max_chars,
    transcript_global_context_threshold,
)
from app.services.translation_service import DEEPSEEK_KEY_PLACEHOLDERS


# Uvicorn does not install a root handler for arbitrary application loggers.
# Use its error logger hierarchy so INFO diagnostics are visible beside access logs.
logger = logging.getLogger("uvicorn.error.transcript_correction")
logger.setLevel(logging.INFO)
LOG_PREFIX = "[TranscriptCorrection]"
ZERO_CHANGE_WARNING_MIN_SEGMENTS = 20


def _redact_secret(message: object, secret: str | None) -> str:
    """Prevent provider credentials from reaching logs or persisted metadata."""
    text = str(message)
    return text.replace(secret, "[REDACTED]") if secret else text


class TranscriptCorrectionError(RuntimeError):
    """Raised when an ASR correction result is invalid or unavailable."""


class CorrectionResponseError(TranscriptCorrectionError):
    """A retryable model-output syntax or schema failure."""


class CorrectedSegment(BaseModel):
    """One corrected text value keyed to an immutable Whisper segment id."""

    model_config = ConfigDict(extra="forbid")

    id: int | str
    corrected_text: str = Field(min_length=1)


class CorrectionBatch(BaseModel):
    """Structured DeepSeek correction response."""

    model_config = ConfigDict(extra="forbid")

    corrections: list[CorrectedSegment]


class ContextTerm(BaseModel):
    """One transcript-supported name or term used for ASR disambiguation."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    canonical: str = Field(min_length=1)


class TranscriptGlobalContext(BaseModel):
    """Reusable context extracted once for a long raw transcript."""

    model_config = ConfigDict(extra="forbid")

    topic: str
    domain: str
    people: list[ContextTerm]
    places: list[ContextTerm]
    organizations: list[ContextTerm]
    terminology: list[ContextTerm]
    context_notes: list[str]


@dataclass(frozen=True)
class TranscriptCorrectionResult:
    """Corrected Whisper segments plus safe diagnostic metadata."""

    segments: list[dict[str, Any]]
    metadata: dict[str, Any]


class DeepSeekTranscriptCorrector:
    """Correct ASR text using full or reusable transcript context."""

    API_URL = "https://api.deepseek.com/chat/completions"
    MODEL = "deepseek-chat"
    REQUEST_TIMEOUT_SECONDS = 120

    def __init__(self, api_key: str | None = None, session: Any | None = None) -> None:
        if api_key is None:
            api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key or not api_key.strip() or api_key in DEEPSEEK_KEY_PLACEHOLDERS:
            raise TranscriptCorrectionError(
                "DEEPSEEK_API_KEY must contain a valid API key for transcript correction."
            )
        self.api_key = api_key
        self.session = session or requests

    def correct_batch(
        self,
        detected_language: str,
        current_batch: list[dict[str, Any]],
        previous_context: list[dict[str, Any]],
        next_context: list[dict[str, Any]],
        global_transcript: list[dict[str, Any]],
        global_context: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        """Correct only current_batch and return id/corrected_text objects."""
        prompt = (
            "You are an ASR Transcript Proofreader, not a translator. The input is a "
            "Whisper automatic speech recognition transcript in "
            f"{language_name(detected_language)}. Correct clear recognition mistakes "
            "using the complete video context, surrounding sentences, topic, natural "
            "language usage, homophones, professional terminology, and well-supported "
            "people, place, and organization names. Be active rather than overly "
            "conservative when context makes an ASR error clear. For example, Chinese "
            "homophone errors such as 售命→寿命, 两马事儿→两码事儿, and 横量→横梁 "
            "should be corrected when supported by context. You may correct obvious "
            "misheard words, proper nouns, punctuation, and capitalization. Do not "
            "translate, summarize, expand, change meaning, invent facts, delete important "
            "information, merge or split segments, change ids or order, or output "
            "timestamps. global_transcript/global_context and previous/next context are "
            "read-only. Do not modify facts or numbers unless context clearly proves an "
            "ASR recognition error. Return exactly one valid JSON object and no other "
            "text. Do not use markdown or ```json fences. Do not include explanations "
            "before or after the JSON. The object must have exactly one corrections "
            "array. Its length must equal the current_batch length. Return every and "
            "only current_batch id, preserving each id exactly and exactly once. Every "
            "corrected_text must be a non-empty string. Each item must contain only id "
            "and corrected_text. Do not output start or end. Required shape: "
            '{"corrections":[{"id":0,"corrected_text":"..."}]}.'
        )
        request_content = {
            "detected_language": detected_language,
            "global_transcript": global_transcript,
            "global_context": dict(global_context),
            "previous_context": previous_context,
            "current_batch": current_batch,
            "next_context": next_context,
        }
        content = self._request(prompt, request_content, "transcript correction")
        return self._parse_corrections(content)

    def retry_correction_batch(
        self,
        detected_language: str,
        current_batch: list[dict[str, Any]],
        previous_context: list[dict[str, Any]],
        next_context: list[dict[str, Any]],
        global_context: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        """Retry an invalid model response with an explicit, isolated contract."""
        required_ids = [item["id"] for item in current_batch]
        prompt = (
            "You are an ASR Transcript Proofreader. This is a retry because the "
            "previous response violated the required JSON or segment contract. "
            "Return exactly one valid JSON object and no other text. Do not use markdown "
            "or ```json fences. Do not include any explanation. You MUST return exactly "
            f"these IDs and no others: {json.dumps(required_ids, ensure_ascii=False)}. "
            "Return every listed id exactly once. Do not return previous_context ids. "
            "Do not return next_context ids. Do not return global transcript ids outside "
            "current_batch. Do not change id values, omit any id, or duplicate any id. "
            "The corrections array length MUST equal the current_batch length. Every "
            "corrected_text must be a non-empty string. Output only corrections for "
            "current_batch. Each item contains only id and corrected_text; never output "
            "start or end. Preserve meaning and facts; do not translate, summarize, "
            "polish beyond ASR correction, merge, split, or invent content. Required "
            'shape: {"corrections":[{"id":0,"corrected_text":"..."}]}.'
        )
        request_content = {
            "detected_language": detected_language,
            "required_ids": required_ids,
            "global_context": dict(global_context),
            "previous_context": [
                {"text": item["text"]} for item in previous_context
            ],
            "current_batch": current_batch,
            "next_context": [{"text": item["text"]} for item in next_context],
        }
        content = self._request(prompt, request_content, "transcript correction retry")
        return self._parse_corrections(content)

    def build_global_context(
        self, detected_language: str, transcript: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Analyze a long raw transcript once without correcting segment text."""
        prompt = (
            "Build read-only context for proofreading a long Whisper ASR transcript in "
            f"{language_name(detected_language)}. Do not correct or reproduce segments, "
            "translate, summarize for display, output timestamps, change ids, or invent "
            "facts. Identify only transcript-supported topic/domain hints, people, "
            "places, organizations, terminology, and context notes useful for resolving "
            "ASR homophones and recognition errors. Return exactly topic, domain, people, "
            "places, organizations, terminology, and context_notes. Named entries contain "
            "only source and canonical. Return one valid JSON object and no other text."
        )
        content = self._request(
            prompt,
            {"detected_language": detected_language, "transcript": transcript},
            "global transcript context",
        )
        return self._parse_global_context(content)

    def _request(
        self, prompt: str, request_content: dict[str, Any], operation: str
    ) -> Any:
        payload = {
            "model": self.MODEL,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(request_content, ensure_ascii=False)},
            ],
        }
        if operation in {"transcript correction", "transcript correction retry"}:
            payload["temperature"] = 0
        response: Any | None = None
        try:
            response = self.session.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            try:
                response_payload = response.json()
            except (TypeError, ValueError) as exc:
                raise TranscriptCorrectionError(
                    f"DeepSeek {operation} response body is not valid JSON."
                ) from exc
            try:
                choices = response_payload["choices"]
                if not isinstance(choices, list) or not choices:
                    raise KeyError("choices")
                message = choices[0]["message"]
                content = message["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise TranscriptCorrectionError(
                    f"DeepSeek {operation} response is missing choices[0].message.content."
                ) from exc
            if not isinstance(content, str) or not content.strip():
                raise CorrectionResponseError(
                    "DeepSeek correction response content is empty."
                )
            return content
        except TranscriptCorrectionError:
            raise
        except requests.RequestException as exc:
            status_code = getattr(response, "status_code", None)
            response_text = _redact_secret(
                getattr(response, "text", ""), self.api_key
            ).strip()
            if status_code is not None:
                detail = f"HTTP {status_code}"
                if response_text:
                    detail += f": {response_text}"
                if operation == "global transcript context":
                    logger.warning("%s global context %s", LOG_PREFIX, detail)
                raise TranscriptCorrectionError(
                    f"DeepSeek {operation} failed: {detail}"
                ) from exc
            raise TranscriptCorrectionError(
                f"DeepSeek {operation} failed: {_redact_secret(exc, self.api_key)}"
            ) from exc

    @staticmethod
    def _extract_balanced_object(content: str) -> str | None:
        """Return the first complete JSON object without guessing or repairing fields."""
        for start, character in enumerate(content):
            if character != "{":
                continue
            depth = 0
            in_string = False
            escaped = False
            for index in range(start, len(content)):
                current = content[index]
                if in_string:
                    if escaped:
                        escaped = False
                    elif current == "\\":
                        escaped = True
                    elif current == '"':
                        in_string = False
                    continue
                if current == '"':
                    in_string = True
                elif current == "{":
                    depth += 1
                elif current == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = content[start : index + 1]
                        try:
                            json.loads(candidate)
                        except json.JSONDecodeError:
                            break
                        return candidate
        return None

    @classmethod
    def _parse_correction_response(cls, content: Any) -> Any:
        """Parse direct, fenced, or explanation-wrapped JSON without repairing data."""
        if not isinstance(content, str) or not content.strip():
            raise CorrectionResponseError("DeepSeek correction response content is empty.")
        candidates = [content, content.strip()]
        fenced = re.fullmatch(
            r"\s*```(?:json)?\s*(.*?)\s*```\s*", content, flags=re.DOTALL | re.IGNORECASE
        )
        if fenced:
            candidates.append(fenced.group(1).strip())
        balanced = cls._extract_balanced_object(content)
        if balanced:
            candidates.append(balanced)
        last_error: json.JSONDecodeError | None = None
        seen: set[str] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as exc:
                last_error = exc
        detail = "truncated" if last_error and last_error.pos >= len(last_error.doc) - 1 else "malformed"
        raise CorrectionResponseError(
            f"DeepSeek correction response contains {detail} JSON."
        ) from last_error

    @classmethod
    def _parse_corrections(cls, content: Any) -> list[dict[str, Any]]:
        try:
            parsed = CorrectionBatch.model_validate(cls._parse_correction_response(content))
        except CorrectionResponseError:
            raise
        except ValidationError as exc:
            raise CorrectionResponseError(
                "DeepSeek correction response has an invalid JSON schema."
            ) from exc
        return [segment.model_dump() for segment in parsed.corrections]

    @classmethod
    def _parse_global_context(cls, content: Any) -> dict[str, Any]:
        try:
            parsed = TranscriptGlobalContext.model_validate(cls._parse_correction_response(content))
        except (CorrectionResponseError, ValidationError) as exc:
            raise TranscriptCorrectionError(
                "DeepSeek returned invalid global transcript context JSON."
            ) from exc
        return parsed.model_dump()


def validate_correction_batch(
    source: list[dict[str, Any]], corrected: list[dict[str, Any]]
) -> None:
    """Require a one-to-one, non-empty correction for every current segment id."""
    expected = [item["id"] for item in source]
    try:
        actual = [item["id"] for item in corrected]
        texts = [str(item["corrected_text"]).strip() for item in corrected]
    except (KeyError, TypeError) as exc:
        raise TranscriptCorrectionError("Invalid corrected segment objects.") from exc
    if any(set(item) != {"id", "corrected_text"} for item in corrected):
        raise TranscriptCorrectionError(
            "Correction may return only id and corrected_text."
        )
    if len(actual) != len(set(actual)):
        raise TranscriptCorrectionError("Correction returned duplicate segment ids.")
    if set(actual) != set(expected) or len(actual) != len(expected):
        raise TranscriptCorrectionError("Correction returned mismatched segment ids.")
    if actual != expected:
        raise TranscriptCorrectionError("Correction changed segment order.")
    if any(not text for text in texts):
        raise TranscriptCorrectionError("Correction returned empty corrected_text.")


def _is_retryable_output_error(exc: Exception) -> bool:
    """Return whether one fresh model response can safely retry strict validation."""
    return isinstance(exc, CorrectionResponseError) or (
        isinstance(exc, TranscriptCorrectionError) and str(exc) in {
        "Invalid corrected segment objects.",
        "Correction may return only id and corrected_text.",
        "Correction returned duplicate segment ids.",
        "Correction returned mismatched segment ids.",
        "Correction changed segment order.",
        "Correction returned empty corrected_text.",
        }
    )


def _prepare_segments(
    segments: Iterable[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], list[dict[str, Any]]]:
    source_segments = list(segments)
    prepared = [
        {
            "id": segment.get("id", index),
            "text": str(segment.get("raw_text", segment.get("text", ""))).strip(),
        }
        for index, segment in enumerate(source_segments)
    ]
    ids = [item["id"] for item in prepared]
    if len(ids) != len(set(ids)):
        raise TranscriptCorrectionError("Whisper segment ids must be unique.")
    if any(not item["text"] for item in prepared):
        raise TranscriptCorrectionError("Whisper transcript contains empty text.")
    return source_segments, prepared


def _merge_corrections(
    source_segments: list[Mapping[str, Any]], corrected_by_id: Mapping[Any, str]
) -> list[dict[str, Any]]:
    return [
        {
            "id": segment.get("id", index),
            "start": segment["start"],
            "end": segment["end"],
            "raw_text": str(segment.get("raw_text", segment.get("text", ""))).strip(),
            "corrected_text": corrected_by_id[segment.get("id", index)],
        }
        for index, segment in enumerate(source_segments)
    ]


def correct_transcript_with_metadata(
    segments: Iterable[Mapping[str, Any]],
    detected_language: str,
    corrector: DeepSeekTranscriptCorrector | None = None,
) -> TranscriptCorrectionResult:
    """Correct each batch and return observable success/fallback metadata."""
    language = require_supported_language(detected_language, "source")
    source_segments, prepared = _prepare_segments(segments)
    enabled = transcript_correction_enabled()
    batch_size = transcript_correction_batch_size()
    context_size = transcript_correction_context_size()
    batch_count = math.ceil(len(prepared) / batch_size) if prepared else 0
    logger.info("%s enabled=%s", LOG_PREFIX, str(enabled).lower())
    logger.info("%s segments=%d", LOG_PREFIX, len(prepared))
    logger.info("%s batch_size=%d", LOG_PREFIX, batch_size)
    logger.info("%s batches=%d", LOG_PREFIX, batch_count)

    raw_by_id = {item["id"]: item["text"] for item in prepared}
    if not enabled or not prepared:
        segments_out = _merge_corrections(source_segments, raw_by_id)
        return TranscriptCorrectionResult(
            segments_out,
            {
                "enabled": enabled,
                "attempted": False,
                "success": True,
                "fallback": False,
                "changed_segments": 0,
                "total_segments": len(prepared),
                "batches": batch_count,
                "failed_batches": 0,
                "retry_batches": 0,
                "retry_successes": 0,
                "zero_change_warning": False,
                "error": None,
            },
        )

    errors: list[str] = []
    global_context_warning: str | None = None
    failed_batches = 0
    retry_batches = 0
    retry_successes = 0
    corrected_by_id = dict(raw_by_id)
    try:
        provider = corrector or DeepSeekTranscriptCorrector()
        global_threshold = transcript_global_context_threshold()
        global_max_chars = transcript_global_context_max_chars()
        transcript_chars = len("\n".join(item["text"] for item in prepared))
        use_global_transcript = (
            len(prepared) <= global_threshold
            and transcript_chars <= global_max_chars
        )
        global_transcript = prepared if use_global_transcript else []
        global_context: dict[str, Any] = {}
        if not use_global_transcript:
            try:
                global_context = provider.build_global_context(language, prepared)
            except Exception as exc:
                global_context_warning = f"global context unavailable: {exc}"
                logger.warning(
                    "%s %s; continuing with batch context only",
                    LOG_PREFIX,
                    global_context_warning,
                )

        for batch_index, offset in enumerate(range(0, len(prepared), batch_size), 1):
            current = prepared[offset : offset + batch_size]
            previous = prepared[max(0, offset - context_size) : offset]
            next_items = prepared[
                offset + batch_size : offset + batch_size + context_size
            ]
            logger.info(
                "%s batch %d/%d sending...", LOG_PREFIX, batch_index, batch_count
            )
            try:
                try:
                    corrected = provider.correct_batch(
                        language,
                        current,
                        previous,
                        next_items,
                        global_transcript,
                        global_context,
                    )
                    validate_correction_batch(current, corrected)
                except Exception as output_error:
                    if not _is_retryable_output_error(output_error):
                        raise
                    retry_batches += 1
                    logger.warning(
                        "%s batch %d/%d invalid model output; retrying: %s",
                        LOG_PREFIX,
                        batch_index,
                        batch_count,
                        output_error,
                    )
                    try:
                        corrected = provider.retry_correction_batch(
                            language,
                            current,
                            previous,
                            next_items,
                            global_context,
                        )
                        validate_correction_batch(current, corrected)
                        retry_successes += 1
                        logger.info(
                            "%s batch %d/%d retry success",
                            LOG_PREFIX,
                            batch_index,
                            batch_count,
                        )
                    except Exception as retry_error:
                        logger.error(
                            "%s batch %d/%d retry FAILED: %s",
                            LOG_PREFIX,
                            batch_index,
                            batch_count,
                            retry_error,
                        )
                        raise TranscriptCorrectionError(
                            f"{output_error}; retry failed: {retry_error}"
                        ) from retry_error
                changed = 0
                for item in corrected:
                    text = str(item["corrected_text"]).strip()
                    corrected_by_id[item["id"]] = text
                    changed += text != raw_by_id[item["id"]]
                logger.info(
                    "%s batch %d/%d success", LOG_PREFIX, batch_index, batch_count
                )
                logger.info(
                    "%s batch %d/%d changed=%d/%d",
                    LOG_PREFIX,
                    batch_index,
                    batch_count,
                    changed,
                    len(current),
                )
            except Exception as exc:
                failed_batches += 1
                message = f"batch {batch_index}/{batch_count}: {exc}"
                errors.append(message)
                logger.error("%s batch %d/%d FAILED: %s", LOG_PREFIX, batch_index, batch_count, exc)
                logger.warning(
                    "%s batch %d/%d fallback to raw/corrected baseline",
                    LOG_PREFIX,
                    batch_index,
                    batch_count,
                )
    except Exception as exc:
        failed_batches = batch_count
        errors.append(str(exc))
        logger.error("%s setup FAILED: %s", LOG_PREFIX, exc)

    segments_out = _merge_corrections(source_segments, corrected_by_id)
    changed_segments = sum(
        item["corrected_text"] != item["raw_text"] for item in segments_out
    )
    zero_change_warning = (
        len(prepared) >= ZERO_CHANGE_WARNING_MIN_SEGMENTS and changed_segments == 0
    )
    if zero_change_warning:
        logger.warning(
            "%s returned zero changes for %d segments.", LOG_PREFIX, len(prepared)
        )
    fallback = failed_batches > 0
    logger.info("%s completed", LOG_PREFIX)
    logger.info(
        "%s changed=%d/%d retry_batches=%d retry_successes=%d fallback=%s",
        LOG_PREFIX,
        changed_segments,
        len(prepared),
        retry_batches,
        retry_successes,
        str(fallback).lower(),
    )
    return TranscriptCorrectionResult(
        segments_out,
        {
            "enabled": True,
            "attempted": True,
            "success": failed_batches == 0,
            "fallback": fallback,
            "changed_segments": changed_segments,
            "total_segments": len(prepared),
            "batches": batch_count,
            "failed_batches": failed_batches,
            "retry_batches": retry_batches,
            "retry_successes": retry_successes,
            "zero_change_warning": zero_change_warning,
            "error": (
                "; ".join(errors)
                if errors
                else global_context_warning
            ),
        },
    )


def correct_transcript(
    segments: Iterable[Mapping[str, Any]],
    detected_language: str,
    corrector: DeepSeekTranscriptCorrector | None = None,
) -> list[dict[str, Any]]:
    """Compatibility wrapper returning corrected segments without metadata."""
    result = correct_transcript_with_metadata(segments, detected_language, corrector)
    if result.metadata["fallback"]:
        raise TranscriptCorrectionError(str(result.metadata["error"]))
    return result.segments


def correct_transcript_with_fallback(
    segments: Iterable[Mapping[str, Any]], detected_language: str
) -> TranscriptCorrectionResult:
    """Correct safely while exposing every fallback through metadata and logs."""
    return correct_transcript_with_metadata(segments, detected_language)
