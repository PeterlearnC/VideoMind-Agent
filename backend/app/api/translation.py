"""Video subtitle translation API."""

import asyncio

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.services.translation_service import (
    TranslationConfigurationError,
    TranslationError,
    translate_segments,
)
from app.config.languages import require_supported_language
from app.config.competition_demo import require_cloud_ai_available


router = APIRouter(tags=["translation"])

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
    source_language: str = Query(default="en"),
    target_language: str = Query(default="zh"),
) -> list[TranslatedSegment]:
    """Translate Whisper segments while preserving their original timeline."""
    require_cloud_ai_available()
    source_segments = [segment.model_dump() for segment in segments]
    try:
        source_language = require_supported_language(source_language, "source")
        target_language = require_supported_language(target_language, "target")
        translated_segments = await asyncio.to_thread(
            translate_segments,
            source_segments,
            source_language,
            target_language,
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
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except (KeyError, OSError, TypeError) as exc:
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
