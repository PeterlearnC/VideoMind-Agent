"""Service for translating Whisper segments and generating bilingual SRT files."""

import json
import logging
import math
from os import PathLike
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.config.transcript_correction import transcript_correction_enabled
from app.services import translation_service
from app.services.transcript_correction_service import correct_transcript_with_fallback
from app.services.transcript_correction_service import TranscriptCorrectionResult
from app.services.subtitle_service import _format_srt_timestamp
from app.services.performance_metrics import get_active_run, map_correction_metadata
from app.config.translation import translation_batch_size


DEFAULT_OUTPUT_PATH = Path("bilingual.srt")
pipeline_logger = logging.getLogger("uvicorn.error.pipeline")
pipeline_logger.setLevel(logging.INFO)


def generate_bilingual_srt(
    source_segments: Iterable[Mapping[str, Any]],
    translated_segments: Iterable[Mapping[str, Any]],
    output_path: str | PathLike[str],
    monolingual: bool = False,
) -> Path:
    """Generate a UTF-8 SRT containing one or two subtitle lines per cue."""
    source_items = list(source_segments)
    translated_items = list(translated_segments)
    if len(source_items) != len(translated_items):
        raise ValueError("Source and translated segment counts do not match.")

    subtitle_blocks: list[str] = []
    for index, (source, translated) in enumerate(
        zip(source_items, translated_items),
        start=1,
    ):
        source_id = source.get("id", index - 1)
        if translated.get("id", index - 1) != source_id:
            raise ValueError("Source and translated segment ids do not match.")
        start = _format_srt_timestamp(source["start"])
        end = _format_srt_timestamp(source["end"])
        source_text = str(source["text"]).strip()
        translated_text = str(translated["text"]).strip()
        cue_text = source_text if monolingual else f"{source_text}\n{translated_text}"
        subtitle_blocks.append(f"{index}\n{start} --> {end}\n{cue_text}")

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = "\n\n".join(subtitle_blocks)
    if content:
        content += "\n"
    destination.write_text(content, encoding="utf-8", newline="\n")
    return destination


