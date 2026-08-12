"""Tests for process-safe backend environment loading."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.config.environment import load_backend_env


class EnvironmentTests(unittest.TestCase):
    def test_loads_backend_env_without_overwriting_process_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_path = Path(temporary_directory) / ".env"
            env_path.write_text(
                "DEEPSEEK_API_KEY=file-key\nTRANSCRIPT_CORRECTION_ENABLED=true\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"DEEPSEEK_API_KEY": "process-key"},
                clear=True,
            ):
                load_backend_env(env_path)
                self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "process-key")
                self.assertEqual(os.environ["TRANSCRIPT_CORRECTION_ENABLED"], "true")


if __name__ == "__main__":
    unittest.main()
