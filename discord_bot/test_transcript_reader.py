"""Reading transcripts must pass the same current-permission check as text."""

import tempfile
import unittest
from pathlib import Path

from channel_access import AccessDenied, AccessUnavailable
from transcript_reader import AuthorizedTranscriptReader
from transcript_store import NewLine, SessionNotFound, TranscriptStore

TEAM_VOICE = 301  # Alice (1) and Bob (2) can see it
LEADER_VOICE = 302  # only Alice (1) can see it


class FakeAccess:
    """Stands in for ChannelAccess: who can read which channel right now."""

    guild_id = 10

    def __init__(self) -> None:
        self.readable = {TEAM_VOICE: {1, 2}, LEADER_VOICE: {1}}
        self.unavailable = False

    async def can_read_history(self, member_id: int, channel_id: int) -> bool:
        if self.unavailable:
            raise AccessUnavailable("Discord could not confirm access")
        return member_id in self.readable.get(channel_id, set())


def line(speaker_id, text):
    return NewLine(speaker_id, "2026-11-18T06:00:01+00:00", "2026-11-18T06:00:03+00:00", text, text, 0.9)


class TranscriptReaderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp_dir.cleanup)
        self.store = TranscriptStore(Path(self.temp_dir.name) / "messages.sqlite3")
        self.store.start_session("team-1", 10, TEAM_VOICE, "2026-11-18T06:00:00+00:00")
        self.store.add_lines("team-1", [line(1, "先看進度"), line(2, "我做完了")])
        self.store.start_session("leader-1", 10, LEADER_VOICE, "2026-11-18T07:00:00+00:00")
        self.store.add_lines("leader-1", [line(1, "私下討論")])
        self.access = FakeAccess()
        self.reader = AuthorizedTranscriptReader(self.access, self.store)

    async def test_member_with_access_reads_transcript(self) -> None:
        lines = await self.reader.transcript_for(2, "team-1")
        self.assertEqual([item.text for item in lines], ["先看進度", "我做完了"])
        sessions = await self.reader.recent_sessions_for(2, TEAM_VOICE)
        self.assertEqual([s.session_id for s in sessions], ["team-1"])

    async def test_private_voice_channel_is_denied_to_others(self) -> None:
        with self.assertRaises(AccessDenied):
            await self.reader.transcript_for(2, "leader-1")
        with self.assertRaises(AccessDenied):
            await self.reader.recent_sessions_for(2, LEADER_VOICE)
        with self.assertRaises(AccessDenied):
            await self.reader.summary_for(2, "leader-1")

    async def test_losing_access_blocks_the_next_read(self) -> None:
        await self.reader.transcript_for(2, "team-1")
        self.access.readable[TEAM_VOICE].discard(2)
        with self.assertRaises(AccessDenied):
            await self.reader.transcript_for(2, "team-1")

    async def test_unconfirmed_access_returns_nothing(self) -> None:
        self.access.unavailable = True
        with self.assertRaises(AccessUnavailable):
            await self.reader.transcript_for(1, "team-1")

    async def test_unknown_session(self) -> None:
        with self.assertRaises(SessionNotFound):
            await self.reader.transcript_for(1, "missing")

    async def test_summary_is_marked_stale_after_new_lines(self) -> None:
        self.assertIsNone(await self.reader.summary_for(1, "team-1"))
        self.store.save_summary("team-1", "API 完成", "test-model", "v1", "2026-11-18T08:00:00+00:00")
        view = await self.reader.summary_for(1, "team-1")
        self.assertFalse(view.is_stale)
        self.store.add_lines("team-1", [line(1, "補一句")])
        view = await self.reader.summary_for(1, "team-1")
        self.assertTrue(view.is_stale)


if __name__ == "__main__":
    unittest.main()
