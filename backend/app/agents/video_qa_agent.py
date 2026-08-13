"""DeepSeek-powered agent for answering questions about one video."""

import json
import os
from typing import Any, Iterable, Mapping

import requests

from app.services.translation_service import DEEPSEEK_KEY_PLACEHOLDERS


class VideoQAAgentError(RuntimeError):
    """Raised when the video Q&A agent cannot produce an answer."""


class VideoQAAgentConfigurationError(VideoQAAgentError):
    """Raised when the Q&A model is not configured."""


class VideoQAAgent:
    """Answer a question using only timestamped subtitle cues."""

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
                raise VideoQAAgentConfigurationError(
                    "Missing DEEPSEEK_API_KEY environment variable."
                ) from exc

        if not api_key.strip() or api_key in DEEPSEEK_KEY_PLACEHOLDERS:
            raise VideoQAAgentConfigurationError(
                "DEEPSEEK_API_KEY must contain a valid API key."
            )
        self.api_key = api_key
        self.session = session or requests

    def answer(
        self,
        video_id: str,
        question: str,
        cues: Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Return a grounded answer with structured supporting references."""
        cue_items = list(cues)
        if not cue_items:
            raise VideoQAAgentError("The subtitle track contains no content.")

        transcript = "\n".join(
            self._format_cue(cue, index) for index, cue in enumerate(cue_items)
        )
        payload = {
            "model": self.MODEL,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You answer questions about one video using only its "
                        "timestamped transcript. Never use outside knowledge or "
                        "invent details. If the transcript is insufficient, say "
                        "clearly that the answer cannot be determined from this "
                        "video and return an empty references array. Respond in "
                        "the same language as the question. Return exactly one JSON "
                        "object with answer (non-empty string) and references (array). "
                        "Each reference must contain cue_id copied exactly from a "
                        "transcript cue and text (non-empty supporting subtitle or "
                        "concise description). Never generate timestamps or seconds; "
                        "the server derives them from the selected cue_id."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Video ID: {video_id}\nQuestion: {question}\n\n"
                        f"Timestamped transcript:\n{transcript}"
                    ),
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
            return self._parse_result(content)
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            raise VideoQAAgentError(f"DeepSeek video Q&A failed: {exc}") from exc

    @staticmethod
    def _format_cue(cue: Mapping[str, Any], index: int = 0) -> str:
        start = float(cue["start"])
        cue_id = str(cue.get("id", index))
        total_seconds = max(0, int(start))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
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
        return f"[cue_id={cue_id}; timestamp={timestamp}] {text}"

    @staticmethod
    def _parse_result(content: Any) -> dict[str, Any]:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("DeepSeek returned empty Q&A content.")
        normalized = content.strip()
        if normalized.startswith("```"):
            lines = normalized.splitlines()
            normalized = "\n".join(lines[1:-1]).strip()
        result = json.loads(normalized)
        if not isinstance(result, dict):
            raise ValueError("DeepSeek returned a non-object Q&A result.")
        return result
