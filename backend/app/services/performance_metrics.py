"""Best-effort performance observations for video processing runs."""

from __future__ import annotations

import contextvars
import json
import logging
import math
import os
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping


logger = logging.getLogger("uvicorn.error.performance")
PERFORMANCE_DIR = Path(__file__).resolve().parents[2] / "data" / "performance"
SCHEMA_VERSION = 1
_active_run: contextvars.ContextVar[PerformanceRun | None] = contextvars.ContextVar(
    "performance_run", default=None
)
_report_lock = threading.RLock()


def _nullable_positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _nullable_positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _parse_frame_rate(value: Any) -> float | None:
    """Parse ffprobe frame-rate values such as ``30000/1001`` safely."""
    if not isinstance(value, str) or not value.strip():
        return _nullable_positive_float(value)
    numerator, separator, denominator = value.partition("/")
    if separator:
        top = _nullable_positive_float(numerator)
        bottom = _nullable_positive_float(denominator)
        if top is None or bottom is None:
            return None
        return round(top / bottom, 6)
    parsed = _nullable_positive_float(value)
    return round(parsed, 6) if parsed is not None else None


def collect_video_metadata(
    video_path: str | os.PathLike[str],
    *,
    runner=subprocess.run,
) -> dict[str, Any]:
    """Collect file/stream metadata without decoding or reading the media payload.

    The result is deliberately best-effort and this function never raises into the
    video pipeline.  ffprobe reads container metadata only; file size comes from
    ``stat()``.
    """
    path = Path(video_path)
    metadata: dict[str, Any] = {
        "filename": path.name or None,
        "video_name": path.name or None,
        "file_size_bytes": None,
        "video_duration_seconds": None,
        "width": None,
        "height": None,
        "resolution": None,
        "fps": None,
        "codec": None,
        "metadata_collection_status": "failed",
        "metadata_collection_error_type": None,
    }
    try:
        metadata["file_size_bytes"] = path.stat().st_size
    except (OSError, ValueError) as exc:
        metadata["metadata_collection_error_type"] = type(exc).__name__

    try:
        result = runner(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "format=duration:stream=width,height,codec_name,avg_frame_rate,r_frame_rate",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        payload = json.loads(result.stdout)
        streams = payload.get("streams")
        stream = streams[0] if isinstance(streams, list) and streams else {}
        media_format = payload.get("format")
        if not isinstance(stream, Mapping):
            stream = {}
        if not isinstance(media_format, Mapping):
            media_format = {}
        width = _nullable_positive_int(stream.get("width"))
        height = _nullable_positive_int(stream.get("height"))
        metadata.update(
            video_duration_seconds=_nullable_positive_float(
                media_format.get("duration")
            ),
            width=width,
            height=height,
            resolution=f"{width}x{height}" if width and height else None,
            fps=(
                _parse_frame_rate(stream.get("avg_frame_rate"))
                or _parse_frame_rate(stream.get("r_frame_rate"))
            ),
            codec=(
                str(stream["codec_name"]).strip()
                if stream.get("codec_name")
                else None
            ),
        )
        required = (
            "file_size_bytes",
            "video_duration_seconds",
            "width",
            "height",
            "resolution",
            "fps",
            "codec",
        )
        metadata["metadata_collection_status"] = (
            "success" if all(metadata[key] is not None for key in required) else "partial"
        )
        metadata["metadata_collection_error_type"] = None
        logger.info(
            "[PERF] video metadata %s filename=%s resolution=%s",
            metadata["metadata_collection_status"],
            metadata["filename"],
            metadata["resolution"],
        )
    except Exception as exc:  # ffprobe observation must never block processing
        metadata["metadata_collection_status"] = (
            "partial" if metadata["file_size_bytes"] is not None else "failed"
        )
        metadata["metadata_collection_error_type"] = type(exc).__name__
        logger.warning(
            "[PERF] video metadata collection failed error_type=%s",
            type(exc).__name__,
        )
    return metadata


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _duration_hms(seconds: float | None) -> str | None:
    if seconds is None or not math.isfinite(seconds) or seconds < 0:
        return None
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _safe_error_type(error: BaseException | str | None) -> str | None:
    if error is None:
        return None
    return type(error).__name__ if isinstance(error, BaseException) else str(error)


class PerformanceStage:
    """One perf_counter-backed stage that never suppresses business exceptions."""

    def __init__(self, run: "PerformanceRun", name: str, details: Mapping[str, Any] | None = None):
        self.run = run
        self.name = name
        self.details = dict(details or {})
        self.started_at = _utc_now()
        self._started = run._clock()
        self._success_override: bool | None = None
        self._finished = False

    def update(self, **details: Any) -> None:
        self.details.update(details)
        if self._finished:
            self.run.data["pipeline"]["stages"][self.name].update(details)

    def mark_success(self, success: bool) -> None:
        self._success_override = bool(success)
        if self._finished:
            self.run.data["pipeline"]["stages"][self.name]["success"] = bool(success)

    def __enter__(self) -> "PerformanceStage":
        logger.info("[PERF] %s started run_id=%s", self.name, self.run.run_id)
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        duration = max(0.0, self.run._clock() - self._started)
        success = exc is None if self._success_override is None else self._success_override
        payload = {
            "started_at": self.started_at,
            "duration_seconds": round(duration, 6),
            "success": success,
            **self.details,
        }
        if exc is not None:
            payload["error_type"] = _safe_error_type(exc)
        self.run._set_stage(self.name, payload)
        self._finished = True
        if success:
            suffix = " ".join(f"{key}={value}" for key, value in self.details.items())
            logger.info(
                "[PERF] %s completed duration=%.2fs%s",
                self.name,
                duration,
                f" {suffix}" if suffix else "",
            )
        else:
            logger.warning(
                "[PERF] %s failed duration=%.2fs error_type=%s",
                self.name,
                duration,
                _safe_error_type(exc) or "StageReportedFailure",
            )
        return False


class _NoOpStage:
    """Fallback stage used when instrumentation itself cannot start."""

    def update(self, **details: Any) -> None:
        return None

    def mark_success(self, success: bool) -> None:
        return None

    def __enter__(self) -> "_NoOpStage":
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False


class PerformanceRun:
    """In-memory metrics for one real subtitle-generation pipeline."""

    def __init__(
        self,
        *,
        video_id: str | None = None,
        video_name: str | None = None,
        report_dir: Path | None = None,
        clock=time.perf_counter,
        now=_utc_now,
    ) -> None:
        self._clock = clock
        self._now = now
        self.report_dir = Path(report_dir or PERFORMANCE_DIR)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        self.run_id = f"{timestamp}_{uuid.uuid4().hex[:8]}"
        self._pipeline_started = self._clock()
        self._lock = threading.RLock()
        self.data: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "created_at": self._now(),
            "video": {
                "video_id": video_id,
                "filename": video_name,
                "video_name": video_name,
                "file_size_bytes": None,
                "file_size_mb": None,
                "video_duration_seconds": None,
                "duration_seconds": None,
                "duration_hms": None,
                "width": None,
                "height": None,
                "resolution": None,
                "fps": None,
                "codec": None,
                "metadata_collection_status": None,
                "metadata_collection_error_type": None,
                "source_language": None,
                "target_language": None,
            },
            "pipeline": {"success": None, "total_duration_seconds": None, "stages": {}},
            "timeline_validation": None,
            "summary_runs": [],
            "qa_runs": [],
            "player_seek_validation": {
                "automated": False,
                "status": "manual_test_required",
            },
        }
        logger.info("[PERF] run started id=%s", self.run_id)

    def stage(self, name: str, **details: Any) -> PerformanceStage | _NoOpStage:
        try:
            return PerformanceStage(self, name, details)
        except Exception as exc:
            logger.warning(
                "[PERF] %s instrumentation unavailable error_type=%s",
                name,
                type(exc).__name__,
            )
            return _NoOpStage()

    def _set_stage(self, name: str, payload: Mapping[str, Any]) -> None:
        with self._lock:
            existing = dict(self.data["pipeline"]["stages"].get(name, {}))
            existing.update(payload)
            self.data["pipeline"]["stages"][name] = existing

    def set_stage_details(self, name: str, **details: Any) -> None:
        """Attach best-effort counters while a surrounding stage is running."""
        try:
            with self._lock:
                stage = self.data["pipeline"]["stages"].setdefault(name, {})
                stage.update(details)
        except Exception as exc:
            logger.warning(
                "[PERF] stage details failed error_type=%s", type(exc).__name__
            )

    def increment_stage(self, name: str, counter: str, amount: int = 1) -> None:
        try:
            with self._lock:
                stage = self.data["pipeline"]["stages"].setdefault(name, {})
                stage[counter] = int(stage.get(counter, 0)) + int(amount)
        except Exception as exc:
            logger.warning(
                "[PERF] stage counter failed error_type=%s", type(exc).__name__
            )

    def skip_stage(self, name: str, reason: str, **details: Any) -> None:
        self._set_stage(name, {
            "started_at": self._now(),
            "duration_seconds": None,
            "success": True,
            "skipped": True,
            "skip_reason": reason,
            **details,
        })
        logger.info("[PERF] %s skipped reason=%s", name, reason)

    def set_video(self, **metadata: Any) -> None:
        try:
            allowed = set(self.data["video"])
            with self._lock:
                for key, value in metadata.items():
                    if key in allowed:
                        self.data["video"][key] = value
                if "video_duration_seconds" in metadata:
                    self.data["video"]["duration_seconds"] = metadata.get(
                        "video_duration_seconds"
                    )
                elif "duration_seconds" in metadata:
                    self.data["video"]["video_duration_seconds"] = metadata.get(
                        "duration_seconds"
                    )
                size = self.data["video"].get("file_size_bytes")
                if isinstance(size, int) and size >= 0:
                    self.data["video"]["file_size_mb"] = round(
                        size / (1024 * 1024), 3
                    )
                duration = self.data["video"].get("video_duration_seconds")
                self.data["video"]["duration_hms"] = _duration_hms(duration)
        except Exception as exc:
            logger.warning(
                "[PERF] video metadata failed error_type=%s", type(exc).__name__
            )

    def set_timeline(self, cues: Iterable[Mapping[str, Any]]) -> None:
        try:
            validation = validate_timeline(
                cues, self.data["video"].get("video_duration_seconds")
            )
            with self._lock:
                self.data["timeline_validation"] = validation
        except Exception as exc:
            logger.warning(
                "[PERF] timeline validation failed error_type=%s",
                type(exc).__name__,
            )

    def finish_pipeline(self, success: bool, error: BaseException | None = None) -> None:
        try:
            duration = max(0.0, self._clock() - self._pipeline_started)
            with self._lock:
                self.data["pipeline"]["success"] = bool(success)
                self.data["pipeline"]["total_duration_seconds"] = round(
                    duration, 6
                )
                if error is not None:
                    self.data["pipeline"]["error_type"] = _safe_error_type(error)
            logger.info(
                "[PERF] pipeline %s duration=%.2fs run_id=%s",
                "completed" if success else "failed",
                duration,
                self.run_id,
            )
        except Exception as exc:
            logger.warning(
                "[PERF] pipeline finish failed error_type=%s", type(exc).__name__
            )

    def save_report(self) -> Path | None:
        """Atomically save without ever raising into business code."""
        try:
            self.report_dir.mkdir(parents=True, exist_ok=True)
            content = json.dumps(self.data, ensure_ascii=False, indent=2)
            destination = self.report_dir / f"{self.run_id}.json"
            _atomic_write(destination, content)
            _atomic_write(self.report_dir / "latest.json", content)
            logger.info("[PERF] report saved path=%s", destination)
            return destination
        except Exception as exc:  # metrics are deliberately best-effort
            logger.warning("[PERF] report save failed error_type=%s", type(exc).__name__)
            return None


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def validate_timeline(
    cues: Iterable[Mapping[str, Any]], video_duration: float | None = None
) -> dict[str, Any]:
    """O(n) structural timeline validation without decoding media."""
    items = list(cues)
    seen: set[str] = set()
    duplicate_ids = ordering_errors = invalid_ranges = overlap_count = gap_count = 0
    first_start: float | None = None
    last_end: float | None = None
    previous_start: float | None = None
    previous_end: float | None = None
    for index, cue in enumerate(items):
        cue_id = str(cue.get("id", index))
        if cue_id in seen:
            duplicate_ids += 1
        seen.add(cue_id)
        try:
            start, end = float(cue["start"]), float(cue["end"])
            finite = math.isfinite(start) and math.isfinite(end)
        except (KeyError, TypeError, ValueError):
            finite = False
            start = end = math.nan
        if not finite or start < 0 or end <= start:
            invalid_ranges += 1
            continue
        if first_start is None:
            first_start = start
        last_end = end
        if previous_start is not None and start < previous_start:
            ordering_errors += 1
        if previous_end is not None:
            if start < previous_end:
                overlap_count += 1
            elif start > previous_end:
                gap_count += 1
        previous_start, previous_end = start, end
    duration = None
    if video_duration is not None:
        try:
            candidate = float(video_duration)
            duration = candidate if math.isfinite(candidate) and candidate > 0 else None
        except (TypeError, ValueError):
            duration = None
    coverage_seconds = (
        last_end - first_start
        if first_start is not None and last_end is not None
        else None
    )
    coverage_ratio = (
        round(coverage_seconds / duration, 6)
        if coverage_seconds is not None and duration is not None
        else None
    )
    return {
        "cue_count": len(items),
        "duplicate_ids": duplicate_ids,
        "ordering_errors": ordering_errors,
        "invalid_ranges": invalid_ranges,
        "overlap_count": overlap_count,
        "timeline_gap_count": gap_count,
        "first_start": first_start,
        "last_end": last_end,
        "video_duration": duration,
        "timeline_coverage_seconds": coverage_seconds,
        "coverage_ratio": coverage_ratio,
        "passed": not (duplicate_ids or ordering_errors or invalid_ranges or overlap_count),
    }


