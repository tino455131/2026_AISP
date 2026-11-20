"""The "查看" buttons read only through AuthorizedTranscriptReader.

Needs discord.py, so run it with discord_bot's environment (from the repo root):
    discord_bot/.venv/Scripts/python.exe -m unittest meeting_ai.tests.test_show_session -v
Under voice_stt's environment (no discord.py) it is skipped.
"""

import json
import tempfile
import unittest
from pathlib import Path

try:
    import discord  # noqa: F401
except ImportError:
    raise unittest.SkipTest("needs discord.py: run with discord_bot/.venv")

from meeting_ai.show_session import NO_SUMMARY, read_for_member, refused
from channel_access import AccessUnavailable
from transcript_reader import AuthorizedTranscriptReader
from transcript_store import NewLine, TranscriptStore

VOICE = 301  # Alice (1) and Bob (2) can see it; Carol (3) cannot
ALICE, BOB, CAROL = 1, 2, 3


class FakeAccess:
    guild_id = 10

    def __init__(self) -> None:
        self.unavailable = False

    async def can_read_history(self, member_id: int, channel_id: int) -> bool:
        if self.unavailable:
            raise AccessUnavailable("Discord could not confirm access")
        return channel_id == VOICE and member_id in {ALICE, BOB}


def line(speaker_id, at, text, confidence=0.9):
    return NewLine(speaker_id, at, at, text, text, confidence)


class ShowSessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = TranscriptStore(Path(temp.name) / "messages.sqlite3")
        self.store.start_session("s1", 10, VOICE, "2026-11-18T06:00:00+00:00")
        self.store.add_lines(
            "s1",
            [
                line(ALICE, "2026-11-18T06:00:01+00:00", "我們決定下週一 merge"),
                line(BOB, "2026-11-18T06:00:05+00:00", "我來寫測試", confidence=0.2),
            ],
        )
        self.access = FakeAccess()
        self.reader = AuthorizedTranscriptReader(self.access, self.store)
        self.asked_names = False

    async def names_of(self, ids):
        self.asked_names = True
        return {ALICE: "Alice", BOB: "Bob"}

    def save_summary(self, line_count=2):
        content = {
            "summary": "討論 merge 時間",
            "decisions": [{"text": "下週一 merge", "source_line_ids": [1]}],
            "action_items": [{"task": "寫測試", "owner": "S2", "due": "", "source_line_ids": [2]}],
        }
        self.store.save_summary("s1", json.dumps(content), model="keyword-rules", prompt_version="v1",
                                created_at="2026-11-18T06:10:00+00:00")

    async def test_anyone_who_can_see_the_channel_gets_the_summary_with_names(self):
        self.save_summary()
        result = await read_for_member(self.reader, BOB, "s1", "summary", self.names_of)
        self.assertTrue(result["ok"])
        self.assertIn("下週一 merge", result["text"])
        self.assertIn("Bob：寫測試", result["text"])  # S2 -> Bob, no @mention
        self.assertNotIn("過時", result["text"])

    async def test_transcript_shows_names_and_marks_unsure_lines(self):
        result = await read_for_member(self.reader, ALICE, "s1", "transcript", self.names_of)
        lines = result["text"].splitlines()
        self.assertIn("**Alice**：我們決定下週一 merge", lines[1])
        self.assertTrue(lines[2].endswith("我來寫測試 ⚠️"))
        self.assertEqual(lines[-1], "-# ⚠️ = 可能聽錯")

    async def test_someone_who_cannot_see_the_channel_gets_nothing(self):
        self.save_summary()
        result = await read_for_member(self.reader, CAROL, "s1", "summary", self.names_of)
        self.assertEqual(result, refused("ACCESS_DENIED_USER"))
        self.assertFalse(self.asked_names)  # not even the speakers' names

    async def test_unconfirmed_access_returns_nothing(self):
        self.access.unavailable = True
        result = await read_for_member(self.reader, ALICE, "s1", "transcript", self.names_of)
        self.assertEqual(result, refused("PERMISSION_UNVERIFIED"))

    async def test_missing_session_or_summary(self):
        self.assertEqual(
            await read_for_member(self.reader, ALICE, "nope", "summary", self.names_of),
            refused("NOT_FOUND"),
        )
        self.assertEqual(
            await read_for_member(self.reader, ALICE, "s1", "summary", self.names_of),
            {"ok": False, "error_code": "NOT_FOUND", "message": NO_SUMMARY},
        )

    async def test_summary_written_before_lines_changed_is_marked(self):
        self.save_summary()
        self.store.add_lines("s1", [line(ALICE, "2026-11-18T06:00:09+00:00", "補一句")])
        result = await read_for_member(self.reader, ALICE, "s1", "summary", self.names_of)
        self.assertIn("可能過時", result["text"])


if __name__ == "__main__":
    unittest.main()
