"""從一場會議整理任務：正式任務和待確認提案分開（spec R05–R07、R11、「會議與任務建立」）。

AI 只能提案；要不要算正式任務，由這裡的程式檢查決定（spec：後端驗證來源作者、TaskOwner 身分、
時間、必要欄位與對應證據；AI 說是明確指派不能取代驗證）。正式任務必須同時符合：
1. 組長（TeamLeader）明確指派，而且依據裡有組長自己說的話
2. 負責人是會議裡認得出來的人（spec：同名對象無法辨識要追問）
3. 有明確期限，能換成確定的時間（存成 UTC RFC 3339）
4. 有依據，而且依據不全是「可能聽錯」的句子
少任何一項就是待確認提案，附上缺什麼和要問組長的問題。

【測試用】離線執行，沒有檢查負責人能不能讀這個頻道；正式版要照 spec R18，
負責人沒有來源權限時 activation_state 要是 awaiting_leader_decision。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from meeting_ai.llm import parse_reply

from .engine import as_user_text
from .local_data import MeetingRecord

PROMPT = """你是團隊的 AI 助理（spec 裡的 AIAssistant），要從會議內容整理「任務候選」。你只能提案，不能決定。
每一行的格式是「[行號] 代號（名字）：內容」。組長（TeamLeader）的代號是 {leader}。
會議日期是 {date}，時區 {tz}。

找出會議中「有人要去做某件事」的地方，每一件列一個 item：
- title：要做的事（簡短）；description：補充說明，沒有就空字串
- owner_label：負責人的代號，只能填會議裡出現的代號；不確定就留空字串，不要猜
- collaborator_labels：協作者的代號，沒有就空陣列
- assigned_by_label：提出這項分工的人的代號
- explicit_assignment：只有「組長明確指定某人負責某事」才是 true；提議、疑問、否定句、「要不要讓某人做」都是 false
- due_text：期限的原話，沒有就空字串
- due_at：期限換成含時區的 ISO 8601 時間（例如 2026-11-27T23:59:00+08:00）；沒有期限或無法唯一解讀就空字串
- question：資訊不夠時（缺負責人、缺期限、看不出是誰）要問組長的一句話；資訊足夠就空字串
- source_line_ids：依據的行號

規則：只根據會議內容；不推定完成、不編百分比；標「可能聽錯」的行不能是唯一依據；全部用台灣繁體中文。"""

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "owner_label": {"type": "string"},
                    "collaborator_labels": {"type": "array", "items": {"type": "string"}},
                    "assigned_by_label": {"type": "string"},
                    "explicit_assignment": {"type": "boolean"},
                    "due_text": {"type": "string"},
                    "due_at": {"type": "string"},
                    "question": {"type": "string"},
                    "source_line_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": [
                    "title", "description", "owner_label", "collaborator_labels", "assigned_by_label",
                    "explicit_assignment", "due_text", "due_at", "question", "source_line_ids",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def _zone(tz: str):
    """Windows Python often has no time zone database (pip install tzdata); Taiwan is always +08:00."""
    try:
        return ZoneInfo(tz)
    except ZoneInfoNotFoundError:
        if tz == "Asia/Taipei":
            return timezone(timedelta(hours=8), "Asia/Taipei")
        raise ValueError(f"找不到時區 {tz}：請在這個 Python 環境執行 pip install tzdata") from None


def _utc(text: str) -> str | None:
    """An ISO time with a time zone -> UTC RFC 3339; anything else -> None (no guessing)."""
    try:
        moment = datetime.fromisoformat(text.strip())
    except (ValueError, AttributeError):
        return None
    if moment.tzinfo is None:
        return None
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def propose_tasks(record: MeetingRecord, leader_user_id: int | None, engine, tz: str = "Asia/Taipei") -> dict:
    """{"tasks": [Task…], "proposals": [PendingAction…], "rejected": n} with spec field names."""
    leader_label = record.label_of(leader_user_id) if leader_user_id is not None else None
    started = datetime.fromisoformat(record.started_at.replace("Z", "+00:00")) if record.started_at else None
    date = started.astimezone(_zone(tz)).strftime("%Y-%m-%d（%a）") if started else "不明"
    system = PROMPT.format(leader=leader_label or "（組長沒有在這場發言）", date=date, tz=tz)
    data = parse_reply(engine.generate(system, as_user_text(record.lines, record.names), SCHEMA))

    by_id = {line.line_id: line for line in record.lines}
    tasks, proposals, rejected = [], [], 0
    for item in data.get("items", []):
        evidence = [by_id[i] for i in item.get("source_line_ids", []) if i in by_id]
        if not evidence:
            rejected += 1  # spec: a task needs its source; invented or missing evidence is dropped
            continue
        owner = record.speakers.get(item.get("owner_label", ""))
        collaborators = [
            record.speakers[label] for label in item.get("collaborator_labels", [])
            if label in record.speakers and record.speakers[label] != owner
        ]
        due_at = _utc(item.get("due_at", ""))
        missing = []
        explicit = (
            item.get("explicit_assignment") is True
            and leader_label is not None
            and item.get("assigned_by_label") == leader_label
            and any(line.speaker_label == leader_label for line in evidence)
        )
        if not explicit:
            missing.append("explicit_assignment")
        if owner is None:
            missing.append("owner_user_id")
        if due_at is None:
            missing.append("due_at")
        if all(line.uncertain for line in evidence):
            missing.append("reliable_evidence")

        task = {
            "title": item.get("title", "").strip(),
            "description": item.get("description", "").strip(),
            "owner_user_id": owner,
            "collaborators": collaborators,
            "due_at": due_at,
            "due_text": item.get("due_text", "").strip(),
            "source_refs": [line.source_ref for line in evidence],
        }
        if missing:
            proposals.append({
                "kind": "task_proposal",
                "state": "needs_clarification",
                "missing": missing,
                "question": item.get("question", "").strip() or "請組長確認負責人和期限。",
                "payload": task,
            })
        else:
            tasks.append({**task, "status": "not_started", "activation_state": "active"})
    return {"tasks": tasks, "proposals": proposals, "rejected": rejected}
