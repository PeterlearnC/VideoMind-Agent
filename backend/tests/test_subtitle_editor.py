"""Tests for file-backed subtitle editing, effective text, and SRT export."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.api.subtitle_editor import (
    BatchUpdateRequest,
    CueUpdate,
    ResetRequest,
    export_edited_srt,
    get_editor,
    patch_cue,
    patch_cues,
    reset_editor_cue,
)
from app.main import app
from app.services.subtitle_editor_service import atomic_write_json


def track() -> dict[str, object]:
    return {
        "source_language": "zh",
        "target_language": "en",
        "correction": {"success": True},
        "metadata": {"correction": {"success": True}, "editor": {"edited_cues": 0, "last_modified": None, "version": 1}},
        "subtitles": [
            {
                "id": 1, "start": 1.25, "end": 3.5,
                "raw_text": "水泥的售命", "corrected_text": "水泥的寿命",
                "translated_text": "The life of cement",
                "edited_source_text": None, "edited_translated_text": None,
            },
            {
                "id": 2, "start": 3.5, "end": 5.75,
                "raw_text": "两马事儿", "corrected_text": "两码事儿",
                "translated_text": "two different things",
                "edited_source_text": None, "edited_translated_text": None,
            },
        ],
    }


class SubtitleEditorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.path = self.directory / "demo.json"
        self.path.write_text(json.dumps(track(), ensure_ascii=False), encoding="utf-8")
        self.patch = patch("app.api.subtitle_editor.SUBTITLE_DIR", self.directory)
        self.patch.start()

    def tearDown(self) -> None:
        self.patch.stop()
        self.temporary.cleanup()

    async def test_get_editor_data_and_effective_baseline(self) -> None:
        payload = await get_editor("demo")
        cue = payload["subtitles"][0]
        self.assertEqual(cue["raw_text"], "水泥的售命")
        self.assertEqual(cue["effective_source_text"], "水泥的寿命")
        self.assertEqual(cue["effective_translated_text"], "The life of cement")
        self.assertFalse(cue["is_source_edited"])

    async def test_edit_source_only_preserves_all_ai_baselines(self) -> None:
        cue = await patch_cue("demo", "1", CueUpdate(source_text="水泥的使用寿命"))
        stored = json.loads(self.path.read_text(encoding="utf-8"))["subtitles"][0]
        self.assertEqual(cue["effective_source_text"], "水泥的使用寿命")
        self.assertEqual(stored["raw_text"], "水泥的售命")
        self.assertEqual(stored["corrected_text"], "水泥的寿命")
        self.assertEqual(stored["translated_text"], "The life of cement")
        self.assertEqual(stored["edited_source_text"], "水泥的使用寿命")
        self.assertIsNone(stored["edited_translated_text"])

    async def test_edit_translation_only_and_both(self) -> None:
        cue = await patch_cue("demo", "1", CueUpdate(translated_text="Cement service life"))
        self.assertEqual(cue["effective_translated_text"], "Cement service life")
        cue = await patch_cue("demo", "1", CueUpdate(source_text="人工原文", translated_text="Human translation"))
        self.assertEqual(cue["effective_source_text"], "人工原文")
        self.assertEqual(cue["effective_translated_text"], "Human translation")

    async def test_invalid_video_and_cue_return_404(self) -> None:
        with self.assertRaises(HTTPException) as missing_video:
            await get_editor("missing")
        self.assertEqual(missing_video.exception.status_code, 404)
        self.assertEqual(missing_video.exception.detail, "Subtitle document not found.")
        with self.assertRaises(HTTPException) as missing_cue:
            await patch_cue("demo", "999", CueUpdate(source_text="valid"))
        self.assertEqual(missing_cue.exception.status_code, 404)
        self.assertEqual(missing_cue.exception.detail, "Subtitle cue not found.")

    def test_blank_source_and_translation_are_rejected(self) -> None:
        for kwargs in ({"source_text": "   "}, {"translated_text": "\n"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                CueUpdate(**kwargs)

    def test_editor_validation_uses_stable_public_messages(self) -> None:
        with self.assertRaisesRegex(ValidationError, "Subtitle text cannot be blank"):
            CueUpdate(source_text=" ")
        with self.assertRaisesRegex(ValidationError, "Subtitle text exceeds maximum length"):
            CueUpdate(source_text="x" * 5001)

    async def test_reset_source_translation_and_all(self) -> None:
        await patch_cue("demo", "1", CueUpdate(source_text="人工原文", translated_text="Human"))
        source_reset = await reset_editor_cue("demo", "1", ResetRequest(field="source"))
        self.assertEqual(source_reset["effective_source_text"], "水泥的寿命")
        self.assertEqual(source_reset["effective_translated_text"], "Human")
        translation_reset = await reset_editor_cue("demo", "1", ResetRequest(field="translation"))
        self.assertEqual(translation_reset["effective_translated_text"], "The life of cement")
        await patch_cue("demo", "1", CueUpdate(source_text="again", translated_text="again"))
        all_reset = await reset_editor_cue("demo", "1", ResetRequest(field="all"))
        self.assertFalse(all_reset["is_source_edited"])
        self.assertFalse(all_reset["is_translation_edited"])

    async def test_batch_update_persists_only_edited_fields(self) -> None:
        request = BatchUpdateRequest(updates=[
            {"id": 1, "source_text": "人工一"},
            {"id": 2, "translated_text": "Human two"},
        ])
        result = await patch_cues("demo", request)
        self.assertEqual(result["updated"], 2)
        stored = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(stored["metadata"]["editor"]["edited_cues"], 2)
        self.assertEqual(stored["subtitles"][0]["edited_source_text"], "人工一")
        self.assertEqual(stored["subtitles"][1]["edited_translated_text"], "Human two")

    async def test_batch_invalid_id_does_not_partially_write(self) -> None:
        before = self.path.read_text(encoding="utf-8")
        request = BatchUpdateRequest(updates=[
            {"id": 1, "source_text": "would change"},
            {"id": 999, "source_text": "missing"},
        ])
        with self.assertRaises(HTTPException) as raised:
            await patch_cues("demo", request)
        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    async def test_export_uses_effective_text_and_whisper_timeline(self) -> None:
        await patch_cue("demo", "1", CueUpdate(source_text="人工原文", translated_text="Human translation"))
        response = await export_edited_srt("demo")
        content = response.body.decode("utf-8")
        self.assertIn("00:00:01,250 --> 00:00:03,500", content)
        self.assertIn("人工原文\nHuman translation", content)
        self.assertNotIn("水泥的售命", content)

    async def test_same_language_export_is_monolingual_effective_source(self) -> None:
        data = track()
        data["target_language"] = "zh"
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        await patch_cue("demo", "1", CueUpdate(source_text="人工单语字幕", translated_text="不应导出"))
        response = await export_edited_srt("demo")
        content = response.body.decode("utf-8")
        self.assertIn("人工单语字幕", content)
        self.assertNotIn("不应导出", content)

    async def test_export_invalid_subtitle_document(self) -> None:
        self.path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(HTTPException) as raised:
            await export_edited_srt("demo")
        self.assertEqual(raised.exception.status_code, 500)
        self.assertEqual(raised.exception.detail, "Invalid subtitle document.")

    async def test_export_invalid_timeline(self) -> None:
        data = track()
        data["subtitles"][0]["end"] = 0.5
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(HTTPException) as raised:
            await export_edited_srt("demo")
        self.assertEqual(raised.exception.status_code, 500)
        self.assertIn("invalid cue timeline", raised.exception.detail)

    async def test_export_blank_effective_source(self) -> None:
        data = track()
        data["subtitles"][0]["corrected_text"] = "   "
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(HTTPException) as raised:
            await export_edited_srt("demo")
        self.assertEqual(raised.exception.status_code, 500)
        self.assertIn("effective source text is blank", raised.exception.detail)

    def test_atomic_write_uses_replace_and_leaves_valid_json(self) -> None:
        destination = self.directory / "atomic.json"
        with patch("app.services.subtitle_editor_service.os.replace", wraps=__import__("os").replace) as replace:
            atomic_write_json(destination, {"value": "完整"})
        replace.assert_called_once()
        self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), {"value": "完整"})

    def test_routes_are_registered(self) -> None:
        paths = app.openapi()["paths"]
        self.assertIn("/subtitle/editor/{video_id}", paths)
        self.assertIn("/subtitle/editor/{video_id}/{cue_id}", paths)
        self.assertIn("/subtitle/{video_id}/export", paths)


if __name__ == "__main__":
    unittest.main()
