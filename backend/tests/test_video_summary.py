"""Tests for the AI video summary agent and API."""

import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.agents.video_summary_agent import VideoSummaryAgent
from app.api.summary import SummaryRequest, generate_video_summary
from app.main import app


SUMMARY_RESULT = {
    "title": "液压制动系统简介",
    "overview": "视频解释了液压制动系统的工作方式。",
    "key_points": ["压力通过制动液传递", "制动力作用于车轮"],
    "chapters": [
        {
            "start": 0,
            "end": 8,
            "title": "工作原理",
            "summary": "介绍压力传递过程。",
        }
    ],
    "keywords": ["液压", "制动"],
}


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "choices": [
                {"message": {"content": json.dumps(SUMMARY_RESULT, ensure_ascii=False)}}
            ]
        }


class FakeSession:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append({"url": url, **kwargs})
        return FakeResponse()


class VideoSummaryAgentTests(unittest.TestCase):
    def test_generates_structured_summary_from_timestamped_cues(self) -> None:
        session = FakeSession()
        agent = VideoSummaryAgent(api_key="test-key", session=session)
        cues = [
            {
                "start": 0,
                "end": 8,
                "source": "Hydraulic pressure applies the brakes.",
                "translation": "液压压力启动制动器。",
            }
        ]

        result = agent.summarize(cues)

        self.assertEqual(result, SUMMARY_RESULT)
        request = session.requests[0]
        self.assertEqual(request["url"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(request["json"]["model"], "deepseek-chat")
        self.assertIn(
            "[00:00:00] Hydraulic pressure applies the brakes.",
            request["json"]["messages"][1]["content"],
        )

    def test_rejects_empty_subtitle_track(self) -> None:
        agent = VideoSummaryAgent(api_key="test-key", session=FakeSession())
        with self.assertRaisesRegex(Exception, "contains no content"):
            agent.summarize([])


class VideoSummaryApiTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.api.summary.get_subtitle", new_callable=AsyncMock)
    async def test_api_reads_subtitles_and_runs_agent(self, get_subtitle: AsyncMock) -> None:
        cues = [{"start": 0, "end": 8, "source": "Test", "translation": "测试"}]
        get_subtitle.return_value = {"video_id": "demo", "subtitles": cues}
        agent = Mock()
        agent.summarize.return_value = SUMMARY_RESULT

        with patch("app.api.summary._get_summary_agent", return_value=agent):
            result = await generate_video_summary("demo", SummaryRequest())

        self.assertEqual(result.video_id, "demo")
        self.assertEqual(result.title, SUMMARY_RESULT["title"])
        agent.summarize.assert_called_once_with(cues, "zh")

    def test_summary_route_is_registered(self) -> None:
        self.assertIn("/summary/{video_id}", app.openapi()["paths"])


if __name__ == "__main__":
    unittest.main()
