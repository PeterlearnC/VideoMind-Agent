"""Tests for full-context Whisper transcript correction."""

import json
import unittest
from unittest.mock import patch

import requests

from app.services.transcript_correction_service import (
    CorrectionResponseError,
    DeepSeekTranscriptCorrector,
    TranscriptCorrectionError,
    correct_transcript,
    correct_transcript_with_metadata,
    correct_transcript_with_fallback,
    validate_correction_batch,
)


class FakeResponse:
    def __init__(self, corrections: object, status_error: Exception | None = None) -> None:
        self.corrections = corrections
        self.status_error = status_error
        self.status_code = 200
        self.text = ""

    def raise_for_status(self) -> None:
        if self.status_error:
            raise self.status_error
        return None

    def json(self) -> dict[str, object]:
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"corrections": self.corrections}, ensure_ascii=False
                        )
                    }
                }
            ]
        }


class FakeSession:
    def __init__(self, replacements: dict[str, str] | None = None) -> None:
        self.requests: list[dict[str, object]] = []
        self.replacements = replacements or {}

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append({"url": url, **kwargs})
        content = json.loads(kwargs["json"]["messages"][1]["content"])
        return FakeResponse(
            [
                {"id": item["id"], "corrected_text": f"corrected: {item['text']}"}
                if item["text"] not in self.replacements
                else {"id": item["id"], "corrected_text": self.replacements[item["text"]]}
                for item in content["current_batch"]
            ]
        )


class MalformedSession:
    def post(self, url: str, **kwargs: object):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "not-json"}}]}

        return Response()


class FailingCorrector:
    def correct_batch(self, *args, **kwargs):
        raise TranscriptCorrectionError("HTTP 503 from DeepSeek")


class GlobalContext400ThenCorrector:
    def __init__(self, replacements: dict[int, str]) -> None:
        self.replacements = replacements
        self.global_context_calls = 0
        self.batch_calls = 0

    def build_global_context(self, language, transcript):
        self.global_context_calls += 1
        raise TranscriptCorrectionError(
            'DeepSeek global transcript context failed: HTTP 400: '
            '{"error":{"message":"Invalid request"}}'
        )

    def correct_batch(
        self,
        language,
        current,
        previous,
        next_items,
        global_transcript,
        global_context,
    ):
        self.batch_calls += 1
        return [
            {
                "id": item["id"],
                "corrected_text": self.replacements.get(item["id"], item["text"]),
            }
            for item in current
        ]


class RetryCorrector:
    def __init__(self, invalid_result, retry_result) -> None:
        self.invalid_result = invalid_result
        self.retry_result = retry_result
        self.retry_calls = 0

    def correct_batch(self, language, current, *args):
        return self.invalid_result(current)

    def retry_correction_batch(self, language, current, *args):
        self.retry_calls += 1
        return self.retry_result(current)


