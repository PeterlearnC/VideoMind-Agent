"""DeepSeek-powered agent for creating structured video summaries."""

import json
import os
from typing import Any, Iterable, Mapping

import requests

from app.config.languages import language_name, require_supported_language
from app.services.translation_service import DEEPSEEK_KEY_PLACEHOLDERS


class SummaryAgentError(RuntimeError):
    """Raised when the video summary agent cannot produce a valid result."""


class SummaryAgentConfigurationError(SummaryAgentError):
    """Raised when the summary model is not configured."""


class VideoSummaryAgent:
    """Summarize timestamped subtitle cues into structured video notes."""

    API_URL = "https://api.deepseek.com/chat/completions"
    MODEL = "deepseek-chat"
    REQUEST_TIMEOUT_SECONDS = 120

    def __init__(
        self,
        api_key: str | None = None,
        session: Any | None = None,
    ) -> None:
        if api_key is None:
            try:
                api_key = os.environ["DEEPSEEK_API_KEY"]
            except KeyError as exc:
                raise SummaryAgentConfigurationError(
                    "Missing DEEPSEEK_API_KEY environment variable."
                ) from exc

        if not api_key.strip() or api_key in DEEPSEEK_KEY_PLACEHOLDERS:
            raise SummaryAgentConfigurationError(
                "DEEPSEEK_API_KEY must contain a valid API key."
            )
        self.api_key = api_key
        self.session = session or requests

    def summarize(
        self,
        cues: Iterable[Mapping[str, Any]],
        output_language: str = "zh",
    ) -> dict[str, Any]:
        """Generate a factual structured summary from timestamped cues."""
        cue_items = list(cues)
        if not cue_items:
            raise SummaryAgentError("The subtitle track contains no content.")

        transcript = "\n".join(self._format_cue(cue) for cue in cue_items)
        output_language = require_supported_language(output_language, "summary")
        output_language_name = language_name(output_language)
        payload = {
            "model": self.MODEL,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a video understanding agent. Analyze only the "
                        "provided timestamped transcript; do not invent facts. "
                        f"Write all output in {output_language_name}. Return one JSON "
                        "object with exactly these fields: title (string), overview "
                        "(string), key_points (array of strings), chapters (array "
                        "of objects with numeric start, numeric end, string title, "
                        "and string summary), keywords (array of strings). Chapter "
                        "timestamps must stay within the supplied timeline."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Summarize this video transcript:\n\n{transcript}",
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
            result = self._parse_result(content)
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            raise SummaryAgentError(f"DeepSeek video summary failed: {exc}") from exc

        return result

    @staticmethod
    def _format_cue(cue: Mapping[str, Any]) -> str:
        start = float(cue["start"])
        minutes, seconds = divmod(int(start), 60)
        hours, minutes = divmod(minutes, 60)
        timestamp = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        source = str(
            cue.get("edited_source_text")
            if cue.get("edited_source_text") is not None
            else cue.get("corrected_text", cue.get("source_text", cue.get("source", "")))
        ).strip()
        translation = str(
            cue.get("edited_translated_text")
            if cue.get("edited_translated_text") is not None
            else cue.get("translated_text", cue.get("translation", ""))
        ).strip()
        text = source or translation
        if source and translation:
            text = f"{source} / {translation}"
        return f"[{timestamp}] {text}"

    @staticmethod
    def _parse_result(content: Any) -> dict[str, Any]:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("DeepSeek returned empty summary content.")
        normalized = content.strip()
        if normalized.startswith("```"):
            lines = normalized.splitlines()
            normalized = "\n".join(lines[1:-1]).strip()
        result = json.loads(normalized)
        if not isinstance(result, dict):
            raise ValueError("DeepSeek returned a non-object summary.")
        return result
