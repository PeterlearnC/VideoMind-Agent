"""Tests for grounded Video Q&A agent and API."""

import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.agents.video_qa_agent import VideoQAAgent
from app.api.qa import VideoQARequest, answer_video_question
from app.main import app


QA_RESULT = {
    "answer": "视频在约 00:11 开始介绍液压制动系统。",
    "references": [
        {
            "timestamp": "00:11",
            "start": 11.0,
            "text": "车辆采用液压制动系统。",
        }
    ],
}

MODEL_QA_RESULT = {
    "answer": QA_RESULT["answer"],
    "references": [{"cue_id": 0, "text": QA_RESULT["references"][0]["text"]}],
}


class FakeResponse:
    def __init__(self, result: object = MODEL_QA_RESULT) -> None:
        self.result = result

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "choices": [
                {"message": {"content": json.dumps(self.result, ensure_ascii=False)}}
            ]
        }


class FakeSession:
    def __init__(self, result: object = MODEL_QA_RESULT) -> None:
        self.result = result
        self.requests: list[dict[str, object]] = []

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append({"url": url, **kwargs})
        return FakeResponse(self.result)


class VideoQAAgentTests(unittest.TestCase):
    def test_answers_from_timestamped_subtitles(self) -> None:
        session = FakeSession()
        agent = VideoQAAgent(api_key="test-key", session=session)
        cues = [
            {
                "start": 11.0,
                "end": 15.0,
                "source": "The vehicle uses a hydraulic braking system.",
                "translation": "车辆采用液压制动系统。",
            }
        ]

        result = agent.answer("demo", "什么时候介绍刹车系统？", cues)

        self.assertEqual(result, MODEL_QA_RESULT)
        request = session.requests[0]
        self.assertEqual(request["url"], VideoQAAgent.API_URL)
        prompt = request["json"]["messages"][1]["content"]
        self.assertIn("Video ID: demo", prompt)
        self.assertIn("cue_id=0", prompt)
        self.assertIn("液压制动系统", prompt)

    def test_prefers_corrected_transcript(self) -> None:
        session = FakeSession()
        agent = VideoQAAgent(api_key="test-key", session=session)

        agent.answer(
            "demo",
            "What is said?",
            [{"id": 3, "start": 2, "raw_text": "wrong", "corrected_text": "correct"}],
        )

        prompt = session.requests[0]["json"]["messages"][1]["content"]
        self.assertIn("correct", prompt)
        self.assertNotIn("wrong", prompt)

    def test_prefers_human_edited_transcript(self) -> None:
        session = FakeSession()
        agent = VideoQAAgent(api_key="test-key", session=session)
        agent.answer("demo", "What is said?", [{
            "id": 3, "start": 2,
            "corrected_text": "AI source", "translated_text": "AI translation",
            "edited_source_text": "Human source",
            "edited_translated_text": "Human translation",
        }])
        prompt = session.requests[0]["json"]["messages"][1]["content"]
        self.assertIn("Human source / Human translation", prompt)
        self.assertNotIn("AI source", prompt)


class VideoQAApiTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.api.qa.get_subtitle", new_callable=AsyncMock)
    async def test_returns_structured_answer_with_numeric_start(
        self, get_subtitle: AsyncMock
    ) -> None:
        cues = [{"id": 0, "start": 11.0, "end": 15.0, "source": "Brakes"}]
        get_subtitle.return_value = {"video_id": "demo", "subtitles": cues}
        agent = Mock()
        agent.answer.return_value = MODEL_QA_RESULT

        with patch("app.api.qa._get_qa_agent", return_value=agent):
            result = await answer_video_question(
                "demo", VideoQARequest(question="什么时候介绍刹车系统？")
            )

        self.assertEqual(result.video_id, "demo")
        self.assertEqual(result.references[0].start, 11.0)
        self.assertEqual(result.references[0].timestamp, "00:11")
        agent.answer.assert_called_once_with(
            "demo", "什么时候介绍刹车系统？", cues
        )

    def test_rejects_blank_question(self) -> None:
        with self.assertRaises(ValidationError):
            VideoQARequest(question="   ")

    @patch("app.api.qa.get_subtitle", new_callable=AsyncMock)
    async def test_propagates_missing_video_subtitle_404(
        self, get_subtitle: AsyncMock
    ) -> None:
        get_subtitle.side_effect = HTTPException(
            status_code=404,
            detail="Subtitle track 'missing' was not found.",
        )

        with self.assertRaises(HTTPException) as raised:
            await answer_video_question(
                "missing", VideoQARequest(question="视频讲了什么？")
            )

        self.assertEqual(raised.exception.status_code, 404)

    @patch("app.api.qa.get_subtitle", new_callable=AsyncMock)
    async def test_returns_422_for_empty_subtitle_track(
        self, get_subtitle: AsyncMock
    ) -> None:
        get_subtitle.return_value = {"video_id": "demo", "subtitles": []}

        with self.assertRaises(HTTPException) as raised:
            await answer_video_question(
                "demo", VideoQARequest(question="视频讲了什么？")
            )

        self.assertEqual(raised.exception.status_code, 422)

    @patch("app.api.qa.get_subtitle", new_callable=AsyncMock)
    async def test_returns_502_for_invalid_model_structure(
        self, get_subtitle: AsyncMock
    ) -> None:
        get_subtitle.return_value = {
            "video_id": "demo",
            "subtitles": [{"start": 1.0, "end": 2.0, "source": "Test"}],
        }
        agent = Mock()
        agent.answer.return_value = {
            "answer": "有答案",
            "references": [{"text": "缺少 cue_id"}],
        }

        with patch("app.api.qa._get_qa_agent", return_value=agent):
            with self.assertRaises(HTTPException) as raised:
                await answer_video_question(
                    "demo", VideoQARequest(question="测试问题")
                )

        self.assertEqual(raised.exception.status_code, 502)
        self.assertIn("invalid video Q&A structure", raised.exception.detail)

    @patch("app.api.qa.get_subtitle", new_callable=AsyncMock)
    async def test_rejects_reference_outside_subtitle_cues(
        self, get_subtitle: AsyncMock
    ) -> None:
        get_subtitle.return_value = {
            "video_id": "demo",
            "subtitles": [{"id": 0, "start": 11.0, "end": 15.0, "source": "Brakes"}],
        }
        agent = Mock()
        agent.answer.return_value = {
            **MODEL_QA_RESULT,
            "references": [{"cue_id": 99, "text": "错误引用"}],
        }

        with patch("app.api.qa._get_qa_agent", return_value=agent):
            with self.assertRaises(HTTPException) as raised:
                await answer_video_question(
                    "demo", VideoQARequest(question="测试问题")
                )

        self.assertEqual(raised.exception.status_code, 502)
        self.assertIn("was not found", raised.exception.detail)

    def test_qa_route_is_registered(self) -> None:
        self.assertIn("/qa/{video_id}", app.openapi()["paths"])


if __name__ == "__main__":
    unittest.main()
