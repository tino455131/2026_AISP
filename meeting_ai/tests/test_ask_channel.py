"""Offline coverage for /ask routing, tools, and Discord-scoped storage."""

import asyncio
import json
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from meeting_ai import ask_channel
from meeting_ai.tools import HISTORY_TOOL_NAME, ToolContext
from sqlite_api import SQLiteStore


def routing(route, answer=""):
    return SimpleNamespace(status="completed", output_text=json.dumps({"route": route, "answer": answer}))


def tool_call(name=HISTORY_TOOL_NAME, arguments="{}", call_id="call_123"):
    payload = {"type": "function_call", "name": name, "arguments": arguments, "call_id": call_id}
    item = SimpleNamespace(**payload, model_dump=lambda **_: payload)
    return SimpleNamespace(status="completed", output=[item])


def reply(text):
    return SimpleNamespace(status="completed", output=[], output_text=text)


def client_with(*responses):
    return SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=responses)))


class ChannelAskTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.read = AsyncMock(return_value=[])
        self.context = ToolContext(self.read)

    async def test_open_questions_use_the_first_answer_without_exposing_tools_or_history(self):
        client = client_with(routing("general", "async 用於定義非同步函式"))
        result = await ask_channel.ask_question(client, "fake", "解釋 Python 的 async", self.context)
        self.assertEqual(result, {"ok": True, "text": "async 用於定義非同步函式", "used_channel_history": False})
        self.read.assert_not_awaited()
        client.responses.create.assert_awaited_once()
        self.assertNotIn("tools", client.responses.create.call_args.kwargs)

    async def test_current_channel_forces_a_tool_and_returns_matching_call_id(self):
        self.read.return_value = [
            {"message_id": 1, "author_id": 3, "created_at": "2026-11-21", "content": "乙" * 4000},
            {"message_id": 2, "author_id": 3, "created_at": "2026-11-22", "content": "甲" * 9000},
        ]
        client = client_with(routing("current_channel"), tool_call(), reply("我們決定星期五開會"))
        result = await ask_channel.ask_question(client, "fake", "我們剛才決定了什麼？", self.context)
        self.assertTrue(result["used_channel_history"])
        self.assertEqual(result["text"], "我們決定星期五開會")
        self.read.assert_awaited_once()
        _, forced, final = [call.kwargs for call in client.responses.create.await_args_list]
        self.assertEqual(forced["tool_choice"], {"type": "function", "name": HISTORY_TOOL_NAME})
        output = final["input"][-1]
        self.assertEqual(output["call_id"], "call_123")
        messages = json.loads(output["output"])
        self.assertEqual([row["message_id"] for row in messages["messages"]], ["1", "2"])
        self.assertEqual([len(row["content"]) for row in messages["messages"]], [3000, 9000])
        self.assertTrue(messages["truncated"])

    async def test_empty_history_and_other_channel_do_not_produce_a_model_summary(self):
        empty = client_with(routing("current_channel"), tool_call())
        self.assertEqual(
            await ask_channel.ask_question(empty, "fake", "這個頻道", self.context),
            {"ok": False, "error_code": "NO_HISTORY"},
        )
        self.assertEqual(empty.responses.create.await_count, 2)
        self.read.reset_mock()
        other = client_with(routing("other_channel", "ignored"))
        self.assertEqual(
            await ask_channel.ask_question(other, "fake", "整理隔壁頻道", self.context),
            {"ok": False, "error_code": "OUTSIDE_CHANNEL"},
        )
        self.read.assert_not_awaited()

    async def test_invalid_tools_or_arguments_cannot_read_history(self):
        for item in (tool_call("another_tool"), tool_call(arguments='{"channel_id":"999"}')):
            client = client_with(routing("current_channel"), item)
            result = await ask_channel.ask_question(client, "fake", "摘要", self.context)
            self.assertEqual(result, {"ok": False, "error_code": "UPSTREAM_UNAVAILABLE"})
        self.read.assert_not_awaited()

    async def test_tool_execution_and_deadline_are_bounded(self):
        self.read.return_value = [{"message_id": 1, "author_id": 2, "created_at": "2026-11-22", "content": "測試"}]
        client = client_with(routing("current_channel"), *(tool_call(call_id=f"call_{i}") for i in range(4)))
        result = await ask_channel.ask_question(client, "fake", "摘要", self.context)
        self.assertEqual(result, {"ok": False, "error_code": "UPSTREAM_UNAVAILABLE"})
        self.assertEqual(self.read.await_count, 3)
        self.assertEqual(client.responses.create.await_args.kwargs["tool_choice"], "none")
        with patch.object(ask_channel, "ASK_TIMEOUT", 0):
            async def slow(**_):
                await asyncio.sleep(1)

            client.responses.create.side_effect = slow
            result = await ask_channel.ask_question(client, "fake", "摘要", self.context)
        self.assertEqual(result, {"ok": False, "error_code": "TIMED_OUT"})

    async def test_sqlite_history_is_scoped_and_handle_permissions_before_model_receives_it(self):
        @asynccontextmanager
        async def discord_session(_token):
            yield object()

        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "ask.sqlite3"
            store = SQLiteStore(db)
            at = "2026-11-22T00:00:00Z"
            store.save_message(1, 10, 20, 30, "本頻道", at)
            store.save_message(2, 10, 21, 30, "其他頻道", at)
            store.save_message(3, 11, 20, 30, "其他伺服器", at)
            access = SimpleNamespace(
                guild_id=10, can_read_bot_history=AsyncMock(return_value=True),
                can_read_history=AsyncMock(return_value=True),
            )
            with (
                patch.dict("os.environ", {"VOICE_BOT_TOKEN": "test"}),
                patch.object(ask_channel, "ready_discord_client", discord_session),
                patch.object(ask_channel, "ChannelAccess", return_value=access),
            ):
                async def read():
                    return await ask_channel.read_channel_history(db, 10, 30, 20)

                self.assertEqual([row["content"] for row in await read()], ["本頻道"])
                access.can_read_history.assert_awaited_once_with(30, 20)

                for bot_ok, user_ok, code in [
                    (False, True, "SOURCE_UNAVAILABLE_BOT"),
                    (True, False, "ACCESS_DENIED_USER"),
                    (True, ask_channel.AccessUnavailable("Discord unavailable"), "PERMISSION_UNVERIFIED"),
                ]:
                    access.can_read_bot_history.return_value = bot_ok
                    if isinstance(user_ok, Exception):
                        access.can_read_history.side_effect = user_ok
                    else:
                        access.can_read_history.side_effect = None
                        access.can_read_history.return_value = user_ok
                    client = client_with(routing("current_channel"), tool_call())
                    result = await ask_channel.ask_question(client, "fake", "摘要", ToolContext(read))
                    self.assertEqual(result, {"ok": False, "error_code": code})
                    self.assertEqual(client.responses.create.await_count, 2)
