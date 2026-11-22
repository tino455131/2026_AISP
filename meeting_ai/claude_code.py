"""ClaudeCodeSummarizer：把逐字稿交給這台電腦上的 Claude Code（`claude -p`）整理。

和 ClaudeSummarizer（Claude API）的差別：不需要 API key，用的是主機上 Claude Code 已登入的帳號
（例如 Pro／Max 訂閱），所以算在那個帳號的用量裡。這適合目前的測試；Anthropic 的規定是給別人用的
產品要用 API key，正式上線請改用 ClaudeSummarizer（MEETING_SUMMARIZER=claude）。

每次摘要都會新開一次 `claude -p`，做完就結束，沒有常駐程式；不摘要的時候不會用到任何額度。
為了不讓它碰到別的東西：
- 在一個空的暫存資料夾裡執行，不讀專案檔案
- 關掉所有工具（--tools ""）與 MCP（--strict-mcp-config），沒辦法讀檔或執行指令
- 不把這次對話存到硬碟（--no-session-persistence），會議內容不會留在 ~/.claude
- 會跳出權限詢問的動作一律拒絕（--permission-prompts none）

提示詞、輸出格式和解析都在 llm.py，跟其他來源共用；這裡只負責執行 claude -p。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from typing import Callable

from .interface import SummaryError
from .llm import LLMSummarizer

MODEL = os.environ.get("MEETING_SUMMARY_CC_MODEL", "").strip()  # empty: Claude Code's own default
TIMEOUT_SECONDS = 600

# run(args, stdin_text, cwd) -> stdout text. Tests pass a fake.
Runner = Callable[[list[str], str, str], str]


def _run_claude(args: list[str], stdin_text: str, cwd: str) -> str:
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)  # use the logged-in account, never bill an API key by accident
    try:
        done = subprocess.run(
            args,
            input=stdin_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            env=env,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise SummaryError(f"Claude Code 超過 {TIMEOUT_SECONDS} 秒沒有回應") from exc
    if done.returncode != 0 and not done.stdout.strip():
        tail = (done.stderr or "").strip().splitlines()[-1:] or ["（沒有訊息）"]
        raise SummaryError(f"Claude Code 執行失敗（結束碼 {done.returncode}）：{tail[0]}")
    return done.stdout


def _parse(stdout: str) -> dict | str:
    """Take the answer out of claude's JSON envelope: the structured output, or the plain text."""
    try:
        out = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise SummaryError("Claude Code 的輸出不是 JSON") from exc
    if out.get("is_error") or out.get("subtype") not in (None, "success"):
        raise SummaryError(f"Claude Code 回報錯誤：{str(out.get('result') or out.get('subtype'))[:200]}")
    data = out.get("structured_output")
    return data if isinstance(data, dict) else str(out.get("result", ""))  # text is parsed by llm.py


class ClaudeCodeSummarizer(LLMSummarizer):
    name = f"claude-code:{MODEL}" if MODEL else "claude-code"

    def __init__(self, run: Runner | None = None, claude_path: str | None = None) -> None:
        self._run = run or _run_claude
        self._claude = claude_path

    def _command(self, system_prompt: str, schema: dict) -> list[str]:
        claude = self._claude or shutil.which("claude")
        if not claude:
            raise SummaryError("找不到 claude 指令：請先在這台電腦安裝並登入 Claude Code")
        args = [
            claude,
            "-p",
            "請依照系統指示處理標準輸入的內容，並照指定的 JSON 格式回覆。",
            "--output-format", "json",
            "--json-schema", json.dumps(schema, ensure_ascii=False),
            "--system-prompt", system_prompt,
            "--tools", "",
            "--strict-mcp-config",
            "--no-session-persistence",
            "--permission-prompts", "none",
            "--effort", "medium",
        ]
        if MODEL:
            args += ["--model", MODEL]
        return args

    def generate(self, system_prompt: str, transcript: str, schema: dict) -> dict | str:
        command = self._command(system_prompt, schema)
        with tempfile.TemporaryDirectory(prefix="meeting-summary-") as empty_dir:
            stdout = self._run(command, transcript, empty_dir)
        return _parse(stdout)
