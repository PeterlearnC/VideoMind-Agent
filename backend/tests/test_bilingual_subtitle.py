"""Tests for bilingual subtitle generation and its API."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.api.bilingual_subtitle import generate_bilingual_subtitle_api
from app.main import app
from app.services.bilingual_subtitle_service import generate_bilingual_subtitle


class BilingualSubtitleServiceTests(unittest.TestCase):
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
                segments,
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
                "subtitle_file": "data/subtitles/bilingual.srt",
            },
        )
        transcribe_video.assert_awaited_once()
        generate_subtitle.assert_called_once_with(
            segments,
            "en",
            expected_path,
            "zh",
        )

    @patch("app.api.bilingual_subtitle.transcribe_video", new_callable=AsyncMock)
    async def test_api_rejects_non_english_video(
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

    def test_new_and_existing_routes_are_registered(self) -> None:
        paths = set(app.openapi()["paths"])
        self.assertIn("/generate-bilingual-subtitle", paths)
        self.assertIn("/transcribe-video", paths)
        self.assertIn("/generate-subtitle", paths)
        self.assertIn("/translate-subtitle", paths)


if __name__ == "__main__":
    unittest.main()