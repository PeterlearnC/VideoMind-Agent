"""Unit tests for subtitle translation services."""

import json
import os
import unittest
from unittest.mock import patch

from app.services.deepseek_translator import DeepSeekTranslator
from app.services.translation_service import (
    TranslationConfigurationError,
    TranslationError,
    Translator,
    translate_segments,
)


class FakeResponse:
    def __init__(self, translations: list[dict[str, object]]) -> None:
        self.translations = translations

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"translations": self.translations},
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
        request_content = json.loads(payload["messages"][1]["content"])
        segments = request_content.get("current_batch") or request_content.get(
            "source_segments", []
        )
        return FakeResponse(
            [
                {
                    "id": segment["id"],
                    "text": self.translations.get(
                        segment["text"], f"译文：{segment['text']}"
                    ),
                }
                for segment in segments
            ]
        )


class ResultTranslator(Translator):
    def __init__(self, results: list[dict[str, object]]) -> None:
        self.results = results

    def translate(self, text: str) -> str:
        return text

    def translate_segments(
        self,
        segments: list[dict[str, object]],
        previous_context=None,
        next_context=None,
        global_transcript=None,
        global_context=None,
        glossary=None,
    ) -> list[dict[str, object]]:
        return self.results


class RecordingTranslator(Translator):
    def __init__(self) -> None:
        self.translation_calls: list[dict[str, object]] = []
        self.global_context_calls: list[dict[str, object]] = []

    def translate(self, text: str) -> str:
        return f"translated: {text}"

    def build_global_context(self, segments, glossary=None):
        self.global_context_calls.append(
            {"segments": segments, "glossary": dict(glossary or {})}
        )
        return {
            "topic": "rail systems",
            "domain": "engineering",
            "people": [],
            "places": [],
            "organizations": [],
            "terminology": [
                {
                    "source": "floating slab",
                    "preferred_translation": "浮置板",
                }
            ],
            "language_notes": [],
        }

    def translate_segments(
        self,
        segments,
        previous_context=None,
        next_context=None,
        global_transcript=None,
        global_context=None,
        glossary=None,
    ):
        self.translation_calls.append(
            {
                "segments": segments,
                "previous_context": previous_context or [],
                "next_context": next_context or [],
                "global_transcript": global_transcript or [],
                "global_context": global_context or {},
                "glossary": dict(glossary or {}),
            }
        )
        return [
            {"id": segment["id"], "text": f"translated: {segment['text']}"}
            for segment in segments
        ]


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
            len(
                json.loads(request["json"]["messages"][1]["content"])[
                    "current_batch"
                ]
            )
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

    def test_generic_language_pairs_preserve_timestamps(self) -> None:
        combinations = [
            ("en", "zh"),
            ("zh", "en"),
            ("ja", "zh"),
            ("ko", "zh"),
            ("ru", "en"),
        ]
        source = [{"id": 7, "start": 1.25, "end": 4.75, "text": "字幕"}]

        for source_language, target_language in combinations:
            with self.subTest(pair=(source_language, target_language)):
                translator = ResultTranslator([{"id": 7, "text": "Translation"}])
                with patch(
                    "app.services.translation_service._get_translator",
                    return_value=translator,
                ) as get_translator:
                    result = translate_segments(
                        source, source_language, target_language
                    )

                get_translator.assert_called_once_with(
                    source_language, target_language
                )
                self.assertEqual(result[0]["start"], source[0]["start"])
                self.assertEqual(result[0]["end"], source[0]["end"])
                self.assertEqual(result[0]["id"], 7)

    def test_same_language_returns_whisper_segments_without_translator(self) -> None:
        combinations = [("en", "en"), ("zh", "zh"), ("ja", "ja")]
        source = [
            {"id": 4, "start": 1.125, "end": 3.875, "text": "Original text"}
        ]

        for source_language, target_language in combinations:
            with self.subTest(language=source_language):
                with patch(
                    "app.services.translation_service._get_translator"
                ) as get_translator:
                    result = translate_segments(
                        source, source_language, target_language
                    )

                get_translator.assert_not_called()
                self.assertEqual(result, source)

    def test_rejects_missing_duplicate_and_extra_translation_ids(self) -> None:
        source = [
            {"id": 1, "start": 0, "end": 1, "text": "One"},
            {"id": 2, "start": 1, "end": 2, "text": "Two"},
        ]
        invalid_results = [
            [{"id": 1, "text": "一"}],
            [{"id": 1, "text": "一"}, {"id": 1, "text": "二"}],
            [
                {"id": 1, "text": "一"},
                {"id": 2, "text": "二"},
                {"id": 3, "text": "三"},
            ],
        ]

        for translated in invalid_results:
            with self.subTest(translated=translated):
                with patch(
                    "app.services.translation_service._get_translator",
                    return_value=ResultTranslator(translated),
                ):
                    with self.assertRaises(TranslationError):
                        translate_segments(source, "en", "zh")

    def test_context_contains_previous_next_and_global_transcript(self) -> None:
        session = FakeSession()
        translator = DeepSeekTranslator(api_key="test-key", session=session)
        segments = [
            {"id": index, "start": index, "end": index + 1, "text": f"Cue {index}"}
            for index in range(18)
        ]

        with patch.dict(
            os.environ,
            {
                "TRANSLATION_BATCH_SIZE": "6",
                "TRANSLATION_CONTEXT_SIZE": "5",
                "TRANSLATION_GLOBAL_TRANSCRIPT_MAX_SEGMENTS": "80",
            },
        ), patch(
            "app.services.translation_service._get_translator",
            return_value=translator,
        ):
            result = translate_segments(segments, "en", "zh")

        first_request = json.loads(
            session.requests[0]["json"]["messages"][1]["content"]
        )
        second_request = json.loads(
            session.requests[1]["json"]["messages"][1]["content"]
        )
        self.assertEqual(
            [item["id"] for item in first_request["next_context"]],
            [6, 7, 8, 9, 10],
        )
        self.assertEqual(
            [item["id"] for item in second_request["previous_context"]],
            [1, 2, 3, 4, 5],
        )
        self.assertEqual(
            [item["id"] for item in second_request["current_batch"]],
            [6, 7, 8, 9, 10, 11],
        )
        self.assertEqual(
            [item["id"] for item in second_request["next_context"]],
            [12, 13, 14, 15, 16],
        )
        self.assertEqual(
            [item["id"] for item in second_request["global_transcript"]],
            list(range(18)),
        )
        self.assertEqual(second_request["global_context"], {})
        self.assertEqual(len(result), len(segments))

    def test_long_video_builds_global_context_once_and_reuses_it(self) -> None:
        translator = RecordingTranslator()
        segments = [
            {"id": index, "start": index + 0.25, "end": index + 0.75, "text": f"Corrected {index}"}
            for index in range(7)
        ]

        with patch.dict(
            os.environ,
            {
                "TRANSLATION_BATCH_SIZE": "3",
                "TRANSLATION_CONTEXT_SIZE": "2",
                "TRANSLATION_GLOBAL_TRANSCRIPT_MAX_SEGMENTS": "5",
            },
        ), patch(
            "app.services.translation_service._get_translator",
            return_value=translator,
        ):
            result = translate_segments(segments, "en", "zh")

        self.assertEqual(len(translator.global_context_calls), 1)
        self.assertEqual(
            [item["text"] for item in translator.global_context_calls[0]["segments"]],
            [f"Corrected {index}" for index in range(7)],
        )
        self.assertEqual(len(translator.translation_calls), 3)
        for call in translator.translation_calls:
            self.assertEqual(call["global_transcript"], [])
            self.assertEqual(call["global_context"]["topic"], "rail systems")
        self.assertEqual(
            [(item["start"], item["end"]) for item in result],
            [(item["start"], item["end"]) for item in segments],
        )

    def test_review_receives_same_local_and_global_context(self) -> None:
        class ReviewRecordingTranslator(RecordingTranslator):
            def __init__(self) -> None:
                super().__init__()
                self.review_calls: list[dict[str, object]] = []

            def review_translations(
                self,
                source_segments,
                translations,
                previous_context=None,
                next_context=None,
                global_transcript=None,
                global_context=None,
                glossary=None,
            ):
                self.review_calls.append(
                    {
                        "source_segments": source_segments,
                        "translations": translations,
                        "previous_context": previous_context or [],
                        "next_context": next_context or [],
                        "global_transcript": global_transcript or [],
                        "global_context": global_context or {},
                        "glossary": dict(glossary or {}),
                    }
                )
                return translations

        translator = ReviewRecordingTranslator()
        segments = [
            {"id": index, "start": index, "end": index + 1, "text": f"Corrected {index}"}
            for index in range(5)
        ]

        with patch.dict(
            os.environ,
            {
                "TRANSLATION_BATCH_SIZE": "2",
                "TRANSLATION_CONTEXT_SIZE": "1",
                "TRANSLATION_GLOBAL_TRANSCRIPT_MAX_SEGMENTS": "80",
            },
        ), patch(
            "app.services.translation_service._get_translator",
            return_value=translator,
        ):
            translate_segments(
                segments,
                "en",
                "zh",
                glossary={"Corrected": "translated"},
                review_enabled=True,
            )

        second = translator.review_calls[1]
        self.assertEqual([item["id"] for item in second["previous_context"]], [1])
        self.assertEqual([item["id"] for item in second["source_segments"]], [2, 3])
        self.assertEqual([item["id"] for item in second["next_context"]], [4])
        self.assertEqual(
            [item["text"] for item in second["global_transcript"]],
            [f"Corrected {index}" for index in range(5)],
        )
        self.assertEqual(second["global_context"], {})
        self.assertEqual(second["glossary"], {"Corrected": "translated"})

    def test_context_ids_are_rejected_if_returned_as_translations(self) -> None:
        source = [
            {"id": index, "start": index, "end": index + 1, "text": f"Cue {index}"}
            for index in range(4)
        ]
        translator = ResultTranslator(
            [{"id": 0, "text": "context output"}, {"id": 1, "text": "current"}]
        )

        with patch.dict(
            os.environ,
            {"TRANSLATION_BATCH_SIZE": "1", "TRANSLATION_CONTEXT_SIZE": "1"},
        ), patch(
            "app.services.translation_service._get_translator",
            return_value=translator,
        ):
            with self.assertRaisesRegex(TranslationError, "mismatched segment ids"):
                translate_segments(source, "en", "zh")

    def test_glossary_is_sent_and_required_in_translation(self) -> None:
        source = "The floating slab supports the track."
        preferred = "浮置板支撑轨道。"
        session = FakeSession({source: preferred})
        translator = DeepSeekTranslator(api_key="test-key", session=session)
        segments = [{"id": 2, "start": 0, "end": 1, "text": source}]

        with patch(
            "app.services.translation_service._get_translator",
            return_value=translator,
        ):
            result = translate_segments(
                segments,
                "en",
                "zh",
                glossary={"floating slab": "浮置板"},
            )

        request_content = json.loads(
            session.requests[0]["json"]["messages"][1]["content"]
        )
        self.assertEqual(request_content["glossary"], {"floating slab": "浮置板"})
        self.assertEqual(result[0]["text"], preferred)

    def test_validator_rejects_changed_numbers_and_units(self) -> None:
        source = [{"id": 1, "start": 0, "end": 1, "text": "Length is 12.5 mm."}]
        translator = ResultTranslator([{"id": 1, "text": "长度为 15 mm。"}])

        with patch(
            "app.services.translation_service._get_translator",
            return_value=translator,
        ):
            with self.assertRaisesRegex(TranslationError, "numbers or units"):
                translate_segments(source, "en", "zh")

    def test_review_rejects_attempt_to_return_timeline(self) -> None:
        class ReviewingTranslator(ResultTranslator):
            def review_translations(
                self,
                source_segments,
                translations,
                previous_context=None,
                next_context=None,
                global_transcript=None,
                global_context=None,
                glossary=None,
            ):
                return [{"id": 9, "text": "校对译文", "start": 999, "end": 1000}]

        source = [{"id": 9, "start": 2.5, "end": 4.5, "text": "Source"}]
        translator = ReviewingTranslator([{"id": 9, "text": "初稿"}])

        with patch(
            "app.services.translation_service._get_translator",
            return_value=translator,
        ):
            with self.assertRaisesRegex(TranslationError, "only id"):
                translate_segments(source, "en", "zh", review_enabled=True)


if __name__ == "__main__":
    unittest.main()
