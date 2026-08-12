"""Service for translating Whisper segments and generating bilingual SRT files."""

import json
import logging
from os import PathLike
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.config.transcript_correction import transcript_correction_enabled
from app.services import translation_service
from app.services.transcript_correction_service import correct_transcript_with_fallback
from app.services.transcript_correction_service import TranscriptCorrectionResult
from app.services.subtitle_service import _format_srt_timestamp


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
) -> Path:
    """Correct Whisper text, translate it, and write SRT plus structured JSON."""
    source_segments = list(segments)
    pipeline_logger.info("[Pipeline] entering transcript correction")
    pipeline_logger.info("[Pipeline] raw segments=%d", len(source_segments))
    pipeline_logger.info(
        "[Pipeline] correction enabled=%s",
        str(transcript_correction_enabled()).lower(),
    )
    correction_result = correct_transcript_with_fallback(
        source_segments, source_language
    )
    if isinstance(correction_result, TranscriptCorrectionResult):
        corrected_segments = correction_result.segments
        correction_metadata = correction_result.metadata
    else:
        # Preserve compatibility with existing provider/test doubles.
        corrected_segments = correction_result
        correction_metadata = {
            "enabled": True,
            "attempted": True,
            "success": True,
            "fallback": False,
            "changed_segments": sum(
                item["raw_text"] != item["corrected_text"]
                for item in corrected_segments
            ),
            "total_segments": len(corrected_segments),
            "batches": 1 if corrected_segments else 0,
            "failed_batches": 0,
            "zero_change_warning": False,
            "error": None,
        }
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
    translated_segments = translation_service.translate_segments(
        translation_input,
        source_language=source_language,
        target_language=target_language,
    )
    destination = generate_bilingual_srt(
        translation_input,
        translated_segments,
        output_path,
        monolingual=source_language == target_language,
    )
    _write_structured_subtitles(
        destination,
        corrected_segments,
        translated_segments,
        source_language,
        target_language,
        correction_metadata,
    )
    return destination


def _write_structured_subtitles(
    srt_path: Path,
    corrected_segments: list[Mapping[str, Any]],
    translated_segments: list[Mapping[str, Any]],
    source_language: str,
    target_language: str,
    correction_metadata: Mapping[str, Any],
) -> Path:
    """Persist raw/corrected/translated text without encoding it into SRT metadata."""
    translated_by_id = {item["id"]: str(item["text"]) for item in translated_segments}
    structured = {
        "source_language": source_language,
        "target_language": target_language,
        "correction": dict(correction_metadata),
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
