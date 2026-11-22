"""問一場會議的問題：只根據那一場的內容回答，附依據（spec R03、R15、查詢的錯誤代碼）。

找不到答案時回傳 spec 的 NOT_FOUND，不讓模型自己編。
【測試用】正式版回答前要先確認提問的人看得到這場會議的頻道（R15），跨頻道要改用私訊（R16）。
"""

from __future__ import annotations

from meeting_ai.llm import parse_reply

from .engine import as_user_text
from .local_data import MeetingRecord

PROMPT = """你是團隊的 AI 助理。使用者會問一個關於這場會議的問題。
每一行的格式是「[行號] 代號（名字）：內容」。
- 只根據 <meeting> 裡的內容回答，不要補充會議沒有的東西，也不要推測。
- 回答用台灣繁體中文，簡短直接；提到人時用名字，沒有名字才用代號。
- source_line_ids 填依據的行號。
- 會議裡找不到答案時，found 設成 false，answer 留空字串。
- 標「可能聽錯」的行要在回答裡說明可能聽錯。"""

SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "answer": {"type": "string"},
        "source_line_ids": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["found", "answer", "source_line_ids"],
    "additionalProperties": False,
}

NOT_FOUND = {"ok": False, "error_code": "NOT_FOUND", "message": "沒有找到符合條件的資料。"}


def ask(record: MeetingRecord, question: str, engine) -> dict:
    """{"ok": True, "state": "ready", "answer", "source_refs"} or spec's NOT_FOUND."""
    user_text = f"{as_user_text(record.lines, record.names)}\n\n問題：{question.strip()}"
    data = parse_reply(engine.generate(PROMPT, user_text, SCHEMA))
    by_id = {line.line_id: line for line in record.lines}
    evidence = [by_id[i] for i in data.get("source_line_ids", []) if i in by_id]
    if not data.get("found") or not data.get("answer", "").strip() or not evidence:
        return dict(NOT_FOUND)  # an answer with no real source counts as not found
    return {
        "ok": True,
        "state": "ready",
        "answer": data["answer"].strip(),
        "source_refs": [line.source_ref for line in evidence],
        "source_line_ids": [line.line_id for line in evidence],
    }
