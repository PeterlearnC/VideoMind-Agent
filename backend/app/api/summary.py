"""API for AI-generated video summaries."""

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.agents.video_summary_agent import (
    SummaryAgentConfigurationError,
    SummaryAgentError,
    VideoSummaryAgent,
)
from app.api.subtitle import get_subtitle


router = APIRouter(tags=["summary"])


class SummaryRequest(BaseModel):
    """Options for summary generation."""

    output_language: Literal["zh", "en"] = "zh"


class SummaryChapter(BaseModel):
    """One timestamped topic in the video."""

    start: float = Field(ge=0)
    end: float = Field(ge=0)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_timeline(self) -> "SummaryChapter":
        if self.end < self.start:
            raise ValueError("Chapter end must not precede chapter start.")
        return self


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