def map_correction_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Map existing correction diagnostics without re-computing them."""
    return {
        "total_segments": metadata.get("total_segments"),
        "changed_segments": metadata.get("changed_segments"),
        "batch_count": metadata.get("batches"),
        "retry_batches": metadata.get("retry_batches"),
        "retry_successes": metadata.get("retry_successes"),
        "failed_batches": metadata.get("failed_batches"),
        "fallback": metadata.get("fallback"),
    }


def activate_run(run: PerformanceRun):
    return _active_run.set(run)


def create_run(**kwargs: Any) -> PerformanceRun | None:
    """Create a run without allowing observation setup to block a request."""
    try:
        return PerformanceRun(**kwargs)
    except Exception as exc:
        logger.warning("[PERF] run creation failed error_type=%s", type(exc).__name__)
        return None


def reset_active_run(token) -> None:
    _active_run.reset(token)


def get_active_run() -> PerformanceRun | None:
    return _active_run.get()


def _report_candidates(report_dir: Path) -> Iterator[Path]:
    if not report_dir.is_dir():
        return iter(())
    return iter(sorted(
        (path for path in report_dir.glob("*.json") if path.name != "latest.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ))


def find_latest_report(video_id: str, report_dir: Path | None = None) -> Path | None:
    directory = Path(report_dir or PERFORMANCE_DIR)
    try:
        for path in _report_candidates(directory):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("video", {}).get("video_id") == video_id:
                return path
    except Exception as exc:
        logger.warning("[PERF] report lookup failed error_type=%s", type(exc).__name__)
    return None


@contextmanager
def observe_operation(
    kind: str, video_id: str, *, report_dir: Path | None = None
) -> Iterator[dict[str, Any]]:
    """Append Summary/Q&A timings to the latest run; never mask business errors."""
    started_at = _utc_now()
    started = time.perf_counter()
    details: dict[str, Any] = {}
    error: BaseException | None = None
    try:
        yield details
    except BaseException as exc:
        error = exc
        raise
    finally:
        duration = max(0.0, time.perf_counter() - started)
        entry = {
            "started_at": started_at,
            "duration_seconds": round(duration, 6),
            "success": error is None,
            **details,
        }
        if error is not None:
            entry["error_type"] = _safe_error_type(error)
        _append_operation(video_id, kind, entry, Path(report_dir or PERFORMANCE_DIR))
        logger.info(
            "[PERF] %s %s video_id=%s duration=%.2fs%s",
            kind,
            "completed" if error is None else "failed",
            video_id,
            duration,
            (
                f" timestamp_count={details.get('timestamp_count')}"
                if kind == "qa" and "timestamp_count" in details
                else ""
            ),
        )


def _append_operation(video_id: str, kind: str, entry: Mapping[str, Any], report_dir: Path) -> None:
    try:
        with _report_lock:
            path = find_latest_report(video_id, report_dir)
            if path is None:
                return
            payload = json.loads(path.read_text(encoding="utf-8"))
            key = "summary_runs" if kind == "summary" else "qa_runs"
            runs = payload.setdefault(key, [])
            record = dict(entry)
            if kind == "qa":
                record["question_index"] = len(runs) + 1
            runs.append(record)
            content = json.dumps(payload, ensure_ascii=False, indent=2)
            _atomic_write(path, content)
            _atomic_write(report_dir / "latest.json", content)
    except Exception as exc:
        logger.warning("[PERF] %s record failed error_type=%s", kind, type(exc).__name__)
