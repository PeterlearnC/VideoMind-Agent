"""Service for generating SubRip (SRT) subtitle files."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from os import PathLike
from pathlib import Path
from typing import Any, Iterable, Mapping


def _format_srt_timestamp(seconds: Any) -> str:
    """Convert seconds to an SRT timestamp with millisecond precision."""
    try:
        value = Decimal(str(seconds))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid subtitle timestamp: {seconds!r}") from exc

    if not value.is_finite() or value < 0:
        raise ValueError(f"Invalid subtitle timestamp: {seconds!r}")

    total_milliseconds = int(
        (value * 1000).to_integral_value(rounding=ROUND_HALF_UP)
    )
    total_seconds, milliseconds = divmod(total_milliseconds, 1000)
    total_minutes, second = divmod(total_seconds, 60)
    hour, minute = divmod(total_minutes, 60)

    return f"{hour:02d}:{minute:02d}:{second:02d},{milliseconds:03d}"


def generate_srt(
    segments: Iterable[Mapping[str, Any]],
    output_path: str | PathLike[str],
) -> Path:
    """Generate a UTF-8 SRT file from Whisper transcription segments."""
    subtitle_blocks: list[str] = []

    for index, segment in enumerate(segments, start=1):
        start = _format_srt_timestamp(segment["start"])
        end = _format_srt_timestamp(segment["end"])
        text = str(segment["text"]).strip()
        subtitle_blocks.append(f"{index}\n{start} --> {end}\n{text}")

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = "\n\n".join(subtitle_blocks)
    if content:
        content += "\n"
    destination.write_text(content, encoding="utf-8", newline="\n")

    return destination