def generate_bilingual_subtitle(
    segments: Iterable[Mapping[str, Any]],
    source_language: str,
    output_path: str | PathLike[str] = DEFAULT_OUTPUT_PATH,
    target_language: str = "zh",
    video_name: str | None = None,
) -> Path:
    """Correct Whisper text, translate it, and write SRT plus structured JSON."""
    source_segments = list(segments)
    metrics = get_active_run()
    pipeline_logger.info("[Pipeline] entering transcript correction")
    pipeline_logger.info("[Pipeline] raw segments=%d", len(source_segments))
    pipeline_logger.info(
        "[Pipeline] correction enabled=%s",
        str(transcript_correction_enabled()).lower(),
    )
    def run_correction() -> tuple[list[Mapping[str, Any]], Mapping[str, Any]]:
        correction_result = correct_transcript_with_fallback(
            source_segments, source_language
        )
        if isinstance(correction_result, TranscriptCorrectionResult):
            return correction_result.segments, correction_result.metadata
        corrected = correction_result
        # Preserve compatibility with existing provider/test doubles.
        return corrected, {
            "enabled": True,
            "attempted": True,
            "success": True,
            "fallback": False,
            "changed_segments": sum(
                item["raw_text"] != item["corrected_text"] for item in corrected
            ),
            "total_segments": len(corrected),
            "batches": 1 if corrected else 0,
            "failed_batches": 0,
            "retry_batches": 0,
            "retry_successes": 0,
            "zero_change_warning": False,
            "error": None,
        }

    if metrics:
        with metrics.stage("transcript_correction") as correction_stage:
            corrected_segments, correction_metadata = run_correction()
            correction_stage.update(**map_correction_metadata(correction_metadata))
            correction_stage.mark_success(
                bool(correction_metadata.get("success", True))
            )
    else:
        corrected_segments, correction_metadata = run_correction()
    pipeline_logger.info("[Pipeline] transcript correction finished")
    pipeline_logger.info(
        "[Pipeline] changed_segments=%d",
        correction_metadata["changed_segments"],
    )
    pipeline_logger.info(
        "[Pipeline] fallback=%s",
        str(correction_metadata["fallback"]).lower(),
    )
    translation_input = [
        {
            "id": segment["id"],
            "start": segment["start"],
            "end": segment["end"],
            "text": segment["corrected_text"],
        }
        for segment in corrected_segments
    ]
    translation_details = {
        "total_cues": len(translation_input),
        "batch_count": (
            math.ceil(
                sum(bool(str(item["text"]).strip()) for item in translation_input)
                / translation_batch_size()
            )
            if translation_input else 0
        ),
        "source_language": source_language,
        "target_language": target_language,
    }
    if source_language == target_language:
        if metrics:
            metrics.skip_stage(
                "translation", "same_language", **translation_details
            )
        translated_segments = translation_service.translate_segments(
            translation_input,
            source_language=source_language,
            target_language=target_language,
        )
    elif metrics:
        with metrics.stage("translation", **translation_details):
            translated_segments = translation_service.translate_segments(
                translation_input,
                source_language=source_language,
                target_language=target_language,
            )
    else:
        translated_segments = translation_service.translate_segments(
            translation_input,
            source_language=source_language,
            target_language=target_language,
        )
    if metrics:
        with metrics.stage("subtitle_generation") as subtitle_stage:
            destination = generate_bilingual_srt(
                translation_input, translated_segments, output_path,
                monolingual=source_language == target_language,
            )
            _write_structured_subtitles(
                destination, corrected_segments, translated_segments,
                source_language, target_language, correction_metadata, video_name,
            )
            metrics.set_timeline(translation_input)
            timeline = metrics.data.get("timeline_validation") or {}
            subtitle_stage.update(
                cue_count=len(translation_input),
                first_cue_start=timeline.get("first_start"),
                last_cue_end=timeline.get("last_end"),
                timeline_coverage_seconds=timeline.get(
                    "timeline_coverage_seconds"
                ),
            )
    else:
        destination = generate_bilingual_srt(
            translation_input, translated_segments, output_path,
            monolingual=source_language == target_language,
        )
        _write_structured_subtitles(
            destination, corrected_segments, translated_segments,
            source_language, target_language, correction_metadata, video_name,
        )
    return destination


def _write_structured_subtitles(
    srt_path: Path,
    corrected_segments: list[Mapping[str, Any]],
    translated_segments: list[Mapping[str, Any]],
    source_language: str,
    target_language: str,
    correction_metadata: Mapping[str, Any],
    video_name: str | None = None,
) -> Path:
    """Persist raw/corrected/translated text without encoding it into SRT metadata."""
    translated_items_by_id = {item["id"]: item for item in translated_segments}
    translated_by_id = {
        item_id: str(item["text"])
        for item_id, item in translated_items_by_id.items()
    }
    structured = {
        "source_language": source_language,
        "target_language": target_language,
        "correction": dict(correction_metadata),
        "metadata": {
            "correction": dict(correction_metadata),
            "workspace": {
                "video_name": video_name,
                "source_language": source_language,
                "target_language": target_language,
            },
            "editor": {
                "edited_cues": 0,
                "last_modified": None,
                "version": 1,
            },
        },
        "subtitles": [
            {
                "id": item["id"],
                "start": item["start"],
                "end": item["end"],
                "raw_text": item["raw_text"],
                "corrected_text": item["corrected_text"],
                "translations": {
                    target_language: translated_by_id[item["id"]]
                },
                "translated_text": translated_by_id[item["id"]],
                "translation_validation_warning": bool(
                    translated_items_by_id[item["id"]].get("validation_warning")
                ),
                "translation_validation_warning_reason": (
                    translated_items_by_id[item["id"]].get(
                        "validation_warning_reason"
                    )
                ),
                "edited_source_text": None,
                "edited_translated_text": None,
                "source": item["corrected_text"],
                "translation": (
                    ""
                    if source_language == target_language
                    else translated_by_id[item["id"]]
                ),
                "source_text": item["corrected_text"],
            }
            for item in corrected_segments
        ],
    }
    destination = srt_path.with_suffix(".json")
    destination.write_text(
        json.dumps(structured, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return destination
