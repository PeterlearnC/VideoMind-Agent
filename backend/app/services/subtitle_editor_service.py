"""File-backed subtitle editing with immutable AI baselines and atomic saves."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Any, Mapping


class SubtitleEditorError(RuntimeError):
    """Base subtitle editor storage error."""


class SubtitleTrackNotFound(SubtitleEditorError):
    pass


class SubtitleCueNotFound(SubtitleEditorError):
    pass


class InvalidSubtitleDocument(SubtitleEditorError):
    pass


_locks_guard = threading.Lock()
_locks: dict[Path, threading.Lock] = {}


def _path_lock(path: Path) -> threading.Lock:
    resolved = path.resolve()
    with _locks_guard:
        return _locks.setdefault(resolved, threading.Lock())


def load_structured_track(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SubtitleTrackNotFound("Subtitle document not found.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data.get("subtitles"), list):
            raise ValueError("Missing subtitles array.")
        return data
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, AttributeError) as exc:
        raise InvalidSubtitleDocument("Invalid subtitle document.") from exc


def effective_source_text(cue: Mapping[str, Any]) -> str:
    edited = cue.get("edited_source_text")
    if edited is not None:
        return str(edited)
    return str(cue.get("corrected_text", cue.get("source_text", cue.get("source", ""))))


def effective_translated_text(cue: Mapping[str, Any]) -> str:
    edited = cue.get("edited_translated_text")
    if edited is not None:
        return str(edited)
    return str(cue.get("translated_text", cue.get("translation", "")))


def enrich_cue(cue: Mapping[str, Any], source_language: str | None, target_language: str | None) -> dict[str, Any]:
    item = dict(cue)
    item.setdefault("edited_source_text", None)
    item.setdefault("edited_translated_text", None)
    item["source_language"] = source_language
    item["target_language"] = target_language
    item["is_source_edited"] = item["edited_source_text"] is not None
    item["is_translation_edited"] = item["edited_translated_text"] is not None
    item["effective_source_text"] = effective_source_text(item)
    item["effective_translated_text"] = effective_translated_text(item)
    item["source_text"] = item["effective_source_text"]
    item["source"] = item["effective_source_text"]
    item["translation"] = item["effective_translated_text"]
    return item


def editor_payload(path: Path, video_id: str) -> dict[str, Any]:
    data = load_structured_track(path)
    source_language = data.get("source_language")
    target_language = data.get("target_language")
    return {
        "video_id": video_id,
        "source_language": source_language,
        "target_language": target_language,
        "metadata": data.get("metadata", {}),
        "subtitles": [enrich_cue(cue, source_language, target_language) for cue in data["subtitles"]],
    }


def _find_cue(data: dict[str, Any], cue_id: str | int) -> dict[str, Any]:
    for cue in data["subtitles"]:
        if str(cue.get("id")) == str(cue_id):
            return cue
    raise SubtitleCueNotFound("Subtitle cue not found.")


def _update_editor_metadata(data: dict[str, Any]) -> None:
    metadata = data.setdefault("metadata", {})
    if "correction" not in metadata and data.get("correction") is not None:
        metadata["correction"] = data["correction"]
    edited_cues = sum(
        cue.get("edited_source_text") is not None or cue.get("edited_translated_text") is not None
        for cue in data["subtitles"]
    )
    editor = metadata.setdefault("editor", {})
    editor.update({
        "edited_cues": edited_cues,
        "last_modified": datetime.now(timezone.utc).isoformat(),
        "version": int(editor.get("version", 0)) + 1,
    })


def atomic_write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as temporary:
            temporary_name = temporary.name
            json.dump(data, temporary, ensure_ascii=False, indent=2)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    except OSError as exc:
        raise SubtitleEditorError(f"Failed to save subtitle editor data: {exc}") from exc
    finally:
        if temporary_name:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass


def update_cues(path: Path, updates: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    with _path_lock(path):
        data = load_structured_track(path)
        cues = [_find_cue(data, update["id"]) for update in updates]
        for cue, update in zip(cues, updates):
            if "source_text" in update:
                cue["edited_source_text"] = update["source_text"]
            if "translated_text" in update:
                cue["edited_translated_text"] = update["translated_text"]
        _update_editor_metadata(data)
        atomic_write_json(path, data)
        return [enrich_cue(cue, data.get("source_language"), data.get("target_language")) for cue in cues]


def reset_cue(path: Path, cue_id: str | int, field: str) -> dict[str, Any]:
    with _path_lock(path):
        data = load_structured_track(path)
        cue = _find_cue(data, cue_id)
        if field in {"source", "all"}:
            cue["edited_source_text"] = None
        if field in {"translation", "all"}:
            cue["edited_translated_text"] = None
        _update_editor_metadata(data)
        atomic_write_json(path, data)
        return enrich_cue(cue, data.get("source_language"), data.get("target_language"))
