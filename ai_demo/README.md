# ai_demo — 會議之後的 AI 功能（測試用）

> **測試用。** 這是 AI 組正式版出來前的示範，照 `spec.md` v1.1 的規則寫。它直接讀本機資料庫、**不檢查 Discord 權限**，結果只印在終端機，不要直接貼給別人。

這是一個獨立的單元：讀 bot 的 SQLite（語音錄音和文字會議都可以），用 AI 做 spec 裡會議之後的事。AI 預設用這台電腦已登入的 Claude Code，和摘要一樣。

```
SQLite（唯讀）──▶ local_data.py ──▶ tasks.py：整理正式任務／待確認提案
                                 └▶ ask.py：問這場會議的問題
                      AI 來源：engine.py（claude-code／claude／openai／自訂）
```

## 怎麼用

在 repo 根目錄執行：

```bash
voice_stt/.venv/Scripts/python.exe -m ai_demo list
```

```bash
voice_stt/.venv/Scripts/python.exe -m ai_demo show <會議ID>
```

```bash
voice_stt/.venv/Scripts/python.exe -m ai_demo tasks <會議ID> --leader <組長的 Discord ID>
```

```bash
voice_stt/.venv/Scripts/python.exe -m ai_demo ask <會議ID> "誰負責期中考出題？"
```

| 選項 | 說明 |
|---|---|
| `--ai` | AI 來源：`claude-code`（預設）、`claude`、`openai`，或 `模組路徑:類別名稱`；也可以設環境變數 `AI_DEMO_ENGINE` |
| `--db` | 資料庫，預設 `discord_bot/data/messages.sqlite3` |
| `--json` | 印出原始結果，欄位名稱照 spec |
| `--leader` | 組長的 Discord ID。文字會議預設是下 `/meeting start` 的人；語音沒給的話，照 spec 全部只會是提案 |

會議 ID：語音是 `rec-…`，文字會議是 `mtg-…`。用 `list` 可以看到全部。

## 照 spec 做了什麼

**整理任務**（`tasks`，對應 spec R05–R07、R11、「會議與任務建立」）

- AI 只能提案，要不要算**正式任務**由程式檢查。正式任務要同時符合四個條件：
  1. 組長明確指派，而且依據裡有組長自己說的話
  2. 認得出負責人是會議裡的誰
  3. 有能換成確定時間的期限，存成 UTC
  4. 有依據，而且依據不全是「可能聽錯」的句子
- 少任何一項就是**待確認提案**，狀態是 `needs_clarification`，會附上缺什麼和要問組長的問題。
- 依據對不上任何一句的項目會直接丟掉，不讓 AI 編造來源。
- 正式任務的欄位照 spec：`owner_user_id`、`collaborators`、`due_at`、`status: not_started`、`source_refs`。

**問問題**（`ask`，對應 spec R03、R15）

- 只根據那一場會議的內容回答，並附上依據的句子。
- 找不到答案、或答案對不上任何一句時，回傳 spec 的 `NOT_FOUND`。

**用 Demo_Script 試的結果**（30 句，A 是組長，Claude Code 約 30 秒）：正式任務 0 項、待確認提案 12 項。原因是劇本裡的分工大多沒有講期限；「C 下週五前完成第一份小考」雖然有期限，但這句是 C 自己說的，不是組長指派。這和 spec 問題 D2 的預期一致。

## 和正式版的差別（AI 組要補的）

| 這裡 | 正式版要做 |
|---|---|
| 直接讀資料庫 | 透過讀取介面，先確認提問的人看得到來源頻道（R15） |
| 沒檢查負責人能不能讀這個頻道 | 負責人沒有權限時，`activation_state` 要是 `awaiting_leader_decision`（R18） |
| 結果印在終端機 | 用私訊或原頻道發布，發送前再驗一次權限（R10、R16） |
| 提案不會存起來 | 存成 `PendingAction`，等組長確認後才建立任務（ConfirmationPolicy） |
| 文字會議沒存原文時，用摘要的項目代替 | 有開文字記錄就讀原文 |

## 測試

```bash
cd ai_demo
../voice_stt/.venv/Scripts/python.exe -m pytest
```

測試用暫時的資料庫和假 AI，不會送出任何東西。
