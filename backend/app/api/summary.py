"""API for AI-generated video summaries."""

import asyncio
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.config.languages import require_supported_language
from app.agents.video_summary_agent import (
    SummaryAgentConfigurationError,
    SummaryAgentError,
    VideoSummaryAgent,
)
from app.api.subtitle import get_subtitle


router = APIRouter(tags=["summary"])


class SummaryRequest(BaseModel):
    """Options for summary generation."""

    output_language: str = "zh"

    @field_validator("output_language")
    @classmethod
    def validate_output_language(cls, value: str) -> str:
        return require_supported_language(value, "summary")


class SummaryChapter(BaseModel):
    """One timestamped topic in the video."""

    start: float = Field(ge=0)
    end: float = Field(ge=0)
    timestamp: str
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_timeline(self) -> "SummaryChapter":
        if self.end < self.start:
            raise ValueError("Chapter end must not precede chapter start.")
        return self

    @model_validator(mode="before")
    @classmethod
    def normalize_timestamps(cls, data: object) -> object:
        """Accept legacy timestamp-only chapters while exposing numeric seconds."""
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        if "start" not in normalized and normalized.get("timestamp"):
            normalized["start"] = _parse_timestamp(normalized["timestamp"])
        if "end" not in normalized and "start" in normalized:
            normalized["end"] = normalized["start"]
        if "timestamp" not in normalized and "start" in normalized:
            normalized["timestamp"] = _format_timestamp(normalized["start"])
        return normalized


def _parse_timestamp(value: object) -> float:
    parts = str(value).strip().split(":")
    if not 1 <= len(parts) <= 3:
        raise ValueError("Chapter timestamp must use SS, MM:SS, or HH:MM:SS format.")
    try:
        numbers = [float(part) for part in parts]
    except ValueError as exc:
        raise ValueError("Chapter timestamp contains a non-numeric value.") from exc
    if any(number < 0 for number in numbers):
        raise ValueError("Chapter timestamp must not be negative.")
    seconds = 0.0
    for number in numbers:
        seconds = seconds * 60 + number
    return seconds


def _format_timestamp(value: object) -> str:
    total_seconds = max(0, int(float(value)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class VideoSummary(BaseModel):
    """Structured summary generated from a video subtitle track."""

    video_id: str
    title: str = Field(min_length=1)
    overview: str = Field(min_length=1)
    key_points: list[str] = Field(min_length=1)
    chapters: list[SummaryChapter]
    keywords: list[str]


def _get_summary_agent() -> VideoSummaryAgent:
    return VideoSummaryAgent()


@router.post("/summary/{video_id}", response_model=VideoSummary)
async def generate_video_summary(
    video_id: str,
    request: SummaryRequest,
) -> VideoSummary:
    """Create a structured AI summary from a generated subtitle track."""
    subtitle_payload = await get_subtitle(video_id)
    try:
        result = await asyncio.to_thread(
            _get_summary_agent().summarize,
            subtitle_payload["subtitles"],
            request.output_language,
        )
        return VideoSummary(video_id=video_id, **result)
    except SummaryAgentConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except SummaryAgentError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"DeepSeek returned an invalid summary structure: {exc}",
        ) from exc
