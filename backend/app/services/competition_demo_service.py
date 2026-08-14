"""Install and expose the preloaded, offline-safe competition demo fixture."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from app.config.competition_demo import (
    COMPETITION_DEMO_MESSAGE,
    competition_demo_mode_enabled,
    deepseek_api_key_configured,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEMO_ROOT = PROJECT_ROOT / "demo" / "competition"
VIDEO_DIR = PROJECT_ROOT / "data" / "videos"
SUBTITLE_DIR = PROJECT_ROOT / "data" / "subtitles"
DEMO_VIDEO_ID = "competition-demo"


def _load_json(filename: str) -> Any:
    path = DEMO_ROOT / filename
    return json.loads(path.read_text(encoding="utf-8"))


def install_competition_demo_workspace() -> bool:
    """Copy immutable fixture assets into ignored runtime data when needed."""
    if not competition_demo_mode_enabled():
        return False

    workspace_source = DEMO_ROOT / "workspace.json"
    video_source = DEMO_ROOT / "competition-demo.mp4"
    if not workspace_source.is_file() or not video_source.is_file():
        raise FileNotFoundError("Competition demo fixture is incomplete.")

    SUBTITLE_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    workspace_destination = SUBTITLE_DIR / f"{DEMO_VIDEO_ID}.json"
    video_destination = VIDEO_DIR / video_source.name
    if not workspace_destination.exists():
        shutil.copyfile(workspace_source, workspace_destination)
    if not video_destination.exists():
        shutil.copyfile(video_source, video_destination)
    return True


def competition_demo_payload() -> dict[str, Any]:
    install_competition_demo_workspace()
    workspace = _load_json("workspace.json")
    metadata = _load_json("metadata.json")
    summary = _load_json("summary.json")
    qa_history = _load_json("qa.json")
    workspace_metadata = workspace.get("metadata", {}).get("workspace", {})
    return {
        "enabled": True,
        "mode": "competition_demo",
        "label": "Preloaded Demo / Competition Demo",
        "message": COMPETITION_DEMO_MESSAGE,
        "api_key_configured": deepseek_api_key_configured(),
        "workspace": {
            "video_id": DEMO_VIDEO_ID,
            "video_name": workspace_metadata.get("video_name"),
            "source_language": workspace.get("source_language"),
            "target_language": workspace.get("target_language"),
        },
        "summary": summary,
        "qa_history": qa_history,
        "fixture": metadata,
    }
