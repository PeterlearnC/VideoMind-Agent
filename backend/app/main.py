"""VideoMind-Agent FastAPI application entry point."""

from app.config.environment import load_backend_env


# Load backend/.env before importing routers whose services read configuration.
# Explicit process environment variables always take precedence.
load_backend_env()

from fastapi import FastAPI

from app.api.bilingual_subtitle import router as bilingual_subtitle_router
from app.api.qa import router as qa_router
from app.api.subtitle import router as subtitle_router
from app.api.subtitle_editor import router as subtitle_editor_router
from app.api.summary import router as summary_router
from app.api.translation import router as translation_router
from app.api.video import router as video_router
from app.config.environment import is_development_environment


app = FastAPI(
    title="VideoMind-Agent",
    description="AI video understanding agent API.",
    version="0.7.1",
)

# Register video upload, transcription, and subtitle generation endpoints.
app.include_router(video_router)
app.include_router(translation_router)
app.include_router(bilingual_subtitle_router)
app.include_router(subtitle_editor_router)
app.include_router(subtitle_router)
app.include_router(summary_router)
app.include_router(qa_router)
if is_development_environment():
    from app.api.debug_transcript_correction import router as correction_debug_router

    app.include_router(correction_debug_router)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "ok"}
