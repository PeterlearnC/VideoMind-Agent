"""DeepSeek translation provider implemented with HTTP requests."""

import json
import os
from typing import Any, Mapping

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config.languages import language_name, require_supported_language

from app.services.translation_service import (
    DEEPSEEK_KEY_PLACEHOLDERS,
    TranslationConfigurationError,
    TranslationError,
    Translator,
)


class DeepSeekTranslator(Translator):
    """Translate subtitle text through the DeepSeek chat completions API."""

    API_URL = "https://api.deepseek.com/chat/completions"
    MODEL = "deepseek-chat"
    REQUEST_TIMEOUT_SECONDS = 60

    def __init__(
        self,
        api_key: str | None = None,
        source_language: str = "en",
        target_language: str = "zh",
        session: Any | None = None,
    ) -> None:
        if api_key is None:
            try:
                api_key = os.environ["DEEPSEEK_API_KEY"]
            except KeyError as exc:
                raise TranslationConfigurationError(
                    "Missing DEEPSEEK_API_KEY environment variable."
                ) from exc

        self.api_key = api_key
        self.source_language = require_supported_language(source_language, "source")
        self.target_language = require_supported_language(target_language, "target")
        self.session = session or requests
        if not self.api_key.strip() or self.api_key in DEEPSEEK_KEY_PLACEHOLDERS:
            raise TranslationConfigurationError(
                "DEEPSEEK_API_KEY must contain a valid API key."
            )

    def translate(self, text: str) -> str:
        """Translate one subtitle into the configured target language."""
        return self.translate_segments([{"id": 0, "text": text}])[0]["text"]

    def translate_segments(
        self,
        segments: list[dict[str, Any]],
        previous_context: list[dict[str, Any]] | None = None,
        next_context: list[dict[str, Any]] | None = None,
        global_transcript: list[dict[str, Any]] | None = None,
        global_context: Mapping[str, Any] | None = None,
        glossary: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Translate current id/text objects using read-only local/global context."""
        if not segments:
            return []

        request_content = {
            "source_language": self.source_language,
            "target_language": self.target_language,
            "global_transcript": global_transcript or [],
            "global_context": dict(global_context or {}),
            "previous_context": previous_context or [],
            "current_batch": segments,
            "next_context": next_context or [],
            "glossary": dict(glossary or {}),
        }
        system_prompt = (
            "You are translating consecutive video subtitle segments. You receive "
            "either a read-only global transcript or a read-only global context, plus "
            "previous_context, current_batch, next_context, and a glossary. Use all "
            "context only for semantic understanding, terminology, and disambiguation. "
            f"Source language: {language_name(self.source_language)}. "
            f"Target language: {language_name(self.target_language)}. "
            "Translate and output only current_batch. Never output ids or text from "
            "global_transcript, previous_context, or next_context. Preserve the original "
            "meaning while writing "
            "natural target-language subtitles. Keep terminology consistent. If a "
            "source phrase appears in glossary, its specified translation has highest "
            "priority. Apply preferred translations for people, places, organizations, "
            "and terminology from global_context consistently throughout the video. "
            "Handle personal names, place names, and organization names cautiously. If "
            "a short segment is incomplete, use its surrounding context to understand it "
            "but still return exactly one translation for that segment id. "
            "Preserve every number, unit, and year exactly. Do not add information not "
            "present in the source. Do not modify ids, add or remove segments, merge or "
            "split segments, or explain the translation. Return one valid JSON object "
            "with a translations array containing only id and text for every and only "
            "the current_batch ids."
        )
        return self._request_structured(system_prompt, request_content)

    def build_global_context(
        self,
        segments: list[dict[str, Any]],
        glossary: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Analyze one long corrected transcript for reusable translation context."""
        request_content = {
            "source_language": self.source_language,
            "target_language": self.target_language,
            "transcript": segments,
            "glossary": dict(glossary or {}),
        }
        system_prompt = (
            "Build read-only translation context from the supplied complete corrected "
            "video transcript. Do not translate subtitle segments, output timestamps, "
            "change ids, summarize content for display, or invent facts. Identify only "
            "well-supported topic/domain hints and recurring people, places, "
            "organizations, terminology, and language notes that help keep later "
            f"translations from {language_name(self.source_language)} into "
            f"{language_name(self.target_language)} consistent. The explicit glossary "
            "has highest priority. Return one JSON object with exactly: topic, domain, "
            "people, places, organizations, terminology, and language_notes. Each named "
            "entity or terminology item must contain only source and "
            "preferred_translation. language_notes must be an array of strings."
        )
        return self._request_global_context(system_prompt, request_content)

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
        """Proofread translated text while preserving current-batch ids."""
        request_content = {
            "source_language": self.source_language,
            "target_language": self.target_language,
            "global_transcript": global_transcript or [],
            "global_context": dict(global_context or {}),
            "previous_context": previous_context or [],
            "source_segments": source_segments,
            "translations": translations,
            "next_context": next_context or [],
            "glossary": dict(glossary or {}),
        }
        system_prompt = (
            "You are proofreading subtitle translations. Review only translated text "
            f"from {language_name(self.source_language)} into "
            f"{language_name(self.target_language)} "
            "for terminology and contextual consistency, omissions, preserved numbers "
            "and units, names and places, and obvious overly literal wording. Apply all "
            "global transcript/context and neighboring context only for understanding. "
            "Apply all glossary entries with highest priority and keep preferred global "
            "entity/term translations consistent. Do not output context ids, change ids, "
            "add or remove segments, merge or split segments, invent information, or "
            "explain edits. Return one valid JSON "
            "object with a translations array containing only id and reviewed text for "
            "every and only the supplied translation ids."
        )
        return self._request_structured(system_prompt, request_content)

    def _request_structured(
        self,
        system_prompt: str,
        request_content: dict[str, Any],
    ) -> list[dict[str, Any]]:
        payload = {
            "model": self.MODEL,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": json.dumps(request_content, ensure_ascii=False),
                },
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = self.session.post(
                self.API_URL,
                headers=headers,
                json=payload,
                timeout=self.REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            translations = self._parse_translations(content)
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            raise TranslationError(f"DeepSeek translation failed: {exc}") from exc

        return translations

    def _request_global_context(
        self,
        system_prompt: str,
        request_content: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "model": self.MODEL,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(request_content, ensure_ascii=False),
                },
            ],
        }
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
            content = response.json()["choices"][0]["message"]["content"]
            return self._parse_global_context(content)
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            raise TranslationError(
                f"DeepSeek global translation context failed: {exc}"
            ) from exc

    @staticmethod
    def _parse_translations(content: Any) -> list[dict[str, Any]]:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("DeepSeek returned empty content.")
        content = content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(lines[1:-1]).strip()
        try:
            parsed = TranslationBatch.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError("DeepSeek returned invalid translation JSON.") from exc
        return [item.model_dump() for item in parsed.translations]

    @staticmethod
    def _parse_global_context(content: Any) -> dict[str, Any]:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("DeepSeek returned empty global context content.")
        normalized = content.strip()
        if normalized.startswith("```"):
            lines = normalized.splitlines()
            normalized = "\n".join(lines[1:-1]).strip()
        try:
            parsed = TranslationGlobalContext.model_validate(json.loads(normalized))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError("DeepSeek returned invalid global context JSON.") from exc
        return parsed.model_dump()


class TranslationItem(BaseModel):
    """One translation keyed to its immutable source segment id."""

    model_config = ConfigDict(extra="forbid")

    id: int | str
    text: str = Field(min_length=1)


class TranslationBatch(BaseModel):
    """Structured DeepSeek translation response."""

    model_config = ConfigDict(extra="forbid")

    translations: list[TranslationItem]


class PreferredTranslation(BaseModel):
    """One transcript-supported preferred rendering for a recurring expression."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    preferred_translation: str = Field(min_length=1)


class TranslationGlobalContext(BaseModel):
    """Reusable semantic context extracted once for a long transcript."""

    model_config = ConfigDict(extra="forbid")

    topic: str
    domain: str
    people: list[PreferredTranslation]
    places: list[PreferredTranslation]
    organizations: list[PreferredTranslation]
    terminology: list[PreferredTranslation]
    language_notes: list[str]
