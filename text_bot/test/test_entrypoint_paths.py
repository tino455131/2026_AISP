"""Smoke tests for the repository's Python entry points after moving modules."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class EntrypointPathTests(unittest.TestCase):
    def run_python(self, *args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        env["PYTHON_DOTENV_DISABLED"] = "1"
        env["TEXT_BOT_TOKEN"] = ""
        return subprocess.run(
            [sys.executable, "-X", "utf8", *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            encoding="utf-8",
            timeout=20,
            check=False,
        )

    def assert_cli_help(self, module: str, cwd: Path) -> None:
        result = self.run_python("-m", module, "--help", cwd=cwd)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage:", result.stdout)

    def test_text_bot_entrypoint_imports_from_outside_repo(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aisp text bot ") as directory:
            result = self.run_python(str(REPO_ROOT / "text_bot" / "bot.py"), cwd=Path(directory))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Missing TEXT_BOT_TOKEN", result.stderr)

    def test_ingest_entrypoint_imports_from_voice_bot_working_directory(self) -> None:
        self.assert_cli_help("stt.ingest_recording", REPO_ROOT / "voice_bot" / "voice_stt")

    def test_stt_entrypoint_imports_from_repo_root(self) -> None:
        self.assert_cli_help("voice_bot.voice_stt.stt", REPO_ROOT)

    def test_viewer_entrypoint_imports_text_bot_readers(self) -> None:
        self.assert_cli_help("meeting_ai.show_session", REPO_ROOT)
