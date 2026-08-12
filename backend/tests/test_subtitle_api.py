"""Tests for the JSON subtitle track API."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app.api.subtitle import get_subtitle, parse_srt
from app.main import app


class SubtitleParserTests(unittest.TestCase):
    def test_parses_bilingual_srt_with_numeric_timestamps(self) -> None:
        content = (
            "1\n"
            "00:00:01,250 --> 00:00:03,500\n"
            "Hello, world.\n"
            "你好，世界。\n\n"
            "2\n"
            "00:01:00,000 --> 00:01:02,125\n"
            "Next line.\n"
            "下一句。\n"
        )

        self.assertEqual(
            parse_srt(content),
            [
                {
                    "id": "1",
                    "start": 1.25,
                    "end": 3.5,
                    "source": "Hello, world.",
                    "translation": "你好，世界。",
                    "source_text": "Hello, world.",
                    "translated_text": "你好，世界。",
                },
                {
                    "id": "2",
                    "start": 60.0,
                    "end": 62.125,
                    "source": "Next line.",
                    "translation": "下一句。",
                    "source_text": "Next line.",
                    "translated_text": "下一句。",
                },
            ],
        )


class SubtitleApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_reads_requested_subtitle_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            subtitle_directory = Path(temporary_directory)
            (subtitle_directory / "demo.srt").write_text(
                "1\n00:00:00,000 --> 00:00:02,000\nHello\n你好\n",
                encoding="utf-8",
            )
            with patch("app.api.subtitle.SUBTITLE_DIR", subtitle_directory):
                result = await get_subtitle("demo")

        self.assertEqual(result["video_id"], "demo")
        self.assertEqual(result["subtitles"][0]["translation"], "你好")

    async def test_prefers_structured_raw_and_corrected_transcript_sidecar(self) -> None:
        structured = {
            "source_language": "en",
            "target_language": "zh",
            "correction": {
                "enabled": True,
                "attempted": True,
                "success": True,
                "fallback": False,
                "changed_segments": 1,
                "total_segments": 1,
                "batches": 1,
                "failed_batches": 0,
                "zero_change_warning": False,
                "error": None,
            },
            "subtitles": [
                {
                    "id": 0,
                    "start": 1.25,
                    "end": 3.5,
                    "raw_text": "wrong name",
                    "corrected_text": "correct name",
                    "translations": {"zh": "正确名称"},
                    "source": "correct name",
                    "translation": "正确名称",
                    "source_text": "correct name",
                    "translated_text": "正确名称",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            subtitle_directory = Path(temporary_directory)
            (subtitle_directory / "demo.srt").write_text(
                "1\n00:00:01,250 --> 00:00:03,500\nlegacy\n旧值\n",
                encoding="utf-8",
            )
            (subtitle_directory / "demo.json").write_text(
                json.dumps(structured, ensure_ascii=False), encoding="utf-8"
            )
            with patch("app.api.subtitle.SUBTITLE_DIR", subtitle_directory):
                result = await get_subtitle("demo")

        self.assertEqual(result["source_language"], "en")
        self.assertEqual(result["target_language"], "zh")
        self.assertEqual(result["correction"]["changed_segments"], 1)
        self.assertEqual(result["subtitles"][0]["raw_text"], "wrong name")
        self.assertEqual(result["subtitles"][0]["corrected_text"], "correct name")

    async def test_returns_404_for_missing_track(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch("app.api.subtitle.SUBTITLE_DIR", Path(temporary_directory)):
                with self.assertRaises(HTTPException) as raised:
                    await get_subtitle("missing")

        self.assertEqual(raised.exception.status_code, 404)

    def test_route_is_registered(self) -> None:
        self.assertIn("/subtitle/{video_id}", app.openapi()["paths"])


if __name__ == "__main__":
    unittest.main()
