"""Tests for restoring the saved source video for an active workspace."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.api.video import get_workspace_video
from app.main import app


class WorkspaceRestoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_video_referenced_by_workspace_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            subtitle_directory = root / "subtitles"
            video_directory = root / "videos"
            subtitle_directory.mkdir()
            video_directory.mkdir()
            video_path = video_directory / "sample.mp4"
            video_path.write_bytes(b"video")
            (subtitle_directory / "bilingual.json").write_text(json.dumps({
                "metadata": {"workspace": {"video_name": "sample.mp4"}},
            }), encoding="utf-8")
            with patch("app.api.video.SUBTITLE_DIR", subtitle_directory), patch(
                "app.api.video.VIDEO_DIR", video_directory
            ):
                response = await get_workspace_video("bilingual")

        self.assertIsInstance(response, FileResponse)
        self.assertEqual(Path(response.path).name, "sample.mp4")

    async def test_missing_or_unsafe_workspace_video_returns_404(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            subtitle_directory = root / "subtitles"
            video_directory = root / "videos"
            subtitle_directory.mkdir()
            video_directory.mkdir()
            (subtitle_directory / "bilingual.json").write_text(json.dumps({
                "metadata": {"workspace": {"video_name": "../outside.mp4"}},
            }), encoding="utf-8")
            with patch("app.api.video.SUBTITLE_DIR", subtitle_directory), patch(
                "app.api.video.VIDEO_DIR", video_directory
            ), self.assertRaises(HTTPException) as raised:
                await get_workspace_video("bilingual")
        self.assertEqual(raised.exception.status_code, 404)

    def test_video_restore_route_is_registered(self) -> None:
        self.assertIn("/video/{video_id}", app.openapi()["paths"])


if __name__ == "__main__":
    unittest.main()
