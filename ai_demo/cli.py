"""【測試用】AI 功能示範：在 repo 根目錄執行

    voice_stt/.venv/Scripts/python.exe -m ai_demo list
    voice_stt/.venv/Scripts/python.exe -m ai_demo show <會議ID>
    voice_stt/.venv/Scripts/python.exe -m ai_demo tasks <會議ID> [--leader <組長的 Discord ID>]
    voice_stt/.venv/Scripts/python.exe -m ai_demo ask <會議ID> "問題"

共用選項：--db 資料庫、--ai claude-code|claude|openai|模組:類別、--json（印出原始結果）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .ask import ask
from .engine import get_engine
from .local_data import DEFAULT_DB, DEFAULT_RECORDINGS, LocalData
from .tasks import propose_tasks

BANNER = "【測試用】ai_demo：直接讀本機資料庫、不檢查 Discord 權限，結果不要直接貼給別人。"
MISSING = {
    "explicit_assignment": "不是組長明確指派",
    "owner_user_id": "看不出負責人是誰",
    "due_at": "沒有明確期限",
    "reliable_evidence": "依據都是可能聽錯的句子",
}


def _who(record, user_id) -> str:
    label = record.label_of(user_id) if user_id is not None else None
    return record.names.get(label, label) if label else "（未指定）"


def _print_tasks(record, result) -> None:
    print(f"\n正式任務（{len(result['tasks'])}）")
    for task in result["tasks"]:
        print(f"  ✅ {task['title']} — 負責：{_who(record, task['owner_user_id'])}，期限：{task['due_at']}（{task['due_text']}）")
    print(f"\n待確認提案（{len(result['proposals'])}）")
    for proposal in result["proposals"]:
        task = proposal["payload"]
        reasons = "、".join(MISSING.get(m, m) for m in proposal["missing"])
        print(f"  ❓ {task['title']} — 負責：{_who(record, task['owner_user_id'])}；{reasons}")
        print(f"     要問組長：{proposal['question']}")
    if result["rejected"]:
        print(f"\n（有 {result['rejected']} 項沒有可對照的依據，已丟掉）")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(prog="python -m ai_demo", description=BANNER)
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--recordings", default=str(DEFAULT_RECORDINGS), help="voice_bot 的錄音資料夾（拿顯示名稱）")
    p.add_argument("--ai", help="claude-code（預設）、claude、openai 或 模組:類別")
    p.add_argument("--json", action="store_true", help="印出原始結果")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="列出所有會議")
    show = sub.add_parser("show", help="看一場會議的內容")
    show.add_argument("meeting_id")
    tasks = sub.add_parser("tasks", help="整理正式任務和待確認提案")
    tasks.add_argument("meeting_id")
    tasks.add_argument("--leader", help="組長的 Discord ID（文字會議預設是開會的人）")
    tasks.add_argument("--tz", default="Asia/Taipei")
    question = sub.add_parser("ask", help="問這場會議的問題")
    question.add_argument("meeting_id")
    question.add_argument("question")
    args = p.parse_args(argv)

    print(BANNER, file=sys.stderr)
    data = LocalData(Path(args.db), Path(args.recordings))
    if args.command == "list":
        for m in data.meetings():
            kind = "語音" if m["kind"] == "voice" else "文字"
            print(f"{m['started_at'][:16]}  {kind}  {m['line_count']:>4} 句  {'有摘要' if m['has_summary'] else '無摘要'}  {m['meeting_id']}")
        return 0

    try:
        record = data.meeting(args.meeting_id)
    except LookupError:
        print(json.dumps({"ok": False, "error_code": "NOT_FOUND", "message": "沒有找到符合條件的資料。"}, ensure_ascii=False))
        return 1

    if args.command == "show":
        for line in record.lines:
            name = record.names.get(line.speaker_label, line.speaker_label)
            print(f"[{line.line_id}] {name}：{line.text}{' ⚠️' if line.uncertain else ''}")
        return 0

    engine = get_engine(args.ai)
    if args.command == "tasks":
        leader = int(args.leader) if args.leader else record.started_by
        if leader is None:
            print("沒有指定組長（--leader），照 spec 所有項目都只會是待確認提案。", file=sys.stderr)
        result = propose_tasks(record, leader, engine, args.tz)
        print(json.dumps(result, ensure_ascii=False, indent=2)) if args.json else _print_tasks(record, result)
        return 0

    result = ask(record, args.question, engine)
    if args.json or not result["ok"]:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{result['answer']}\n（依據：第 {'、'.join(map(str, result['source_line_ids']))} 句）")
    return 0 if result["ok"] else 1
