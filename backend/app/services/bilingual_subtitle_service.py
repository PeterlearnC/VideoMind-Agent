"""Service for translating Whisper segments and generating bilingual SRT files."""

from os import PathLike
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.services import translation_service
from app.services.subtitle_service import _format_srt_timestamp


DEFAULT_OUTPUT_PATH = Path("bilingual.srt")


def generate_bilingual_srt(
    source_segments: Iterable[Mapping[str, Any]],
    translated_segments: Iterable[Mapping[str, Any]],
    output_path: str | PathLike[str],
) -> Path:
    """Generate a UTF-8 SRT containing source and translated subtitle lines."""
    source_items = list(source_segments)
    translated_items = list(translated_segments)
    if len(source_items) != len(translated_items):
        raise ValueError("Source and translated segment counts do not match.")

    subtitle_blocks: list[str] = []
    for index, (source, translated) in enumerate(
        zip(source_items, translated_items),
        start=1,
    ):
        start = _format_srt_timestamp(source["start"])
        end = _format_srt_timestamp(source["end"])
        source_text = str(source["text"]).strip()
        translated_text = str(translated["text"]).strip()
        subtitle_blocks.append(
            f"{index}\n{start} --> {end}\n{source_text}\n{translated_text}"
        )

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
    """Translate Whisper segments via translation_service and write bilingual SRT."""
    source_segments = list(segments)
    translated_segments = translation_service.translate_segments(
        source_segments,
        source_language=source_language,
        target_language=target_language,
    )
    return generate_bilingual_srt(
        source_segments,
        translated_segments,
        output_path,
    )