"""Subtitle editor, reset, batch-save, and effective SRT export APIs."""

import math
from numbers import Real
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.subtitle import VIDEO_ID_PATTERN
from app.api.video import SUBTITLE_DIR
from app.services.subtitle_editor_service import (
    SubtitleCueNotFound,
    SubtitleEditorError,
    InvalidSubtitleDocument,
    SubtitleTrackNotFound,
    editor_payload,
    reset_cue,
    update_cues,
)
from app.services.subtitle_service import _format_srt_timestamp


router = APIRouter(tags=["subtitle-editor"])


def _path(video_id: str):
    if VIDEO_ID_PATTERN.fullmatch(video_id) is None:
        raise HTTPException(status_code=400, detail="Invalid video_id.")
    return SUBTITLE_DIR / f"{video_id}.json"


def _text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Subtitle text cannot be blank.")
    return normalized


class CueUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_text: str | None = None
    translated_text: str | None = None

    @field_validator("source_text", "translated_text", mode="before")
    @classmethod
    def validate_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Subtitle text must be a string.")
        if len(value) > 5000:
            raise ValueError("Subtitle text exceeds maximum length.")
        return _text(value)

    @model_validator(mode="after")
    def require_update(self):
        if "source_text" not in self.model_fields_set and "translated_text" not in self.model_fields_set:
            raise ValueError("At least one subtitle field is required.")
        return self


class BatchCueUpdate(CueUpdate):
    id: int | str


class BatchUpdateRequest(BaseModel):
    updates: list[BatchCueUpdate] = Field(min_length=1)


class ResetRequest(BaseModel):
    field: Literal["source", "translation", "all"]


def _handle_storage(exc: Exception):
    if isinstance(exc, (SubtitleTrackNotFound, SubtitleCueNotFound)):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail="Invalid subtitle document.") from exc


def _validate_export_cues(cues: list[dict[str, Any]]) -> None:
    seen_ids: set[str] = set()
    for cue in cues:
        cue_id = cue.get("id")
        normalized_id = str(cue_id).strip() if cue_id is not None else ""
        if not normalized_id or normalized_id in seen_ids:
            raise HTTPException(status_code=500, detail="Invalid subtitle document: invalid cue id.")
        seen_ids.add(normalized_id)
        start = cue.get("start")
        end = cue.get("end")
        if (
            isinstance(start, bool) or isinstance(end, bool)
            or not isinstance(start, Real) or not isinstance(end, Real)
            or not math.isfinite(float(start)) or not math.isfinite(float(end))
            or float(end) < float(start)
        ):
            raise HTTPException(status_code=500, detail="Invalid subtitle document: invalid cue timeline.")
        if not str(cue.get("effective_source_text", "")).strip():
            raise HTTPException(status_code=500, detail="Invalid subtitle document: effective source text is blank.")


@router.get("/subtitle/editor/{video_id}")
async def get_editor(video_id: str) -> dict[str, Any]:
    try:
        return editor_payload(_path(video_id), video_id)
    except SubtitleEditorError as exc:
        _handle_storage(exc)


@router.patch("/subtitle/editor/{video_id}/{cue_id}")
async def patch_cue(video_id: str, cue_id: str, request: CueUpdate) -> dict[str, Any]:
    update = {"id": cue_id, **request.model_dump(exclude_unset=True)}
    try:
        return update_cues(_path(video_id), [update])[0]
    except SubtitleEditorError as exc:
        _handle_storage(exc)


@router.patch("/subtitle/editor/{video_id}")
async def patch_cues(video_id: str, request: BatchUpdateRequest) -> dict[str, Any]:
    updates = [item.model_dump(exclude_unset=True) for item in request.updates]
    try:
        cues = update_cues(_path(video_id), updates)
        return {"video_id": video_id, "updated": len(cues), "subtitles": cues}
    except SubtitleEditorError as exc:
        _handle_storage(exc)


@router.post("/subtitle/editor/{video_id}/{cue_id}/reset")
async def reset_editor_cue(video_id: str, cue_id: str, request: ResetRequest) -> dict[str, Any]:
    try:
        return reset_cue(_path(video_id), cue_id, request.field)
    except SubtitleEditorError as exc:
        _handle_storage(exc)


@router.get("/subtitle/{video_id}/export")
async def export_edited_srt(video_id: str) -> Response:
    try:
        payload = editor_payload(_path(video_id), video_id)
    except SubtitleEditorError as exc:
        _handle_storage(exc)
    _validate_export_cues(payload["subtitles"])
    monolingual = payload["source_language"] == payload["target_language"]
    blocks = []
    for index, cue in enumerate(payload["subtitles"], 1):
        source = cue["effective_source_text"]
        translated = cue["effective_translated_text"]
        text = source if monolingual or not translated else f"{source}\n{translated}"
        blocks.append(
            f"{index}\n{_format_srt_timestamp(cue['start'])} --> "
            f"{_format_srt_timestamp(cue['end'])}\n{text}"
        )
    content = "\n\n".join(blocks) + ("\n" if blocks else "")
    return Response(
        content=content, media_type="application/x-subrip; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{video_id}.srt"'},
    )
