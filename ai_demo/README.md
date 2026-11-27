# ai_demo — 會議之後的 AI 功能（測試用）

> **測試用。** 終端機透過 `SQLiteStore` 查閱本機資料，適合使用 [AI 團隊指南](../docs/ai_team_guide.md)中的假資料。Discord 的 `/ai` 由 Bot 檢查來源頻道的權限。

這是一個獨立的單元：讀 bot 的 SQLite（語音錄音和文字會議都可以），用 AI 做 spec 裡會議之後的事。AI 來源可用 `AI_DEMO_ENGINE` 或 `--ai` 設定。

```
SQLite ──▶ SQLiteStore（唯讀）──▶ local_data.py ──▶ tasks.py：整理正式任務／待確認提案
                                 └▶ ask.py：問這場會議的問題
                      AI 來源：engine.py（claude-code／openai／自訂）
```

## 在 Discord 裡用：`/ai`

Discord 的 `/ai` 指令暫停註冊，以下保留流程說明。可從終端機繼續使用 AI demo。同一來源頻道的會議結果通過聽眾驗權才會公開。跨頻道結果與回報進度使用私人回覆。

| 指令 | 做什麼 |
|---|---|
| `/ai tasks meeting:<會議> [leader:<組長>]` | 整理正式任務和待確認提案 |
| `/ai ask meeting:<會議> question:<問題>` | 問這場會議的問題 |
| `/ai tracked` | 看追蹤中的任務和最新進度（只列你看得到的頻道） |

- `meeting` 打字就能搜尋，例如打「語音」或日期，只會列出你看得到的頻道裡的會議。
- `leader` 沒填時，用開會的人（`/meeting start`）或開始錄音的人（`/record start`）。自動錄音沒有開始的人，這時照 spec 全部只會是提案。
- 照 spec R15，bot 會先確認你看得到那場會議的頻道（檢視頻道＋讀取訊息歷史），才去讀資料。看不到就回「你沒有權限取得所要求的資訊」，確認不了就回「暫時無法確認你的權限」。
- 用 Claude Code 大約要 5～40 秒，期間會顯示「AI 正在讀…」。

流程：`Discord /ai` → voice_bot（`src/ai.js`）檢查權限 → `python -m ai_demo --bot …` 讀資料庫、問 AI → 依來源與聽眾權限交付結果。

文字會議表保存範圍、摘要和引用。Discord 的 `/ai` 會從來源頻道讀取原文，若回傳空清單，就以已保存的摘要回答。被 @ 的人即使沒說話也會有代號，所以「@某人 負責…」認得出負責人。

各功能讀哪些資料表，見 [docs/database_schema.md](../docs/database_schema.md)。AI 工具開發及假資料說明見 [docs/ai_team_guide.md](../docs/ai_team_guide.md)。

## 追蹤進度（測試）

`/ai tasks` 找到正式任務時，回覆下面會多一個「追蹤這 N 項正式任務的進度」按鈕：

1. **組長按下去，就是確認**這次顯示的那幾項（spec ConfirmationPolicy）。只有下指令的組長能按，按一次就失效；重送也不會重複建立任務。
2. **負責人看得到來源頻道** → bot 私訊問進度。私訊會附上 spec 規定的那句「本次提交的任務進度將分享給有來源權限的組長」，以及四個按鈕：還沒開始、進行中、卡住了、完成了。
3. **負責人看不到來源頻道** → 不私訊，任務標成 `awaiting_leader_decision`，等組長決定（R18）。
4. **私訊失敗**（對方關閉私訊）→ 記成 `delivery_failed`；Discord 沒有回應、不知道有沒有送到 → 記成 `delivery_unknown`，不重送。兩種都不改貼到公開頻道，也不算對方沒回（R10）。
5. **負責人按了進度** → 任務狀態更新，這次詢問結案。組長看得到來源頻道的話，bot 會私訊通知組長。只有負責人本人能回報（R07、R11）；回報「完成」後就不能再改，要重新開啟請找組長。

測試版只在確認時問一次，沒有排程提醒、追問、取消或改期限。資料存在 `demo_` 開頭的三張表，和 AI 組之後的正式表分開。

## 在終端機用

在 repo 根目錄執行：

```bash
voice_bot/voice_stt/.venv/Scripts/python.exe -m ai_demo list
```

```bash
voice_bot/voice_stt/.venv/Scripts/python.exe -m ai_demo show <會議ID>
```

```bash
voice_bot/voice_stt/.venv/Scripts/python.exe -m ai_demo tasks <會議ID> --leader <組長的 Discord ID>
```

```bash
voice_bot/voice_stt/.venv/Scripts/python.exe -m ai_demo ask <會議ID> "誰負責期中考出題？"
```

| 選項 | 說明 |
|---|---|
| `--ai` | AI 來源：`claude-code`、`openai`，或 `模組路徑:類別名稱`。沒給的話依序看 `AI_DEMO_ENGINE`、正在用的摘要器（`simple` 除外），最後才是 `claude-code`。所以 bot 啟動時加 `--summarizer openai`，`/ai` 也會跟著改用 ChatGPT |
| `--db` | 資料庫，預設是根目錄 `.env` 的 `BOT_DB`，沒填就是 `data/messages.sqlite3` |
| `--json` | 印出原始結果，欄位名稱照 spec |
| `--bot` | 給 voice_bot 呼叫：只印一行 `RESULT {json}`，Discord ID 用字串（數字太長，JavaScript 放不下） |
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

可用 [Demo 劇本](../Demo_Script.md)的假資料檢查候選與正式任務的差異。產生資料的方式見 [AI 團隊接手指南](../docs/ai_team_guide.md#1-準備環境與假資料)。

## 和正式版的差別（AI 組要補的）

| 這裡 | 正式版要做 |
|---|---|
| 終端機透過 `SQLiteStore` 讀取假資料 | Discord 使用者的查詢依[授權讀取介面](../docs/ai_memory_api.md)處理 |
| 確認追蹤後詢問一次進度 | 正式版需有排程、取消和改期流程 |
| 候選只保留在當次結果 | 需保存 `PendingAction`，讓組長確認後再建立任務 |

## 測試

```bash
cd ai_demo
../voice_bot/voice_stt/.venv/Scripts/python.exe -m pytest
```

測試用暫時的資料庫和假 AI，不會送出任何東西。
