# meeting_ai — 會議摘要（可替換的介面）

> **給 AI 組（Alex、claire）**：這裡的實作是 Ping3227 為了測試整條語音流程先放的。
> 之後照下面的介面 `MeetingSummarizer` 換成你們自己的版本。

## 在流程中的位置

```
/record stop → voice_stt 轉文字存進資料庫 → meeting_ai 整理摘要 → 存進 voice_session_summaries
按「查看摘要」→ show_session 透過 AuthorizedTranscriptReader 讀 → 只給按的人看
```

voice_bot 會執行 `python -m meeting_ai.summarize_session <session_id>`（在 repo 根目錄、用 voice_stt 的 venv）。

文字會議（`/meeting end`）也用同一個摘要器：voice_bot 把那段訊息以 JSON 交給 `python -m meeting_ai.summarize_text_meeting`，結果存進 `text_meetings` 表（`text_meeting_store.py`）。每則訊息是一行，作者一樣標成 S1、S2，所以兩種會議的摘要格式相同。

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

## 內建的實作

| 名稱 | 檔案 | 說明 |
|---|---|---|
| `simple`（預設） | `simple.py` | 關鍵字規則，不用 API，結果粗糙，只為了測試流程 |
| `claude` | `claude.py` | 呼叫 Claude API（預設 `claude-opus-5-5`，`MEETING_SUMMARY_MODEL` 可換），用 JSON schema 固定輸出格式；需要 API key，`voice_stt/.venv` 已裝好 `anthropic` |
| `claude-code` | `claude_code.py` | 交給主機上已登入的 Claude Code（`claude -p`），不用 API key，算在那個帳號的訂閱額度 |
| `openai` | `openai_summarizer.py` | ChatGPT（OpenAI）API，預設模型 `gpt-4.1-mini`（`MEETING_SUMMARY_OPENAI_MODEL` 可換）。**預設沒開**：要 `pip install openai` 和 `OPENAI_API_KEY` |

切換：設定環境變數 `MEETING_SUMMARIZER=simple|claude|claude-code|openai`（voice_bot 讀 `voice_bot/.env`），或 voice_bot 啟動時加 `--summarizer openai`。

**換到別台電腦用 ChatGPT**：`voice_stt/.venv/Scripts/pip install openai` → 在 `voice_bot/.env` 填 `OPENAI_API_KEY=...` → 啟動時加 `--summarizer openai`（或把 `.env` 改成 `MEETING_SUMMARIZER=openai`）。

`claude` 和 `claude-code` 都是 `llm.py` 裡 `LLMSummarizer` 的子類別：提示詞、輸出格式、逐字稿排法、回覆解析和檢查都共用，各自只寫「怎麼呼叫模型」那一個方法。所以兩個的摘要格式完全一樣，切換只要改一行設定。

**從 claude-code 換成 Claude API**：在 `voice_bot/.env` 改成 `MEETING_SUMMARIZER=claude`，再加上 `ANTHROPIC_API_KEY=...`，重開 bot。

**`claude-code` 怎麼運作**：每次摘要新開一次 `claude -p`，做完就結束，不摘要時不佔用任何額度（一場短會議約 7 秒）。為了安全：

- 在空的暫存資料夾執行
- 關掉所有工具和 MCP，不能讀檔、不能執行指令
- 不把對話存到硬碟
- 不會用到 `ANTHROPIC_API_KEY`

注意：Anthropic 規定給別人用的產品要用 API key，不能用個人訂閱，所以 `claude-code` 只適合測試，正式上線請改用 `claude`。執行的主機也要先裝好並登入 Claude Code。

## 換成其他來源（不用改 meeting_ai 的檔案）

**只想換模型**（例如 OpenAI、Gemini、本機模型）：繼承 `LLMSummarizer`，只寫 `generate()`。提示詞、格式和檢查都沿用。

```python
# 例如放在 repo 根目錄的 my_summarizers/other_model.py
from meeting_ai.llm import LLMSummarizer

class OtherModelSummarizer(LLMSummarizer):
    name = "other-model"  # 會跟摘要一起存進資料庫

    def generate(self, system_prompt, transcript, schema):
        # system_prompt 當系統指示、transcript 當使用者訊息，要求模型回傳符合 schema 的 JSON。
        # 回傳 JSON 字串或 dict 都可以；失敗時 raise meeting_ai.SummaryError。
        ...
```

**整套自己做**（AI 組自己的提示詞或流程）：任何有 `name`、`prompt_version`、`summarize(lines, speakers)` 的類別都可以，回傳 `MeetingSummary`。

接上去：在 `voice_bot/.env` 設

```
MEETING_SUMMARIZER=my_summarizers.other_model:OtherModelSummarizer
MEETING_SUMMARY_SENDS_TO=OpenAI 的 GPT
```

- 模組路徑從 repo 根目錄算起。
- `MEETING_SUMMARY_SENDS_TO` 是錄音通知裡「逐字稿會交給誰整理」的名稱。在這台電腦上跑的模型填 `none`。

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

回傳 `{"ok": true, "text": ...}`，或 `{"ok": false, "error_code": ..., "message": ...}`。錯誤代碼照 `spec.md`：

| `error_code` | 什麼時候 |
|---|---|
| `ACCESS_DENIED_USER` | 這個人看不到那個語音頻道 |
| `PERMISSION_UNVERIFIED` | Discord 暫時無法確認權限（不會因此放行） |
| `NOT_FOUND` | 找不到這場錄音，或這場還沒有摘要（`message` 會說是哪一種） |

`message` 是給使用者看的繁體中文，不會透露對方看不到的頻道或內容。

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
