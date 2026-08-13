"""Unit tests for best-effort performance observations."""

from __future__ import annotations

import asyncio
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import UploadFile

from app.services.performance_metrics import (
    PerformanceRun,
    activate_run,
    collect_video_metadata,
    find_latest_report,
    map_correction_metadata,
    observe_operation,
    reset_active_run,
    validate_timeline,
)


class FakeClock:
    def __init__(self, values: list[float]) -> None:
        self.values = iter(values)

    def __call__(self) -> float:
        return next(self.values)


class PerformanceMetricsTests(unittest.TestCase):
    def test_video_metadata_is_collected_and_serialized(self) -> None:
        probe_output = json.dumps({
            "streams": [{
                "width": 1920,
                "height": 1080,
                "codec_name": "h264",
                "avg_frame_rate": "30000/1001",
                "r_frame_rate": "30/1",
            }],
            "format": {"duration": "4519.76"},
        })
        with tempfile.TemporaryDirectory() as directory:
            video_path = Path(directory) / "lecture.mp4"
            video_path.write_bytes(b"metadata-test")
            runner = unittest.mock.Mock(
                return_value=subprocess.CompletedProcess([], 0, probe_output, "")
            )
            metadata = collect_video_metadata(video_path, runner=runner)

            self.assertEqual(metadata["filename"], "lecture.mp4")
            self.assertEqual(metadata["file_size_bytes"], 13)
            self.assertEqual(metadata["video_duration_seconds"], 4519.76)
            self.assertEqual(metadata["width"], 1920)
            self.assertEqual(metadata["height"], 1080)
            self.assertEqual(metadata["resolution"], "1920x1080")
            self.assertAlmostEqual(metadata["fps"], 29.97003, places=5)
            self.assertEqual(metadata["codec"], "h264")
            self.assertEqual(metadata["metadata_collection_status"], "success")

            run = PerformanceRun(report_dir=Path(directory))
            run.set_video(**metadata)
            report_path = run.save_report()
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["video"]["resolution"], "1920x1080")
            self.assertEqual(payload["video"]["video_duration_seconds"], 4519.76)
            self.assertEqual(payload["video"]["duration_seconds"], 4519.76)
            self.assertEqual(payload["video"]["duration_hms"], "01:15:19")

    def test_ffprobe_failure_is_nonblocking_and_preserves_stat_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            video_path = Path(directory) / "lecture.mp4"
            video_path.write_bytes(b"1234")
            runner = unittest.mock.Mock(
                side_effect=subprocess.CalledProcessError(1, ["ffprobe"])
            )

            metadata = collect_video_metadata(video_path, runner=runner)

            self.assertEqual(metadata["filename"], "lecture.mp4")
            self.assertEqual(metadata["file_size_bytes"], 4)
            self.assertIsNone(metadata["video_duration_seconds"])
            self.assertIsNone(metadata["resolution"])
            self.assertEqual(metadata["metadata_collection_status"], "partial")
            self.assertEqual(
                metadata["metadata_collection_error_type"], "CalledProcessError"
            )

    def test_metadata_instrumentation_failure_does_not_stop_transcription(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = PerformanceRun(report_dir=root / "performance")
            token = activate_run(run)
            upload = UploadFile(filename="lecture.mp4", file=io.BytesIO(b"video"))
            try:
                with (
                    patch("app.api.video.VIDEO_DIR", root / "videos"),
                    patch("app.api.video.AUDIO_DIR", root / "audio"),
                    patch("app.api.video._extract_audio"),
                    patch(
                        "app.api.video.collect_video_metadata",
                        side_effect=RuntimeError("probe unavailable"),
                    ),
                    patch(
                        "app.api.video.transcribe_audio",
                        return_value={
                            "language": "en",
                            "segments": [{"id": 0, "start": 0, "end": 1, "text": "ok"}],
                        },
                    ),
                ):
                    result = asyncio.run(
                        __import__(
                            "app.api.video", fromlist=["transcribe_video"]
                        ).transcribe_video(upload)
                    )
            finally:
                reset_active_run(token)

            self.assertEqual(result["language"], "en")
            self.assertEqual(len(result["segments"]), 1)
            self.assertEqual(
                run.data["video"]["metadata_collection_status"], "failed"
            )
            self.assertEqual(
                run.data["video"]["metadata_collection_error_type"], "RuntimeError"
            )

    def test_stage_records_nonnegative_duration(self) -> None:
        run = PerformanceRun(clock=FakeClock([1.0, 2.0, 3.25]))
        with run.stage("whisper_transcription") as stage:
            stage.update(raw_segment_count=12)
        saved = run.data["pipeline"]["stages"]["whisper_transcription"]
        self.assertTrue(saved["success"])
        self.assertEqual(saved["duration_seconds"], 1.25)
        self.assertEqual(saved["raw_segment_count"], 12)

    def test_stage_exception_is_failed_and_propagates(self) -> None:
        run = PerformanceRun(clock=FakeClock([1.0, 2.0, 2.5]))
        with self.assertRaisesRegex(ValueError, "business failure"):
            with run.stage("translation"):
                raise ValueError("business failure")
        saved = run.data["pipeline"]["stages"]["translation"]
        self.assertFalse(saved["success"])
        self.assertEqual(saved["error_type"], "ValueError")

    def test_writes_run_and_latest_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = PerformanceRun(report_dir=Path(directory))
            path = run.save_report()
            self.assertIsNotNone(path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["run_id"], run.run_id)
            self.assertTrue((Path(directory) / "latest.json").is_file())

    def test_json_write_failure_is_nonblocking(self) -> None:
        run = PerformanceRun()
        with patch(
            "app.services.performance_metrics._atomic_write",
            side_effect=OSError("disk full"),
        ):
            self.assertIsNone(run.save_report())

    def test_total_pipeline_uses_elapsed_clock_not_stage_sum(self) -> None:
        run = PerformanceRun(clock=FakeClock([5.0, 6.0, 7.0, 10.0]))
        with run.stage("one"):
            pass
        run.finish_pipeline(True)
        self.assertEqual(run.data["pipeline"]["total_duration_seconds"], 5.0)
        self.assertGreaterEqual(
            run.data["pipeline"]["total_duration_seconds"],
            run.data["pipeline"]["stages"]["one"]["duration_seconds"],
        )

    def test_valid_timeline(self) -> None:
        result = validate_timeline([
            {"id": 0, "start": 0, "end": 2},
            {"id": 1, "start": 2, "end": 5},
        ], 5)
        self.assertTrue(result["passed"])
        self.assertEqual(result["coverage_ratio"], 1.0)
        self.assertEqual(result["timeline_gap_count"], 0)

    def test_duplicate_id(self) -> None:
        result = validate_timeline([
            {"id": "a", "start": 0, "end": 1},
            {"id": "a", "start": 1, "end": 2},
        ])
        self.assertEqual(result["duplicate_ids"], 1)
        self.assertFalse(result["passed"])

    def test_ordering_error(self) -> None:
        result = validate_timeline([
            {"id": 0, "start": 3, "end": 4},
            {"id": 1, "start": 1, "end": 2},
        ])
        self.assertEqual(result["ordering_errors"], 1)
        self.assertFalse(result["passed"])

    def test_invalid_start_end(self) -> None:
        result = validate_timeline([
            {"id": 0, "start": 1, "end": 1},
            {"id": 1, "start": "bad", "end": 2},
        ])
        self.assertEqual(result["invalid_ranges"], 2)
        self.assertFalse(result["passed"])

    def test_null_or_zero_video_duration_has_no_ratio(self) -> None:
        cues = [{"id": 0, "start": 0, "end": 1}]
        self.assertIsNone(validate_timeline(cues, None)["coverage_ratio"])
        self.assertIsNone(validate_timeline(cues, 0)["coverage_ratio"])

    def test_same_language_translation_is_explicitly_skipped(self) -> None:
        run = PerformanceRun()
        run.skip_stage("translation", "same_language", source_language="zh", target_language="zh")
        stage = run.data["pipeline"]["stages"]["translation"]
        self.assertTrue(stage["skipped"])
        self.assertEqual(stage["skip_reason"], "same_language")
        self.assertIsNone(stage["duration_seconds"])

    def test_translation_validation_counters_survive_stage_completion(self) -> None:
        run = PerformanceRun(clock=FakeClock([1.0, 2.0, 3.0]))
        with run.stage("translation"):
            run.set_stage_details(
                "translation",
                translation_validation_warning_count=0,
                translation_validation_retry_count=0,
                translation_validation_failure_count=0,
            )
            run.increment_stage(
                "translation", "translation_validation_warning_count"
            )
        stage = run.data["pipeline"]["stages"]["translation"]
        self.assertEqual(stage["translation_validation_warning_count"], 1)
        self.assertEqual(stage["translation_validation_retry_count"], 0)
        self.assertEqual(stage["translation_validation_failure_count"], 0)

    def test_correction_metadata_maps_existing_fields(self) -> None:
        metadata = {
            "total_segments": 117, "changed_segments": 51, "batches": 3,
            "retry_batches": 1, "retry_successes": 1,
            "failed_batches": 0, "fallback": False,
        }
        self.assertEqual(map_correction_metadata(metadata), {
            "total_segments": 117, "changed_segments": 51, "batch_count": 3,
            "retry_batches": 1, "retry_successes": 1,
            "failed_batches": 0, "fallback": False,
        })

    def _saved_run(self, directory: str) -> PerformanceRun:
        run = PerformanceRun(video_id="bilingual", report_dir=Path(directory))
        run.finish_pipeline(True)
        run.save_report()
        return run

    def test_summary_runs_append(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = self._saved_run(directory)
            for _ in range(2):
                with observe_operation("summary", "bilingual", report_dir=Path(directory)):
                    pass
            payload = json.loads((Path(directory) / f"{run.run_id}.json").read_text(encoding="utf-8"))
            self.assertEqual(len(payload["summary_runs"]), 2)

    def test_qa_runs_append_with_indices(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = self._saved_run(directory)
            for count in (1, 2):
                with observe_operation("qa", "bilingual", report_dir=Path(directory)) as details:
                    details.update(answer_length=20, timestamp_count=count)
            payload = json.loads((Path(directory) / f"{run.run_id}.json").read_text(encoding="utf-8"))
            self.assertEqual([item["question_index"] for item in payload["qa_runs"]], [1, 2])
            self.assertEqual(payload["qa_runs"][1]["timestamp_count"], 2)

    def test_qa_report_never_stores_question_or_answer_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = self._saved_run(directory)
            with observe_operation("qa", "bilingual", report_dir=Path(directory)) as details:
                details.update(answer_length=99, timestamp_count=3)
            content = (Path(directory) / f"{run.run_id}.json").read_text(encoding="utf-8")
            self.assertNotIn("question\"", content)
            self.assertNotIn("answer\"", content)
            self.assertIn("answer_length", content)

    def test_run_ids_are_unique(self) -> None:
        self.assertNotEqual(PerformanceRun().run_id, PerformanceRun().run_id)

    def test_latest_report_matches_video_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = self._saved_run(directory)
            found = find_latest_report("bilingual", Path(directory))
            self.assertEqual(found.name, f"{run.run_id}.json")

    def test_runtime_reports_are_gitignored(self) -> None:
        ignore = (Path(__file__).resolve().parents[2] / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/backend/data/performance/*", ignore)


if __name__ == "__main__":
    unittest.main()
