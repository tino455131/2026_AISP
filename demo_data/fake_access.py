"""【測試用】不用連 Discord 的權限判斷，給 AuthorizedTranscriptReader、AuthorizedMessageReader 用。

真的 ChannelAccess（text_bot/channel_access.py）每次都問 Discord：
「這個人現在能不能看這個頻道、讀訊息歷史」。這裡改成查一張表，其他程式完全一樣。

    access = FakeAccess()                                   # 預設：A～E 看得到語音和文字頻道，40 只有 A
    access = FakeAccess({20: {1001}})                       # 自己設定：只有 1001 看得到頻道 20
    access = FakeAccess(unavailable=True)                   # 假裝 Discord 無法確認 → AccessUnavailable
"""

from __future__ import annotations

from make_demo_db import GUILD_ID, LEADER, LEADER_ONLY_CHANNEL_ID, PEOPLE, TEXT_CHANNEL_ID, VOICE_CHANNEL_ID

from channel_access import AccessUnavailable

TEAM = set(PEOPLE.values())
DEFAULT_READABLE = {
    VOICE_CHANNEL_ID: TEAM,
    TEXT_CHANNEL_ID: TEAM,
    LEADER_ONLY_CHANNEL_ID: {PEOPLE[LEADER]},
}


class FakeAccess:
    """Same shape as ChannelAccess: a guild_id and can_read_history()."""

    def __init__(
        self,
        readable: dict[int, set[int]] | None = None,
        guild_id: int = GUILD_ID,
        unavailable: bool = False,
    ) -> None:
        self.guild_id = guild_id
        self.readable = {int(c): {int(u) for u in users} for c, users in (readable or DEFAULT_READABLE).items()}
        self.unavailable = unavailable

    async def can_read_history(self, member_id: int, channel_id: int) -> bool:
        if self.unavailable:
            raise AccessUnavailable("（測試）假裝 Discord 無法確認權限")
        return int(member_id) in self.readable.get(int(channel_id), set())
