"""Competition Demo mode stays usable without exposing or requiring an API key."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.api.competition_demo import get_competition_demo_status
from app.api.qa import VideoQARequest, answer_video_question
from app.api.summary import SummaryRequest, generate_video_summary
from app.config.competition_demo import (
    competition_demo_mode_enabled,
    deepseek_api_key_configured,
    require_cloud_ai_available,
)
from app.main import app
from app.services import competition_demo_service


class CompetitionDemoTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.demo_environment = patch.dict(
            os.environ,
            {"COMPETITION_DEMO_MODE": "true", "DEEPSEEK_API_KEY": ""},
            clear=False,
        )
        self.demo_environment.start()

    def tearDown(self) -> None:
        self.demo_environment.stop()

    def test_mode_without_api_key_is_enabled_and_cloud_calls_are_friendly(self) -> None:
        self.assertTrue(competition_demo_mode_enabled())
        with self.assertRaises(HTTPException) as raised:
            require_cloud_ai_available()
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("Competition Demo Mode", str(raised.exception.detail))
        self.assertIn("DEEPSEEK_API_KEY", str(raised.exception.detail))

    def test_empty_and_placeholder_api_keys_are_never_configured(self) -> None:
        for value in ("", "   ", "your_api_key_here", "placeholder", "your_deepseek_api_key"):
            with self.subTest(value=repr(value)), patch.dict(
                os.environ, {"DEEPSEEK_API_KEY": value}, clear=False
            ):
                self.assertFalse(deepseek_api_key_configured())

    def test_non_placeholder_api_key_is_configured_without_exposing_it(self) -> None:
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "configured-test-value"}, clear=False):
            self.assertTrue(deepseek_api_key_configured())

    async def test_preloaded_workspace_summary_and_qa_are_available(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            runtime = Path(temporary_directory)
            with patch.object(competition_demo_service, "VIDEO_DIR", runtime / "videos"), patch.object(
                competition_demo_service, "SUBTITLE_DIR", runtime / "subtitles"
            ):
                payload = await get_competition_demo_status()
                workspace_file = runtime / "subtitles" / "competition-demo.json"
                video_file = runtime / "videos" / "competition-demo.mp4"
                workspace_file_exists = workspace_file.is_file()
                video_file_exists = video_file.is_file()
                workspace = json.loads(workspace_file.read_text(encoding="utf-8"))

        self.assertTrue(payload["enabled"])
        self.assertFalse(payload["api_key_configured"])
        self.assertEqual(payload["workspace"]["video_id"], "competition-demo")
        self.assertTrue(payload["summary"]["title"])
        self.assertTrue(payload["qa_history"][0]["references"])
        self.assertTrue(workspace_file_exists)
        self.assertTrue(video_file_exists)
        self.assertEqual(len(workspace["subtitles"]), 3)

    async def test_new_summary_and_qa_are_blocked_before_agents_run(self) -> None:
        with self.assertRaises(HTTPException) as summary_error:
            await generate_video_summary("competition-demo", SummaryRequest())
        with self.assertRaises(HTTPException) as qa_error:
            await answer_video_question(
                "competition-demo", VideoQARequest(question="What happens?")
            )
        self.assertEqual(summary_error.exception.status_code, 409)
        self.assertEqual(qa_error.exception.status_code, 409)

    def test_normal_mode_behavior_is_unchanged(self) -> None:
        with patch.dict(
            os.environ,
            {"COMPETITION_DEMO_MODE": "false", "DEEPSEEK_API_KEY": ""},
            clear=False,
        ):
            require_cloud_ai_available()

    def test_route_is_registered(self) -> None:
        self.assertIn("/competition-demo/status", app.openapi()["paths"])


if __name__ == "__main__":
    unittest.main()
