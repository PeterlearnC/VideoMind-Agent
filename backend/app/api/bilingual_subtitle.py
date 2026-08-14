"""API for generating translated bilingual subtitles from a video."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.config.languages import (
    default_target_language,
    require_supported_language,
)
from app.api.video import PROJECT_ROOT, SUBTITLE_DIR, transcribe_video
from app.services.bilingual_subtitle_service import generate_bilingual_subtitle
from app.services.translation_service import (
    TranslationConfigurationError,
    TranslationError,
)
from app.services.performance_metrics import (
    activate_run,
    create_run,
    reset_active_run,
)
from app.config.competition_demo import require_cloud_ai_available


router = APIRouter(tags=["subtitle"])

BILINGUAL_SUBTITLE_PATH = SUBTITLE_DIR / "bilingual.srt"
@router.post("/generate-bilingual-subtitle")
async def generate_bilingual_subtitle_api(
    file: UploadFile = File(...),
    target_language: Annotated[str | None, Form()] = None,
) -> dict[str, str]:
    """Detect, transcribe, translate, and create a bilingual SRT."""
    require_cloud_ai_available()
    metrics = create_run(
        video_id="bilingual",
        video_name=getattr(file, "filename", None),
    )
    token = activate_run(metrics) if metrics else None
    pipeline_error: BaseException | None = None
    try:
        return await _run_bilingual_pipeline(file, target_language, metrics)
    except BaseException as exc:
        pipeline_error = exc
        raise
    finally:
        if metrics:
            metrics.finish_pipeline(pipeline_error is None, pipeline_error)
            metrics.save_report()
        if token is not None:
            reset_active_run(token)


async def _run_bilingual_pipeline(
    file: UploadFile,
    target_language: str | None,
    metrics,
) -> dict[str, str]:
    transcription = await transcribe_video(file)
    try:
        source_language = require_supported_language(
            transcription["language"], "source"
        )
        resolved_target = require_supported_language(
            target_language or default_target_language(source_language), "target"
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if metrics:
        metrics.set_video(
            video_id="bilingual",
            video_name=transcription["filename"],
            source_language=source_language,
            target_language=resolved_target,
        )
    try:
        subtitle_path = await asyncio.to_thread(
            generate_bilingual_subtitle,
            transcription["segments"],
            source_language,
            BILINGUAL_SUBTITLE_PATH,
            resolved_target,
            transcription["filename"],
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
        "language": source_language,
        "source_language": source_language,
        "target_language": resolved_target,
        "subtitle_file": subtitle_path.relative_to(PROJECT_ROOT).as_posix(),
    }
