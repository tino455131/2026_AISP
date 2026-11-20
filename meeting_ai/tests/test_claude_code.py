"""ClaudeCodeSummarizer is tested with a fake `claude -p`: nothing is sent anywhere."""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from meeting_ai import MeetingLine, SummaryError, get_summarizer
from meeting_ai import claude_code
from meeting_ai.claude_code import ClaudeCodeSummarizer

LINES = [
    MeetingLine(1, "S1", "2026-11-20T06:00:01+00:00", "我們決定下週一 merge"),
    MeetingLine(2, "S2", "2026-11-20T06:00:05+00:00", "我週五前把測試寫完"),
    MeetingLine(3, "S1", "2026-11-20T06:00:09+00:00", "好 那就這樣", uncertain=True),
]
REPLY = {
    "summary": "討論 merge 時間與測試分工。",
    "decisions": [{"text": "下週一 merge", "source_line_ids": [1, 99]}],  # 99 does not exist
    "action_items": [{"task": "寫測試", "owner": "S2（皓元）", "due": "週五前", "source_line_ids": [2]}],
}


class FakeClaudeCode:
    def __init__(self, output):
        self.output, self.calls = output, []

    def __call__(self, args, stdin_text, cwd):
        self.calls.append({"args": args, "stdin": stdin_text, "cwd_files": os.listdir(cwd)})
        return json.dumps(self.output, ensure_ascii=False)


def ok(structured=None, result=""):
    return {"type": "result", "subtype": "success", "is_error": False, "result": result, "structured_output": structured}


def test_transcript_goes_in_through_stdin_with_no_tools_and_nothing_saved():
    fake = FakeClaudeCode(ok(REPLY))
    summary = ClaudeCodeSummarizer(run=fake, claude_path="claude").summarize(LINES, {"S1": "ping", "S2": "皓元"})

    call = fake.calls[0]
    assert call["cwd_files"] == []  # runs in an empty folder: no project files to read
    assert "[2] S2（皓元）：我週五前把測試寫完" in call["stdin"]
    assert "（可能聽錯）" in call["stdin"]
    args = call["args"]
    assert args[args.index("--tools") + 1] == ""
    for flag in ("--strict-mcp-config", "--no-session-persistence", "--json-schema", "--system-prompt"):
        assert flag in args
    assert args[args.index("--permission-prompts") + 1] == "none"

    assert summary.decisions[0].source_line_ids == (1,)  # invented line 99 dropped
    assert summary.action_items[0].owner == "S2"  # "S2（皓元）" trimmed so it becomes a mention


def test_json_written_as_text_is_accepted():
    fenced = "```json\n" + json.dumps(REPLY, ensure_ascii=False) + "\n```"
    summary = ClaudeCodeSummarizer(run=FakeClaudeCode(ok(None, fenced)), claude_path="claude").summarize(LINES, {})
    assert summary.summary.startswith("討論")


@pytest.mark.parametrize(
    "output",
    [
        {"type": "result", "subtype": "error_max_turns", "is_error": True, "result": ""},
        ok(None, "抱歉，我無法整理"),
    ],
)
def test_errors_become_summary_errors(output):
    with pytest.raises(SummaryError):
        ClaudeCodeSummarizer(run=FakeClaudeCode(output), claude_path="claude").summarize(LINES, {})


def test_missing_claude_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(claude_code.shutil, "which", lambda name: None)
    with pytest.raises(SummaryError, match="找不到 claude"):
        ClaudeCodeSummarizer(run=FakeClaudeCode(ok(REPLY))).summarize(LINES, {})


def test_never_bills_an_api_key_by_accident(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen["env"] = kwargs["env"]
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setattr(claude_code.subprocess, "run", fake_run)
    claude_code._run_claude(["claude"], "", str(Path.cwd()))
    assert "ANTHROPIC_API_KEY" not in seen["env"]


def test_picked_by_name():
    assert isinstance(get_summarizer("claude-code"), ClaudeCodeSummarizer)
