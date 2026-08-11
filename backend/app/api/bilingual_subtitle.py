"""API for generating Chinese-English subtitles from an English video."""

import asyncio

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.video import PROJECT_ROOT, SUBTITLE_DIR, transcribe_video
from app.services.bilingual_subtitle_service import generate_bilingual_subtitle
from app.services.translation_service import (
    TranslationConfigurationError,
    TranslationError,
)


router = APIRouter(tags=["subtitle"])

BILINGUAL_SUBTITLE_PATH = SUBTITLE_DIR / "bilingual.srt"
TARGET_LANGUAGE = "zh"


def _is_english(language: str) -> bool:
    normalized = language.strip().lower().replace("_", "-")
    return normalized == "english" or normalized.split("-", 1)[0] == "en"


@router.post("/generate-bilingual-subtitle")
async def generate_bilingual_subtitle_api(
    file: UploadFile = File(...),
) -> dict[str, str]:
    """Transcribe an English video, translate it, and create bilingual.srt."""
    transcription = await transcribe_video(file)
    language = str(transcription["language"])
    if not _is_english(language):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Bilingual subtitle generation currently requires an English "
                f"video; Whisper detected {language!r}."
            ),
        )

    try:
        subtitle_path = await asyncio.to_thread(
            generate_bilingual_subtitle,
            transcription["segments"],
            language,
            BILINGUAL_SUBTITLE_PATH,
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
            detail=f"Failed to generate bilingual subtitles: {exc}",
        ) from exc

    return {
        "filename": transcription["filename"],
        "language": language,
        "subtitle_file": subtitle_path.relative_to(PROJECT_ROOT).as_posix(),
    }