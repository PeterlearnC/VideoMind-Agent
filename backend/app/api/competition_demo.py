"""Read-only API for the preloaded Competition Demo workspace."""

from fastapi import APIRouter, HTTPException, status

from app.config.competition_demo import competition_demo_mode_enabled
from app.services.competition_demo_service import competition_demo_payload


router = APIRouter(tags=["competition-demo"])


@router.get("/competition-demo/status")
async def get_competition_demo_status() -> dict[str, object]:
    if not competition_demo_mode_enabled():
        return {"enabled": False, "mode": "normal"}
    try:
        return competition_demo_payload()
    except (OSError, UnicodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Competition demo fixture is unavailable.",
        ) from exc
