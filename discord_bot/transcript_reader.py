"""The only entry point AI features should use for saved voice transcripts.

規則和 AuthorizedMessageReader 一樣：每次讀取前都用 ChannelAccess 當下確認，
提問的人現在能不能讀這個「語音頻道」的歷史（View Channel + Read Message History）。
沒有權限拋 AccessDenied；Discord 無法確認時拋 AccessUnavailable，不回傳任何內容。

目前的規則：看得到語音頻道的人，就能讀那個頻道的逐字稿（即使當天沒參加會議）。
是否要再限制成「只有在場的人」，待團隊決定。
"""

import asyncio
from dataclasses import dataclass

from channel_access import AccessDenied, ChannelAccess
from transcript_store import SessionSummary, TranscriptLine, TranscriptStore, VoiceSession


@dataclass(frozen=True)
class SummaryView:
    summary: SessionSummary
    is_stale: bool  # True = lines were added or removed after it was written; redo it


class AuthorizedTranscriptReader:
    def __init__(self, access: ChannelAccess, store: TranscriptStore) -> None:
        self.access = access
        self.store = store

    async def recent_sessions_for(
        self, member_id: int, channel_id: int, limit: int = 20
    ) -> list[VoiceSession]:
        """Newest recordings of one voice channel, newest first."""
        await self._require(member_id, channel_id)
        return await asyncio.to_thread(self.store.recent_sessions, self.access.guild_id, channel_id, limit)

    async def transcript_for(self, member_id: int, session_id: str) -> list[TranscriptLine]:
        """Every saved sentence of one recording, in time order."""
        await self._require_session(member_id, session_id)
        return await asyncio.to_thread(self.store.lines, session_id)

    async def summary_for(self, member_id: int, session_id: str) -> SummaryView | None:
        """The stored summary of one recording, or None when none was written yet."""
        await self._require_session(member_id, session_id)
        summary = await asyncio.to_thread(self.store.summary, session_id)
        if summary is None:
            return None
        count = await asyncio.to_thread(self.store.line_count, session_id)
        return SummaryView(summary=summary, is_stale=count != summary.source_line_count)

    async def _require_session(self, member_id: int, session_id: str) -> None:
        session = await asyncio.to_thread(self.store.get_session, session_id)  # SessionNotFound
        if session.guild_id != self.access.guild_id:
            raise AccessDenied("Recording belongs to another server")
        await self._require(member_id, session.channel_id)

    async def _require(self, member_id: int, channel_id: int) -> None:
        if not await self.access.can_read_history(member_id, channel_id):
            raise AccessDenied("Member cannot read this voice channel's history")
