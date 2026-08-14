"""Competition Demo mode configuration and Cloud AI access policy."""

from __future__ import annotations

import os

from fastapi import HTTPException, status


COMPETITION_DEMO_MESSAGE = (
    "当前处于 Competition Demo Mode。已加载预置演示结果。"
    "如需处理新视频或重新生成 AI 内容，请配置 DEEPSEEK_API_KEY。"
)
_PLACEHOLDERS = {
    "your_api_key_here",
    "your_deepseek_api_key",
    "placeholder",
}


def competition_demo_mode_enabled() -> bool:
    return os.getenv("COMPETITION_DEMO_MODE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def deepseek_api_key_configured() -> bool:
    value = os.getenv("DEEPSEEK_API_KEY", "").strip()
    return bool(value) and value.lower() not in _PLACEHOLDERS


def competition_demo_cloud_ai_blocked() -> bool:
    return competition_demo_mode_enabled() and not deepseek_api_key_configured()


def require_cloud_ai_available() -> None:
    """Return a friendly response before any Cloud LLM work is attempted."""
    if competition_demo_cloud_ai_blocked():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=COMPETITION_DEMO_MESSAGE,
        )
