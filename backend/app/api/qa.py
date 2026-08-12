"""API for grounded questions and answers about a video."""

import asyncio

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.agents.video_qa_agent import (
    VideoQAAgent,
    VideoQAAgentConfigurationError,
    VideoQAAgentError,
)
from app.api.subtitle import get_subtitle


router = APIRouter(tags=["qa"])


class VideoQARequest(BaseModel):
    """One question about a video's subtitle content."""

    question: str = Field(min_length=1, max_length=1000)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Question must not be empty.")
        return normalized


class VideoQAReference(BaseModel):
    """One timestamped video segment supporting an answer."""

    timestamp: str = Field(min_length=1)
    start: float = Field(ge=0)
    text: str = Field(min_length=1)


class VideoQAResponse(BaseModel):
    """A grounded video answer and its supporting segments."""

    video_id: str
    answer: str = Field(min_length=1)
    references: list[VideoQAReference]


class VideoQAModelReference(BaseModel):
    """A model-selected cue; timing is resolved by the server."""

    cue_id: str | int
    text: str = Field(min_length=1)


class VideoQAModelResponse(BaseModel):
    """Internal DeepSeek result without model-authored timestamps."""

    answer: str = Field(min_length=1)
    references: list[VideoQAModelReference]


def _get_qa_agent() -> VideoQAAgent:
    return VideoQAAgent()


def _format_timestamp(start: float) -> str:
    total_seconds = max(0, int(start))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _build_response_from_cues(
    video_id: str,
    result: object,
    cues: list[dict[str, object]],
) -> VideoQAResponse:
    model_response = VideoQAModelResponse.model_validate(result)
    cues_by_id = {
        str(cue.get("id", index)): cue for index, cue in enumerate(cues)
    }
    references: list[VideoQAReference] = []
    for model_reference in model_response.references:
        cue_id = str(model_reference.cue_id)
        if cue_id not in cues_by_id:
            raise ValueError(f"Reference cue_id {cue_id!r} was not found.")
        start = float(cues_by_id[cue_id]["start"])
        references.append(
            VideoQAReference(
                timestamp=_format_timestamp(start),
                start=start,
                text=model_reference.text,
            )
        )
    return VideoQAResponse(
        video_id=video_id,
        answer=model_response.answer,
        references=references,
    )


@router.post("/qa/{video_id}", response_model=VideoQAResponse)
async def answer_video_question(
    video_id: str,
    request: VideoQARequest,
) -> VideoQAResponse:
    """Answer a question using only the requested video's subtitle track."""
    subtitle_payload = await get_subtitle(video_id)
    cues = subtitle_payload["subtitles"]
    if not cues:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The subtitle track contains no content.",
        )

    try:
        result = await asyncio.to_thread(
            _get_qa_agent().answer,
            video_id,
            request.question,
            cues,
        )
        return _build_response_from_cues(video_id, result, cues)
    except VideoQAAgentConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except VideoQAAgentError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"DeepSeek returned an invalid video Q&A structure: {exc}",
        ) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"DeepSeek returned invalid video Q&A references: {exc}",
        ) from exc
