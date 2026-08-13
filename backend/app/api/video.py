"""Video upload API."""

import asyncio
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.services.subtitle_service import generate_srt
from app.services.whisper_service import transcribe_audio
from app.services.performance_metrics import collect_video_metadata, get_active_run


router = APIRouter(tags=["video"])

PROJECT_ROOT = Path(__file__).resolve().parents[3]
VIDEO_DIR = PROJECT_ROOT / "data" / "videos"
AUDIO_DIR = PROJECT_ROOT / "data" / "audio"
SUBTITLE_DIR = PROJECT_ROOT / "data" / "subtitles"
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi"}
VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


@router.get("/video/{video_id}")
async def get_workspace_video(video_id: str) -> FileResponse:
    """Return the saved source video associated with a subtitle workspace."""
    if VIDEO_ID_PATTERN.fullmatch(video_id) is None:
        raise HTTPException(status_code=400, detail="Invalid video_id.")
    subtitle_document = SUBTITLE_DIR / f"{video_id}.json"
    if not subtitle_document.is_file():
        raise HTTPException(status_code=404, detail="Workspace video not found.")
    try:
        payload = json.loads(subtitle_document.read_text(encoding="utf-8"))
        video_name = payload.get("metadata", {}).get("workspace", {}).get("video_name")
        if not isinstance(video_name, str) or not video_name.strip():
            raise ValueError("Missing workspace video name.")
        safe_name = Path(video_name).name
        if safe_name != video_name or Path(safe_name).suffix.lower() not in ALLOWED_VIDEO_EXTENSIONS:
            raise ValueError("Invalid workspace video name.")
        video_path = VIDEO_DIR / safe_name
    except (AttributeError, json.JSONDecodeError, OSError, UnicodeError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Workspace video not found.") from exc
    if not video_path.is_file():
        raise HTTPException(status_code=404, detail="Workspace video not found.")
    return FileResponse(video_path, media_type="video/mp4")


def _extract_audio(video_path: Path, audio_path: Path) -> None:
    """Extract mono 16 kHz WAV audio from a video using FFmpeg."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


@router.post("/upload-video")
async def upload_video(file: UploadFile = File(...)) -> dict[str, str]:
    """Validate and save an uploaded video in the project data directory."""
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file must have a filename.",
        )

    if Path(filename).suffix.lower() not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported video format. Allowed formats: mp4, mov, avi.",
        )

    destination = VIDEO_DIR / filename

    try:
        VIDEO_DIR.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as output_file:
            while chunk := await file.read(1024 * 1024):
                output_file.write(chunk)
    except Exception as exc:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            # Preserve the original upload error if partial-file cleanup fails.
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save the uploaded video: {exc}",
        ) from exc
    finally:
        try:
            await file.close()
        except Exception:
            # Closing a failed upload must not terminate request handling.
            pass

    saved_path = destination.relative_to(PROJECT_ROOT).as_posix()
    return {
        "filename": filename,
        "saved_path": saved_path,
        "status": "uploaded",
    }


@router.post("/transcribe-video")
async def transcribe_video(file: UploadFile = File(...)) -> dict[str, Any]:
    """Save a video, extract its audio, and transcribe it with Whisper."""
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file must have a filename.",
        )

    if Path(filename).suffix.lower() not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported video format. Allowed formats: mp4, mov, avi.",
        )

    video_path = VIDEO_DIR / filename
    audio_path = AUDIO_DIR / f"{Path(filename).stem}.wav"
    metrics = get_active_run()

    try:
        stage = metrics.stage(
            "upload", measurement_scope="server_receive_and_save"
        ) if metrics else None
        if stage:
            stage.__enter__()
        try:
            VIDEO_DIR.mkdir(parents=True, exist_ok=True)
            with video_path.open("wb") as output_file:
                while chunk := await file.read(1024 * 1024):
                    output_file.write(chunk)
            file_size = video_path.stat().st_size
            if stage:
                stage.update(file_size_bytes=file_size)
            if metrics:
                metrics.set_video(
                    filename=filename,
                    video_name=filename,
                    file_size_bytes=file_size,
                )
        except BaseException as exc:
            if stage:
                stage.__exit__(type(exc), exc, exc.__traceback__)
                stage = None
            raise
        finally:
            if stage:
                stage.__exit__(None, None, None)
    except Exception as exc:
        try:
            video_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save the uploaded video: {exc}",
        ) from exc
    finally:
        try:
            await file.close()
        except Exception:
            pass

    if metrics:
        try:
            video_metadata = await asyncio.to_thread(
                collect_video_metadata, video_path
            )
            metrics.set_video(**video_metadata)
        except Exception as exc:
            # Metrics are best-effort; even scheduling/collection failures must
            # never prevent audio extraction and transcription.
            metrics.set_video(
                filename=filename,
                video_name=filename,
                file_size_bytes=file_size,
                metadata_collection_status="failed",
                metadata_collection_error_type=type(exc).__name__,
            )

    try:
        if metrics:
            with metrics.stage("media_preparation"):
                await asyncio.to_thread(_extract_audio, video_path, audio_path)
        else:
            await asyncio.to_thread(_extract_audio, video_path, audio_path)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="FFmpeg is not installed or is not available on PATH.",
        ) from exc
    except subprocess.CalledProcessError as exc:
        try:
            audio_path.unlink(missing_ok=True)
        except OSError:
            pass
        error_message = (exc.stderr or "Unknown FFmpeg error").strip()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to extract audio from the video: {error_message}",
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to prepare audio extraction: {exc}",
        ) from exc

    try:
        if metrics:
            with metrics.stage("whisper_transcription") as stage:
                transcription = await asyncio.to_thread(transcribe_audio, audio_path)
                stage.update(raw_segment_count=len(transcription.get("segments", [])))
        else:
            transcription = await asyncio.to_thread(transcribe_audio, audio_path)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to transcribe the video: {exc}",
        ) from exc

    return {
        "filename": filename,
        "language": transcription["language"],
        "segments": transcription["segments"],
    }


@router.post("/generate-subtitle")
async def generate_subtitle(file: UploadFile = File(...)) -> dict[str, str]:
    """Transcribe an uploaded video and generate an SRT subtitle file."""
    transcription = await transcribe_video(file)
    filename = transcription["filename"]
    subtitle_path = SUBTITLE_DIR / f"{Path(filename).stem}.srt"

    try:
        await asyncio.to_thread(
            generate_srt,
            transcription["segments"],
            subtitle_path,
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate subtitles: {exc}",
        ) from exc

    return {
        "filename": filename,
        "language": transcription["language"],
        "subtitle_file": subtitle_path.relative_to(PROJECT_ROOT).as_posix(),
    }