class TranscriptCorrectionTests(unittest.TestCase):
    def test_correction_request_uses_json_mode_zero_temperature_and_strict_prompt(self) -> None:
        session = FakeSession()
        provider = DeepSeekTranscriptCorrector(api_key="test-key", session=session)
        provider.correct_batch(
            "en", [{"id": 7, "text": "raw"}], [], [], [], {}
        )

        payload = session.requests[0]["json"]
        prompt = payload["messages"][0]["content"]
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["temperature"], 0)
        self.assertNotIn("max_tokens", payload)
        for contract in (
            "exactly one valid JSON object",
            "Do not use markdown",
            "exactly once",
            "non-empty string",
            "Do not output start or end",
        ):
            self.assertIn(contract, prompt)

    def test_layered_parser_accepts_direct_fenced_and_explanation_wrapped_json(self) -> None:
        body = '{"corrections":[{"id":1,"corrected_text":"fixed"}]}'
        variants = [body, f"  {body}\n", f"```json\n{body}\n```", f"Result follows:\n{body}\nDone."]
        for content in variants:
            with self.subTest(content=content):
                self.assertEqual(
                    DeepSeekTranscriptCorrector._parse_corrections(content),
                    [{"id": 1, "corrected_text": "fixed"}],
                )

    def test_parser_distinguishes_truncated_malformed_and_schema_errors(self) -> None:
        invalid = [
            ('{"corrections":[{"id":1', "truncated JSON"),
            ("not-json", "malformed JSON"),
            ('{"items":[]}', "invalid JSON schema"),
        ]
        for content, message in invalid:
            with self.subTest(content=content), self.assertRaisesRegex(
                CorrectionResponseError, message
            ):
                DeepSeekTranscriptCorrector._parse_corrections(content)

    def test_parser_does_not_relax_segment_schema(self) -> None:
        content = json.dumps({
            "corrections": [{
                "id": 1, "corrected_text": "fixed", "start": 0, "end": 1,
            }]
        })
        with self.assertRaisesRegex(CorrectionResponseError, "invalid JSON schema"):
            DeepSeekTranscriptCorrector._parse_corrections(content)

    def test_invalid_json_retries_once_then_preserves_whisper_timeline(self) -> None:
        class InvalidJsonThenSuccess:
            def __init__(self):
                self.retry_calls = 0

            def correct_batch(self, *args):
                raise CorrectionResponseError(
                    "DeepSeek correction response contains malformed JSON."
                )

            def retry_correction_batch(self, language, current, *args):
                self.retry_calls += 1
                return [
                    {"id": item["id"], "corrected_text": f"fixed {item['text']}"}
                    for item in current
                ]

        source = [{"id": 5, "start": 1.25, "end": 3.75, "text": "raw"}]
        provider = InvalidJsonThenSuccess()
        result = correct_transcript_with_metadata(source, "en", provider)

        self.assertEqual(provider.retry_calls, 1)
        self.assertEqual(result.metadata["retry_batches"], 1)
        self.assertEqual(result.metadata["retry_successes"], 1)
        self.assertFalse(result.metadata["fallback"])
        self.assertEqual(result.segments[0]["start"], 1.25)
        self.assertEqual(result.segments[0]["end"], 3.75)
        self.assertEqual(result.segments[0]["corrected_text"], "fixed raw")

    def test_correction_preserves_ids_count_and_whisper_timeline(self) -> None:
        source = [
            {"id": 4, "start": 1.25, "end": 3.75, "text": "raw one"},
            {"id": 8, "start": 3.75, "end": 6.0, "text": "raw two"},
        ]
        corrector = DeepSeekTranscriptCorrector(api_key="test-key", session=FakeSession())

        result = correct_transcript(source, "en", corrector)

        self.assertEqual([item["id"] for item in result], [4, 8])
        self.assertEqual(len(result), len(source))
        self.assertEqual(result[0]["start"], 1.25)
        self.assertEqual(result[0]["end"], 3.75)
        self.assertEqual(result[0]["raw_text"], "raw one")
        self.assertEqual(result[0]["corrected_text"], "corrected: raw one")

    def test_long_transcript_uses_previous_and_next_context(self) -> None:
        session = FakeSession()
        corrector = DeepSeekTranscriptCorrector(api_key="test-key", session=session)
        source = [
            {"id": index, "start": index, "end": index + 1, "text": f"cue {index}"}
            for index in range(7)
        ]

        with patch.dict(
            "os.environ",
            {
                "TRANSCRIPT_CORRECTION_BATCH_SIZE": "3",
                "TRANSCRIPT_CORRECTION_CONTEXT_SIZE": "2",
            },
        ):
            result = correct_transcript(source, "en", corrector)

        second = json.loads(session.requests[1]["json"]["messages"][1]["content"])
        self.assertEqual([item["id"] for item in second["previous_context"]], [1, 2])
        self.assertEqual([item["id"] for item in second["current_batch"]], [3, 4, 5])
        self.assertEqual([item["id"] for item in second["next_context"]], [6])
        self.assertEqual(
            [item["id"] for item in second["global_transcript"]], list(range(7))
        )
        self.assertEqual(second["global_context"], {})
        self.assertEqual(len(result), len(source))

    def test_validator_rejects_missing_duplicate_and_extra_ids(self) -> None:
        source = [{"id": 1, "text": "one"}, {"id": 2, "text": "two"}]
        invalid = [
            [{"id": 1, "corrected_text": "one"}],
            [
                {"id": 1, "corrected_text": "one"},
                {"id": 1, "corrected_text": "two"},
            ],
            [
                {"id": 1, "corrected_text": "one"},
                {"id": 2, "corrected_text": "two"},
                {"id": 3, "corrected_text": "three"},
            ],
            [
                {"id": 2, "corrected_text": "two"},
                {"id": 1, "corrected_text": "one"},
            ],
        ]

        for corrected in invalid:
            with self.subTest(corrected=corrected):
                with self.assertRaises(TranscriptCorrectionError):
                    validate_correction_batch(source, corrected)

    def test_failure_falls_back_to_raw_text(self) -> None:
        source = [{"id": 2, "start": 1, "end": 2, "text": "raw transcript"}]

        with patch(
            "app.services.transcript_correction_service.DeepSeekTranscriptCorrector",
            return_value=FailingCorrector(),
        ), self.assertLogs(
            "uvicorn.error.transcript_correction", level="ERROR"
        ):
            result = correct_transcript_with_fallback(source, "en")

        self.assertEqual(result.segments[0]["corrected_text"], "raw transcript")
        self.assertEqual(result.segments[0]["raw_text"], "raw transcript")
        self.assertEqual(result.segments[0]["start"], 1)
        self.assertFalse(result.metadata["success"])
        self.assertTrue(result.metadata["fallback"])
        self.assertEqual(result.metadata["failed_batches"], 1)
        self.assertIn("HTTP 503", result.metadata["error"])

    def test_real_prompt_corrects_known_chinese_asr_errors(self) -> None:
        source = [
            {"id": 0, "start": 0, "end": 1, "text": "水泥的售命只有50年"},
            {"id": 1, "start": 1, "end": 2, "text": "这完全就是两马事儿啊"},
            {"id": 2, "start": 2, "end": 3, "text": "工程师会在房子的横量楼板"},
        ]
        replacements = {
            "水泥的售命只有50年": "水泥的寿命只有50年",
            "这完全就是两马事儿啊": "这完全就是两码事儿啊",
            "工程师会在房子的横量楼板": "工程师会在房子的横梁、楼板",
        }
        session = FakeSession(replacements)
        corrector = DeepSeekTranscriptCorrector(api_key="test-key", session=session)

        result = correct_transcript_with_metadata(source, "zh", corrector)

        self.assertEqual(result.metadata["changed_segments"], 3)
        self.assertTrue(result.metadata["success"])
        self.assertFalse(result.metadata["fallback"])
        self.assertEqual(
            [item["corrected_text"] for item in result.segments],
            list(replacements.values()),
        )
        request = session.requests[0]["json"]
        self.assertIn("ASR Transcript Proofreader", request["messages"][0]["content"])
        self.assertNotIn("test-key", json.dumps(request, ensure_ascii=False))

    def test_malformed_response_falls_back_with_error_metadata(self) -> None:
        source = [{"id": 0, "start": 0, "end": 1, "text": "raw"}]
        corrector = DeepSeekTranscriptCorrector(
            api_key="test-key", session=MalformedSession()
        )

        result = correct_transcript_with_metadata(source, "en", corrector)

        self.assertTrue(result.metadata["fallback"])
        self.assertIn("malformed JSON", result.metadata["error"])
        self.assertEqual(result.metadata["retry_batches"], 1)
        self.assertEqual(result.metadata["retry_successes"], 0)
        self.assertEqual(result.segments[0]["corrected_text"], "raw")

    def test_zero_change_response_is_success_with_warning(self) -> None:
        source = [
            {"id": index, "start": index, "end": index + 1, "text": f"cue {index}"}
            for index in range(20)
        ]

        class UnchangedCorrector:
            def correct_batch(self, language, current, *args):
                return [
                    {"id": item["id"], "corrected_text": item["text"]}
                    for item in current
                ]

        with self.assertLogs(
            "uvicorn.error.transcript_correction", level="WARNING"
        ) as logs:
            result = correct_transcript_with_metadata(
                source, "en", UnchangedCorrector()
            )

        self.assertTrue(result.metadata["success"])
        self.assertFalse(result.metadata["fallback"])
        self.assertTrue(result.metadata["zero_change_warning"])
        self.assertIn("zero changes for 20 segments", "\n".join(logs.output))

    def test_long_transcript_builds_global_context_once(self) -> None:
        class ContextCorrector:
            def __init__(self) -> None:
                self.context_calls = 0
                self.batch_contexts: list[dict[str, object]] = []

            def build_global_context(self, language, transcript):
                self.context_calls += 1
                return {
                    "topic": "concrete",
                    "domain": "engineering",
                    "people": [],
                    "places": [],
                    "organizations": [],
                    "terminology": [
                        {"source": "横量", "canonical": "横梁"}
                    ],
                    "context_notes": [],
                }

            def correct_batch(
                self,
                language,
                current,
                previous,
                next_items,
                global_transcript,
                global_context,
            ):
                self.batch_contexts.append(
                    {
                        "global_transcript": global_transcript,
                        "global_context": global_context,
                    }
                )
                return [
                    {"id": item["id"], "corrected_text": item["text"]}
                    for item in current
                ]

        source = [
            {"id": index, "start": index, "end": index + 1, "text": f"cue {index}"}
            for index in range(6)
        ]
        corrector = ContextCorrector()
        with patch.dict(
            "os.environ",
            {
                "TRANSCRIPT_CORRECTION_BATCH_SIZE": "2",
                "TRANSCRIPT_GLOBAL_CONTEXT_THRESHOLD": "5",
            },
        ):
            result = correct_transcript_with_metadata(source, "zh", corrector)

        self.assertEqual(corrector.context_calls, 1)
        self.assertEqual(len(corrector.batch_contexts), 3)
        self.assertTrue(result.metadata["success"])
        for call in corrector.batch_contexts:
            self.assertEqual(call["global_transcript"], [])
            self.assertEqual(call["global_context"]["topic"], "concrete")

    def test_global_context_400_logs_body_and_preserves_batch_correction(self) -> None:
        class Http400Response:
            status_code = 400
            text = '{"error":{"message":"response_format JSON requires JSON prompt"}}'

            def raise_for_status(self):
                raise requests.HTTPError("400 Client Error", response=self)

            def json(self):
                return {}

        class Http400Session:
            def post(self, url, **kwargs):
                return Http400Response()

        provider = DeepSeekTranscriptCorrector(
            api_key="secret-test-key", session=Http400Session()
        )
        with self.assertLogs(
            "uvicorn.error.transcript_correction", level="WARNING"
        ) as logs:
            with self.assertRaisesRegex(
                TranscriptCorrectionError,
                "response_format JSON requires JSON prompt",
            ):
                provider.build_global_context(
                    "zh", [{"id": 0, "text": "水泥的售命只有50年"}]
                )

        output = "\n".join(logs.output)
        self.assertIn("global context HTTP 400", output)
        self.assertIn("response_format JSON requires JSON prompt", output)
        self.assertNotIn("secret-test-key", output)

    def test_117_segments_use_three_batches_without_global_context(self) -> None:
        source = [
            {"id": index, "start": index, "end": index + 1, "text": f"原始字幕 {index}"}
            for index in range(117)
        ]
        provider = GlobalContext400ThenCorrector(
            {
                0: "水泥的寿命只有50年",
                5: "这完全就是两码事儿啊",
                15: "工程师会在房子的横梁、楼板",
            }
        )
        with patch.dict(
            "os.environ",
            {
                "TRANSCRIPT_CORRECTION_BATCH_SIZE": "40",
                "TRANSCRIPT_CORRECTION_CONTEXT_SIZE": "5",
                "TRANSCRIPT_GLOBAL_CONTEXT_THRESHOLD": "150",
                "TRANSCRIPT_GLOBAL_CONTEXT_MAX_CHARS": "12000",
            },
        ):
            result = correct_transcript_with_metadata(source, "zh", provider)

        self.assertEqual(provider.global_context_calls, 0)
        self.assertEqual(provider.batch_calls, 3)
        self.assertTrue(result.metadata["success"])
        self.assertFalse(result.metadata["fallback"])
        self.assertEqual(result.metadata["failed_batches"], 0)
        self.assertEqual(result.metadata["changed_segments"], 3)

    def test_global_context_failure_is_warning_and_batches_continue(self) -> None:
        source = [
            {"id": index, "start": index, "end": index + 1, "text": f"raw {index}"}
            for index in range(6)
        ]
        provider = GlobalContext400ThenCorrector({0: "corrected 0"})
        with patch.dict(
            "os.environ",
            {
                "TRANSCRIPT_CORRECTION_BATCH_SIZE": "2",
                "TRANSCRIPT_GLOBAL_CONTEXT_THRESHOLD": "5",
            },
        ), self.assertLogs(
            "uvicorn.error.transcript_correction", level="WARNING"
        ) as logs:
            result = correct_transcript_with_metadata(source, "en", provider)

        self.assertEqual(provider.global_context_calls, 1)
        self.assertEqual(provider.batch_calls, 3)
        self.assertTrue(result.metadata["success"])
        self.assertFalse(result.metadata["fallback"])
        self.assertEqual(result.metadata["failed_batches"], 0)
        self.assertEqual(result.metadata["changed_segments"], 1)
        self.assertIn("global context unavailable", result.metadata["error"])
        self.assertIn("continuing with batch context only", "\n".join(logs.output))

    def test_missing_extra_and_duplicate_ids_retry_success(self) -> None:
        source = [
            {"id": 10, "start": 1.25, "end": 2.5, "text": "raw ten"},
            {"id": 11, "start": 2.5, "end": 4.75, "text": "raw eleven"},
        ]
        invalid_results = {
            "missing": lambda current: [
                {"id": current[0]["id"], "corrected_text": "first"}
            ],
            "extra": lambda current: [
                *[
                    {"id": item["id"], "corrected_text": item["text"]}
                    for item in current
                ],
                {"id": 999, "corrected_text": "context leak"},
            ],
            "duplicate": lambda current: [
                {"id": current[0]["id"], "corrected_text": "first"},
                {"id": current[0]["id"], "corrected_text": "duplicate"},
            ],
        }

        for name, invalid_result in invalid_results.items():
            with self.subTest(name=name):
                provider = RetryCorrector(
                    invalid_result,
                    lambda current: [
                        {
                            "id": item["id"],
                            "corrected_text": f"retry: {item['text']}",
                        }
                        for item in current
                    ],
                )
                result = correct_transcript_with_metadata(source, "en", provider)

                self.assertEqual(provider.retry_calls, 1)
                self.assertEqual(result.metadata["retry_batches"], 1)
                self.assertEqual(result.metadata["retry_successes"], 1)
                self.assertEqual(result.metadata["failed_batches"], 0)
                self.assertFalse(result.metadata["fallback"])
                self.assertEqual([item["id"] for item in result.segments], [10, 11])
                self.assertEqual(result.segments[0]["start"], 1.25)
                self.assertEqual(result.segments[1]["end"], 4.75)

    def test_retry_request_hides_context_ids_and_lists_exact_batch_ids(self) -> None:
        session = FakeSession()
        provider = DeepSeekTranscriptCorrector(api_key="test-key", session=session)

        provider.retry_correction_batch(
            "en",
            [{"id": 40, "text": "current forty"}, {"id": 41, "text": "current forty-one"}],
            [{"id": 39, "text": "previous"}],
            [{"id": 42, "text": "next"}],
            {"topic": "test"},
        )

        request = session.requests[0]["json"]
        prompt = request["messages"][0]["content"]
        content = json.loads(request["messages"][1]["content"])
        self.assertEqual(content["required_ids"], [40, 41])
        self.assertEqual(content["previous_context"], [{"text": "previous"}])
        self.assertEqual(content["next_context"], [{"text": "next"}])
        self.assertNotIn("global_transcript", content)
        self.assertIn("exactly these IDs", prompt)

    def test_retry_failure_falls_back_only_current_batch(self) -> None:
        class TwoBatchCorrector:
            def __init__(self):
                self.batch_calls = 0
                self.retry_calls = 0

            def correct_batch(self, language, current, *args):
                self.batch_calls += 1
                if self.batch_calls == 1:
                    return [
                        {"id": item["id"], "corrected_text": f"saved: {item['text']}"}
                        for item in current
                    ]
                return [{"id": current[0]["id"], "corrected_text": "missing second"}]

            def retry_correction_batch(self, language, current, *args):
                self.retry_calls += 1
                return [
                    {"id": current[0]["id"], "corrected_text": "still missing"},
                    {"id": 999, "corrected_text": "extra"},
                ]

        source = [
            {"id": index, "start": index + 0.1, "end": index + 0.9, "text": f"raw {index}"}
            for index in range(4)
        ]
        provider = TwoBatchCorrector()
        with patch.dict(
            "os.environ", {"TRANSCRIPT_CORRECTION_BATCH_SIZE": "2"}
        ), self.assertLogs(
            "uvicorn.error.transcript_correction", level="WARNING"
        ) as logs:
            result = correct_transcript_with_metadata(source, "en", provider)

        self.assertEqual(provider.retry_calls, 1)
        self.assertEqual(result.metadata["retry_batches"], 1)
        self.assertEqual(result.metadata["retry_successes"], 0)
        self.assertEqual(result.metadata["failed_batches"], 1)
        self.assertTrue(result.metadata["fallback"])
        self.assertEqual(
            [item["corrected_text"] for item in result.segments[:2]],
            ["saved: raw 0", "saved: raw 1"],
        )
        self.assertEqual(
            [item["corrected_text"] for item in result.segments[2:]],
            ["raw 2", "raw 3"],
        )
        output = "\n".join(logs.output)
        self.assertIn("retry FAILED", output)
        self.assertIn("fallback to raw/corrected baseline", output)


if __name__ == "__main__":
    unittest.main()
