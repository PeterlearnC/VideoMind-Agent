"""DeepSeek translation provider implemented with HTTP requests."""

import json
import os
from typing import Any

import requests

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
        self.target_language = target_language
        self.session = session or requests
        if not self.api_key.strip() or self.api_key in DEEPSEEK_KEY_PLACEHOLDERS:
            raise TranslationConfigurationError(
                "DEEPSEEK_API_KEY must contain a valid API key."
            )

    def translate(self, text: str) -> str:
        """Translate one English subtitle into concise Chinese text."""
        return self.translate_batch([text])[0]

    def translate_batch(self, texts: list[str]) -> list[str]:
        """Translate one subtitle batch in a single DeepSeek request."""
        if not texts:
            return []

        payload = {
            "model": self.MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Translate English video subtitles into natural, concise "
                        f"{self.target_language} Chinese. Preserve the meaning and "
                        "return a JSON array of translated strings in exactly the "
                        "same order and length as the input array. Return JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(texts, ensure_ascii=False),
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

        if (
            len(translations) != len(texts)
            or any(not item.strip() for item in translations)
        ):
            raise TranslationError(
                "DeepSeek returned an invalid number or format of translations."
            )
        return [item.strip() for item in translations]

    @staticmethod
    def _parse_translations(content: Any) -> list[str]:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("DeepSeek returned empty content.")
        content = content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(lines[1:-1]).strip()
        translations = json.loads(content)
        if not isinstance(translations, list) or any(
            not isinstance(item, str) for item in translations
        ):
            raise ValueError("DeepSeek returned invalid translation JSON.")
        return translations
