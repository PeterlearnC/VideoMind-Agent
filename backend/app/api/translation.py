"""Video subtitle translation API."""

import asyncio

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.translation_service import (
    TranslationConfigurationError,
    TranslationError,
    translate_segments,
)


router = APIRouter(tags=["translation"])

TARGET_LANGUAGE = "zh"


class WhisperSegment(BaseModel):
    """Whisper segment accepted by the translation endpoint."""

    text: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)


class TranslatedSegment(BaseModel):
    """Original and translated subtitle text with preserved timestamps."""

    original: str
    translation: str
    start: float
    end: float


@router.post("/translate-subtitle", response_model=list[TranslatedSegment])
async def translate_subtitle(
    segments: list[WhisperSegment],
) -> list[TranslatedSegment]:
    """Translate English Whisper segments into timestamp-aligned Chinese text."""
    source_segments = [segment.model_dump() for segment in segments]
    try:
        translated_segments = await asyncio.to_thread(
            translate_segments,
            source_segments,
            "en",
            TARGET_LANGUAGE,
        )
    except TranslationConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except TranslationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate translated subtitles: {exc}",
        ) from exc

    return [
        TranslatedSegment(
            original=source["text"],
            translation=translated["text"],
            start=source["start"],
            end=source["end"],
        )
        for source, translated in zip(source_segments, translated_segments)
    ]
