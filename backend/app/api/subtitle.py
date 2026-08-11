"""API for reading generated subtitle tracks as JSON."""

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.api.video import SUBTITLE_DIR


router = APIRouter(tags=["subtitle"])

VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
TIMESTAMP_PATTERN = re.compile(
    r"^(?P<hours>\d{2,}):(?P<minutes>\d{2}):(?P<seconds>\d{2})"
    r"[,.](?P<milliseconds>\d{3})$"
)


def _timestamp_to_seconds(timestamp: str) -> float:
    match = TIMESTAMP_PATTERN.fullmatch(timestamp.strip())
    if match is None:
        raise ValueError(f"Invalid SRT timestamp: {timestamp!r}")
    parts = {key: int(value) for key, value in match.groupdict().items()}
    return (
        parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
        + parts["milliseconds"] / 1000
    )


def parse_srt(content: str) -> list[dict[str, object]]:
    """Parse mono- or bilingual SRT content into frontend-friendly cues."""
    cues: list[dict[str, object]] = []
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return cues

    for block in re.split(r"\n{2,}", normalized):
        lines = [line.strip() for line in block.splitlines()]
        if len(lines) < 3 or "-->" not in lines[1]:
            raise ValueError("Invalid SRT cue structure.")
        start_text, end_text = (part.strip() for part in lines[1].split("-->", 1))
        text_lines = [line for line in lines[2:] if line]
        cues.append(
            {
                "id": lines[0],
                "start": _timestamp_to_seconds(start_text),
                "end": _timestamp_to_seconds(end_text),
                "source": text_lines[0] if text_lines else "",
                "translation": "\n".join(text_lines[1:]),
            }
        )
    return cues


@router.get("/subtitle/{video_id}")
async def get_subtitle(video_id: str) -> dict[str, object]:
    """Return a generated subtitle track as timestamped JSON cues."""
    if VIDEO_ID_PATTERN.fullmatch(video_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid video_id. Use letters, numbers, underscores, or hyphens.",
        )

    subtitle_path = SUBTITLE_DIR / f"{video_id}.srt"
    if not subtitle_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subtitle track {video_id!r} was not found.",
        )

    try:
        subtitles = parse_srt(subtitle_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read subtitle track: {exc}",
        ) from exc

    return {"video_id": video_id, "subtitles": subtitles}
