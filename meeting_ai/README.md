# meeting_ai — 會議摘要（可替換的介面）

> **給 AI 組（Alex、claire）**：這裡的實作是 Ping3227 為了測試整條語音流程先放的。
> 之後照下面的介面 `MeetingSummarizer` 換成你們自己的版本。

## 在流程中的位置

```
/record stop → voice_stt 轉文字存進資料庫 → meeting_ai 整理摘要 → 存進 voice_session_summaries
按「查看摘要」→ show_session 透過 AuthorizedTranscriptReader 讀 → 只給按的人看
```

voice_bot 會執行 `python -m meeting_ai.summarize_session <session_id>`（在 repo 根目錄、用 voice_stt 的 venv）。

## 介面

```python
class MeetingSummarizer(Protocol):
    name: str              # 存進資料庫的 model 欄位
    prompt_version: str    # 改 prompt 或規則時更新，舊摘要才知道要重做
    def summarize(self, lines: Sequence[MeetingLine], speakers: Mapping[str, str]) -> MeetingSummary: ...
```

**輸入**

- `MeetingLine`：`line_id`（來源行號）、`speaker`（`S1`、`S2`…）、`started_at`、`text`、`uncertain`（可能聽錯）
- `speakers`：`{"S1": "組長", ...}`，有顯示名稱才會有

**輸出** `MeetingSummary`

- `summary`
- `decisions`：`text`、`source_line_ids`
- `action_items`：`task`、`owner`、`due`、`source_line_ids`
  - `owner` 用 `S1` 這種代號，貼到 Discord 時會自動換成 @提及（不會發通知）
  - 負責人或期限不明時填空字串，不要猜

## 內建的兩個實作

| 名稱 | 檔案 | 說明 |
|---|---|---|
| `simple`（預設） | `simple.py` | 關鍵字規則，不用 API，結果粗糙，只為了測試流程 |
| `claude` | `claude.py` | 呼叫 Claude（`claude-opus-5-5`），用 JSON schema 固定輸出格式；需要 `pip install anthropic` 和 API key |

切換：設定環境變數 `MEETING_SUMMARIZER=simple|claude`。

## 換成你們自己的版本

1. 新增一個 class，例如 `meeting_ai/team.py` 裡的 `TeamSummarizer`，有 `name`、`prompt_version`、`summarize()`。
2. 在 `interface.py` 的 `get_summarizer()` 加一行 `if kind == "team": ...`。
3. 用 `MEETING_SUMMARIZER=team` 執行。

不用改 voice_bot、voice_stt，也不用改資料庫。

## 規則（請保留）

- 每個決定、每項待辦都要附 `source_line_ids`，對應 Spec「任務草案要有來源依據」。
  不存在的行號會被 `MeetingSummary.from_dict(valid_ids=...)` 自動濾掉。
- `uncertain=True` 的句子可能聽錯，不要單憑它就產生決定或待辦。
- 摘要不主動貼出來，只存進資料庫；要讀一律透過 `AuthorizedTranscriptReader`，誰能讀和逐字稿一樣。要貼到頻道或私訊時，要先做聽眾檢查（見 [docs/ai_memory_api.md](../docs/ai_memory_api.md) 第 5 節）。

## 讀取的範例：`show_session.py`

voice_bot 的「查看摘要」「查看逐字稿」按鈕會執行它，也可以當作 AI 組使用讀取介面的範例：

```python
reader = AuthorizedTranscriptReader(ChannelAccess(client, guild_id), TranscriptStore(db))
lines = await reader.transcript_for(member_id, session_id)   # 沒權限 → AccessDenied
view = await reader.summary_for(member_id, session_id)       # 沒摘要 → None
```

手動試（要用 `discord_bot/.venv`，因為需要 discord.py；會用 voice_bot 的 token 連上 Discord 幾秒）：

```bash
discord_bot/.venv/Scripts/python.exe -m meeting_ai.show_session <session_id> --member <Discord ID> --guild-id <伺服器ID> --what summary
```

回傳 `{"ok": true, "text": ...}`，或 `{"ok": false, "reason": "denied" | "unavailable" | "not_found" | "no_summary"}`。

## 測試

```bash
cd meeting_ai
../voice_stt/.venv/Scripts/python.exe -m pytest
```

8 項測試；Claude 版本用假的 client 測，不會真的呼叫 API。
`show_session` 的 6 項測試需要 discord.py，在上面的環境會跳過，請另外跑：

```bash
discord_bot/.venv/Scripts/python.exe -m unittest meeting_ai.tests.test_show_session -v   # 在 repo 根目錄
```

手動試一場已存的會議：

```bash
voice_stt/.venv/Scripts/python.exe -m meeting_ai.summarize_session <session_id> --db 資料庫路徑
```
