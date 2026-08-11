"""Unit tests for subtitle translation services."""

import json
import os
import unittest
from unittest.mock import patch

from app.services.deepseek_translator import DeepSeekTranslator
from app.services.translation_service import (
    TranslationConfigurationError,
    translate_segments,
)


class FakeResponse:
    def __init__(self, translations: list[str]) -> None:
        self.translations = translations

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            self.translations,
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }


class FakeSession:
    def __init__(self, translations: dict[str, str] | None = None) -> None:
        self.translations = translations or {}
        self.requests: list[dict[str, object]] = []

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append({"url": url, **kwargs})
        payload = kwargs["json"]
        texts = json.loads(payload["messages"][1]["content"])
        return FakeResponse(
            [self.translations.get(text, f"译文：{text}") for text in texts]
        )


class TranslationServiceTests(unittest.TestCase):
    def test_deepseek_translator_uses_requests_and_returns_translation(self) -> None:
        source = "This car is equipped with the latest hydraulic brakes."
        expected = "这辆汽车配备最新的液压制动系统。"
        session = FakeSession({source: expected})
        translator = DeepSeekTranslator(api_key="test-key", session=session)

        result = translator.translate(source)

        self.assertEqual(result, expected)
        request = session.requests[0]
        self.assertEqual(
            request["url"],
            "https://api.deepseek.com/chat/completions",
        )
        self.assertEqual(request["json"]["model"], "deepseek-chat")
        self.assertEqual(
            request["headers"]["Authorization"],
            "Bearer test-key",
        )

    def test_translate_segments_batches_fifteen_items_per_request(self) -> None:
        session = FakeSession()
        translator = DeepSeekTranslator(api_key="test-key", session=session)
        segments = [
            {"id": index, "start": index, "end": index + 1, "text": f"Text {index}"}
            for index in range(31)
        ]

        with patch(
            "app.services.translation_service._get_translator",
            return_value=translator,
        ):
            result = translate_segments(segments, "en")

        self.assertEqual(len(session.requests), 3)
        batch_lengths = [
            len(json.loads(request["json"]["messages"][1]["content"]))
            for request in session.requests
        ]
        self.assertEqual(batch_lengths, [15, 15, 1])
        self.assertEqual(result[0]["text"], "译文：Text 0")
        self.assertEqual(result[-1]["text"], "译文：Text 30")

    def test_translate_segments_reports_missing_api_key(self) -> None:
        segments = [{"id": 0, "start": 0, "end": 4, "text": "Test."}]

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                TranslationConfigurationError,
                "Missing DEEPSEEK_API_KEY",
            ):
                translate_segments(segments, "en")


if __name__ == "__main__":
    unittest.main()
