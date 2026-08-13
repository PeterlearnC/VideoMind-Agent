"""Tests for bilingual subtitle generation and its API."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.api.bilingual_subtitle import generate_bilingual_subtitle_api
from app.main import app
from app.services.bilingual_subtitle_service import generate_bilingual_subtitle


class BilingualSubtitleServiceTests(unittest.TestCase):
    def test_regeneration_clears_edits_and_resets_editor_metadata(self) -> None:
        source = [{"id": 1, "start": 0, "end": 2, "text": "new baseline"}]
        corrected = [{
            "id": 1, "start": 0, "end": 2,
            "raw_text": "new baseline", "corrected_text": "corrected baseline",
        }]
        translated = [{"id": 1, "start": 0, "end": 2, "text": "新基线"}]
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "bilingual.srt"
            output_path.with_suffix(".json").write_text(json.dumps({
                "metadata": {"editor": {"edited_cues": 1, "version": 9}},
                "subtitles": [{
                    "id": 1,
                    "edited_source_text": "old human source",
                    "edited_translated_text": "old human translation",
                }],
            }), encoding="utf-8")
            with patch(
                "app.services.bilingual_subtitle_service.correct_transcript_with_fallback",
                return_value=corrected,
            ), patch(
                "app.services.bilingual_subtitle_service.translation_service.translate_segments",
                return_value=translated,
            ):
                generate_bilingual_subtitle(source, "en", output_path, "zh")

            stored = json.loads(output_path.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertIsNone(stored["subtitles"][0]["edited_source_text"])
            self.assertIsNone(stored["subtitles"][0]["edited_translated_text"])
            self.assertEqual(stored["metadata"]["editor"], {
                "edited_cues": 0, "last_modified": None, "version": 1,
            })

    def test_translates_via_translation_service_and_writes_bilingual_srt(self) -> None:
        segments = [
            {
                "start": 0,
                "end": 4,
                "text": "Turning left, turning left, turning right.",
            }
        ]
        translated = [
            {
                "id": 0,
                "start": 0,
                "end": 4,
                "text": "向左转，向左转，向右转。",
            }
        ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "bilingual.srt"
            with patch(
                "app.services.bilingual_subtitle_service."
                "correct_transcript_with_fallback",
                return_value=[
                    {
                        "id": 0,
                        "start": 0,
                        "end": 4,
                        "raw_text": segments[0]["text"],
                        "corrected_text": segments[0]["text"],
                    }
                ],
            ), patch(
                "app.services.bilingual_subtitle_service."
                "translation_service.translate_segments",
                return_value=translated,
            ) as translate:
                result = generate_bilingual_subtitle(
                    segments,
                    "en",
                    output_path,
                )

            self.assertEqual(result, output_path)
            translate.assert_called_once_with(
                [
                    {
                        "id": 0,
                        "start": 0,
                        "end": 4,
                        "text": segments[0]["text"],
                    }
                ],
                source_language="en",
                target_language="zh",
            )
            self.assertEqual(
                output_path.read_text(encoding="utf-8"),
                "1\n"
                "00:00:00,000 --> 00:00:04,000\n"
                "Turning left, turning left, turning right.\n"
                "向左转，向左转，向右转。\n",
            )
            structured = json.loads(
                output_path.with_suffix(".json").read_text(encoding="utf-8")
            )
            self.assertEqual(structured["metadata"]["workspace"], {
                "video_name": None,
                "source_language": "en",
                "target_language": "zh",
            })
            self.assertEqual(
                structured["correction"],
                {
                    "enabled": True,
                    "attempted": True,
                    "success": True,
                    "fallback": False,
                    "changed_segments": 0,
                    "total_segments": 1,
                    "batches": 1,
                    "failed_batches": 0,
                    "retry_batches": 0,
                    "retry_successes": 0,
                    "zero_change_warning": False,
                    "error": None,
                },
            )

    def test_rejects_mismatched_translated_segment_count(self) -> None:
        segments = [{"start": 0, "end": 4, "text": "Turning left."}]

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "bilingual.srt"
            with patch(
                "app.services.bilingual_subtitle_service."
                "translation_service.translate_segments",
                return_value=[],
            ):
                with self.assertRaisesRegex(ValueError, "counts do not match"):
                    generate_bilingual_subtitle(segments, "en", output_path)

    def test_same_language_writes_monolingual_srt_with_whisper_timeline(self) -> None:
        segments = [
            {
                "id": 8,
                "start": 1.125,
                "end": 3.875,
                "text": "こんにちは",
            }
        ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "monolingual.srt"
            corrected = [
                {
                    "id": 8,
                    "start": 1.125,
                    "end": 3.875,
                    "raw_text": "こんにちは",
                    "corrected_text": "今日は",
                }
            ]
            with patch(
                "app.services.bilingual_subtitle_service."
                "correct_transcript_with_fallback",
                return_value=corrected,
            ), patch(
                "app.services.translation_service._get_translator"
            ) as get_translator:
                result = generate_bilingual_subtitle(
                    segments, "ja", output_path, "ja"
                )

            get_translator.assert_not_called()
            self.assertEqual(result, output_path)
            self.assertEqual(
                output_path.read_text(encoding="utf-8"),
                "1\n"
                "00:00:01,125 --> 00:00:03,875\n"
                "今日は\n",
            )

    def test_translation_uses_corrected_text(self) -> None:
        source = [{"id": 1, "start": 0, "end": 2, "text": "wrong term"}]
        corrected = [
            {
                "id": 1,
                "start": 0,
                "end": 2,
                "raw_text": "wrong term",
                "corrected_text": "correct term",
            }
        ]
        translated = [{"id": 1, "start": 0, "end": 2, "text": "正确术语"}]

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "bilingual.srt"
            with patch(
                "app.services.bilingual_subtitle_service."
                "correct_transcript_with_fallback",
                return_value=corrected,
            ), patch(
                "app.services.bilingual_subtitle_service."
                "translation_service.translate_segments",
                return_value=translated,
            ) as translate:
                generate_bilingual_subtitle(source, "en", output_path, "zh")

        translation_input = translate.call_args.args[0]
        self.assertEqual(translation_input[0]["text"], "correct term")
        self.assertEqual(translation_input[0]["start"], 0)
        self.assertEqual(translation_input[0]["end"], 2)

    def test_failure_metadata_is_written_without_api_key(self) -> None:
        source = [{"id": 1, "start": 0, "end": 2, "text": "raw text"}]
        corrected = [
            {
                "id": 1,
                "start": 0,
                "end": 2,
                "raw_text": "raw text",
                "corrected_text": "raw text",
            }
        ]
        metadata = {
            "enabled": True,
            "attempted": True,
            "success": False,
            "fallback": True,
            "changed_segments": 0,
            "total_segments": 1,
            "batches": 1,
            "failed_batches": 1,
            "zero_change_warning": False,
            "error": "DeepSeek correction failed: HTTP 503",
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "bilingual.srt"
            from app.services.transcript_correction_service import TranscriptCorrectionResult

            with patch(
                "app.services.bilingual_subtitle_service.correct_transcript_with_fallback",
                return_value=TranscriptCorrectionResult(corrected, metadata),
            ), patch(
                "app.services.bilingual_subtitle_service.translation_service.translate_segments",
                return_value=[{"id": 1, "start": 0, "end": 2, "text": "raw text"}],
            ):
                generate_bilingual_subtitle(source, "en", output_path, "en")

            content = output_path.with_suffix(".json").read_text(encoding="utf-8")
            structured = json.loads(content)
            self.assertEqual(structured["correction"], metadata)
            self.assertNotIn("api_key", content.casefold())


class BilingualSubtitleApiTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.api.bilingual_subtitle.generate_bilingual_subtitle")
    @patch("app.api.bilingual_subtitle.transcribe_video", new_callable=AsyncMock)
    async def test_api_runs_complete_pipeline(
        self,
        transcribe_video: AsyncMock,
        generate_subtitle,
    ) -> None:
        segments = [{"start": 0, "end": 4, "text": "Turning left."}]
        transcribe_video.return_value = {
            "filename": "video.mp4",
            "language": "en",
            "segments": segments,
        }
        expected_path = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "subtitles"
            / "bilingual.srt"
        )
        generate_subtitle.return_value = expected_path

        result = await generate_bilingual_subtitle_api(object())

        self.assertEqual(
            result,
            {
                "filename": "video.mp4",
                "language": "en",
                "source_language": "en",
                "target_language": "zh",
                "subtitle_file": "data/subtitles/bilingual.srt",
            },
        )
        transcribe_video.assert_awaited_once()
        generate_subtitle.assert_called_once_with(
            segments,
            "en",
            expected_path,
            "zh",
            "video.mp4",
        )

    @patch("app.api.bilingual_subtitle.transcribe_video", new_callable=AsyncMock)
    async def test_api_rejects_unsupported_source_language(
        self,
        transcribe_video: AsyncMock,
    ) -> None:
        transcribe_video.return_value = {
            "filename": "video.mp4",
            "language": "fr",
            "segments": [],
        }

        with self.assertRaises(HTTPException) as raised:
            await generate_bilingual_subtitle_api(object())

        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("Unsupported source language: fr", raised.exception.detail)

    @patch("app.api.bilingual_subtitle.transcribe_video", new_callable=AsyncMock)
    async def test_api_rejects_unsupported_target_language(
        self, transcribe_video: AsyncMock
    ) -> None:
        transcribe_video.return_value = {
            "filename": "video.mp4",
            "language": "en",
            "segments": [],
        }

        with self.assertRaises(HTTPException) as raised:
            await generate_bilingual_subtitle_api(object(), "th")

        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("Unsupported target language: th", raised.exception.detail)

    @patch("app.api.bilingual_subtitle.generate_bilingual_subtitle")
    @patch("app.api.bilingual_subtitle.transcribe_video", new_callable=AsyncMock)
    async def test_api_allows_source_equal_to_target(
        self, transcribe_video: AsyncMock, generate_subtitle
    ) -> None:
        transcribe_video.return_value = {
            "filename": "video.mp4",
            "language": "ja",
            "segments": [{"id": 0, "start": 0, "end": 1, "text": "こんにちは"}],
        }
        expected_path = Path(__file__).resolve().parents[2] / "data/subtitles/bilingual.srt"
        generate_subtitle.return_value = expected_path

        result = await generate_bilingual_subtitle_api(object(), "ja")

        self.assertEqual(result["source_language"], "ja")
        self.assertEqual(result["target_language"], "ja")
        generate_subtitle.assert_called_once_with(
            transcribe_video.return_value["segments"],
            "ja",
            expected_path,
            "ja",
            "video.mp4",
        )

    @patch("app.api.bilingual_subtitle.generate_bilingual_subtitle")
    @patch("app.api.bilingual_subtitle.transcribe_video", new_callable=AsyncMock)
    async def test_non_english_source_defaults_to_english(
        self, transcribe_video: AsyncMock, generate_subtitle
    ) -> None:
        segments = [{"id": 0, "start": 0, "end": 1, "text": "こんにちは"}]
        transcribe_video.return_value = {
            "filename": "video.mp4",
            "language": "ja",
            "segments": segments,
        }
        expected_path = Path(__file__).resolve().parents[2] / "data/subtitles/bilingual.srt"
        generate_subtitle.return_value = expected_path

        result = await generate_bilingual_subtitle_api(object())

        self.assertEqual(result["source_language"], "ja")
        self.assertEqual(result["target_language"], "en")
        generate_subtitle.assert_called_once_with(
            segments, "ja", expected_path, "en", "video.mp4"
        )

    def test_new_and_existing_routes_are_registered(self) -> None:
        paths = set(app.openapi()["paths"])
        self.assertIn("/generate-bilingual-subtitle", paths)
        self.assertIn("/transcribe-video", paths)
        self.assertIn("/generate-subtitle", paths)
        self.assertIn("/translate-subtitle", paths)


if __name__ == "__main__":
    unittest.main()
