"""Development-only endpoint for diagnosing the real DeepSeek ASR corrector."""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config.languages import require_supported_language
from app.services.transcript_correction_service import (
    TranscriptCorrectionError,
    correct_transcript_with_metadata,
)


router = APIRouter(prefix="/debug", tags=["debug"])


class DebugCorrectionSegment(BaseModel):
    """One text-only segment supplied to the correction diagnostic."""

    model_config = ConfigDict(extra="forbid")

    id: int | str
    text: str = Field(min_length=1)


class DebugCorrectionRequest(BaseModel):
    """A small ASR fixture for calling the configured real provider."""

    model_config = ConfigDict(extra="forbid")

    segments: list[DebugCorrectionSegment] = Field(min_length=1, max_length=100)
    language: str

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        return require_supported_language(value, "source")


@router.post("/transcript-correction")
async def debug_transcript_correction(
    request: DebugCorrectionRequest,
) -> dict[str, Any]:
    """Run the actual configured corrector without writing subtitle files."""
    source = [
        {"id": item.id, "start": 0.0, "end": 0.0, "text": item.text}
        for item in request.segments
    ]
    try:
        result = await asyncio.to_thread(
            correct_transcript_with_metadata, source, request.language
        )
    except (TranscriptCorrectionError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return {
        "raw": [
            {"id": item["id"], "text": item["raw_text"]}
            for item in result.segments
        ],
        "corrected": [
            {"id": item["id"], "corrected_text": item["corrected_text"]}
            for item in result.segments
        ],
        **result.metadata,
    }
