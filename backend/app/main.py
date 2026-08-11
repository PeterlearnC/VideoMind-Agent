"""VideoMind-Agent FastAPI application entry point."""

from fastapi import FastAPI

from app.api.bilingual_subtitle import router as bilingual_subtitle_router
from app.api.subtitle import router as subtitle_router
from app.api.translation import router as translation_router
from app.api.video import router as video_router


app = FastAPI(
    title="VideoMind-Agent",
    description="AI video understanding agent API.",
    version="0.1.0",
)

# Register video upload, transcription, and subtitle generation endpoints.
app.include_router(video_router)
app.include_router(translation_router)
app.include_router(bilingual_subtitle_router)
app.include_router(subtitle_router)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "ok"}
