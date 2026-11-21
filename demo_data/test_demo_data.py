"""【測試用】假資料庫和真的程式接得起來：讀取介面、權限、ai_demo 都讀得到。

在 repo 根目錄執行：
    discord_bot/.venv/Scripts/python.exe -m unittest discover -s demo_data
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE), str(HERE.parent / "discord_bot")]

from channel_access import AccessDenied, AccessUnavailable, AuthorizedMessageReader  # noqa: E402
from fake_access import FakeAccess  # noqa: E402
from make_demo_db import (  # noqa: E402
    LEADER_ONLY_CHANNEL_ID, OUTSIDER_ID, PEOPLE, TEXT_CHANNEL_ID, TEXT_MEETING_ID, VOICE_CHANNEL_ID,
    VOICE_SESSION_ID, build,
)
from message_store import MessageStore  # noqa: E402
from transcript_reader import AuthorizedTranscriptReader  # noqa: E402
from transcript_store import TranscriptStore  # noqa: E402

from ai_demo.local_data import LocalData  # noqa: E402

SCRIPT = """# 測試劇本

**A：** 大家好，我們來分工。

**B：** 我可以負責設備。

**C：** 我下週五前出題。

---

**總結**（這裡之後不讀）

**D：** 不應該被讀到。
"""


class DemoDataTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        out = Path(self.tmp.name)
        (out / "script.md").write_text(SCRIPT, encoding="utf-8")
        self.made = build(out / "script.md", out)
        self.db = self.made["db"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_script_becomes_a_voice_session_and_a_text_meeting(self):
        self.assertEqual(self.made["voice_lines"], 4)  # 3 lines before "---" + the explicit assignment
        self.assertEqual(self.made["text_messages"], 4)
        sent = json.loads((Path(self.tmp.name) / "text_meeting_messages.json").read_text(encoding="utf-8"))
        self.assertEqual(sent["messages"][-1]["mentions"], [{"id": str(PEOPLE["C"]), "name": "C"}])

    async def test_readers_check_access_like_the_real_ones(self):
        voice = AuthorizedTranscriptReader(FakeAccess(), TranscriptStore(self.db))
        self.assertEqual([s.session_id for s in await voice.recent_sessions_for(PEOPLE["B"], VOICE_CHANNEL_ID)],
                         [VOICE_SESSION_ID])
        self.assertEqual(len(await voice.transcript_for(PEOPLE["B"], VOICE_SESSION_ID)), 4)
        self.assertFalse((await voice.summary_for(PEOPLE["B"], VOICE_SESSION_ID)).is_stale)
        with self.assertRaises(AccessDenied):
            await voice.transcript_for(OUTSIDER_ID, VOICE_SESSION_ID)
        with self.assertRaises(AccessDenied):  # channel 40 is the leader's only
            await AuthorizedMessageReader(FakeAccess(), MessageStore(self.db)).recent_messages_for(
                PEOPLE["B"], LEADER_ONLY_CHANNEL_ID)
        with self.assertRaises(AccessUnavailable):
            await AuthorizedTranscriptReader(FakeAccess(unavailable=True), TranscriptStore(self.db)).transcript_for(
                PEOPLE["A"], VOICE_SESSION_ID)
        texts = await AuthorizedMessageReader(FakeAccess(), MessageStore(self.db)).recent_messages_for(
            PEOPLE["A"], TEXT_CHANNEL_ID)
        self.assertEqual(len(texts), 4)

    def test_ai_demo_reads_both_meetings_and_names_the_mentioned_owner(self):
        data = LocalData(self.db, Path(self.tmp.name) / "recordings")
        self.assertEqual({m["meeting_id"] for m in data.meetings()}, {VOICE_SESSION_ID, TEXT_MEETING_ID})
        voice = data.meeting(VOICE_SESSION_ID)
        self.assertEqual(voice.names, {"S1": "A", "S2": "B", "S3": "C"})
        text = data.meeting(TEXT_MEETING_ID)  # from the messages table, as in the terminal
        self.assertEqual(len(text.lines), 4)
        self.assertIn("（S3）", text.lines[-1].text)  # "<@1003>" became "@…（S3）": C can be named as owner
        self.assertEqual(text.speakers["S3"], PEOPLE["C"])


if __name__ == "__main__":
    unittest.main()
