"""Tests for the development-only transcript correction diagnostic endpoint."""

import unittest
from unittest.mock import patch

from app.api.debug_transcript_correction import (
    DebugCorrectionRequest,
    debug_transcript_correction,
)
from app.main import app
from app.services.transcript_correction_service import TranscriptCorrectionResult


class DebugTranscriptCorrectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_endpoint_returns_real_service_result_shape(self) -> None:
        result = TranscriptCorrectionResult(
            segments=[
                {
                    "id": 0,
                    "start": 0.0,
                    "end": 0.0,
                    "raw_text": "水泥的售命只有50年",
                    "corrected_text": "水泥的寿命只有50年",
                }
            ],
            metadata={
                "enabled": True,
                "attempted": True,
                "success": True,
                "fallback": False,
                "changed_segments": 1,
                "total_segments": 1,
                "batches": 1,
                "failed_batches": 0,
                "zero_change_warning": False,
                "error": None,
            },
        )
        request = DebugCorrectionRequest(
            language="zh",
            segments=[{"id": 0, "text": "水泥的售命只有50年"}],
        )

        with patch(
            "app.api.debug_transcript_correction.correct_transcript_with_metadata",
            return_value=result,
        ) as correct:
            payload = await debug_transcript_correction(request)

        correct.assert_called_once()
        self.assertEqual(payload["changed_segments"], 1)
        self.assertTrue(payload["success"])
        self.assertFalse(payload["fallback"])
        self.assertEqual(
            payload["corrected"][0]["corrected_text"],
            "水泥的寿命只有50年",
        )

    def test_route_is_registered_in_default_development_environment(self) -> None:
        self.assertIn("/debug/transcript-correction", app.openapi()["paths"])


if __name__ == "__main__":
    unittest.main()
