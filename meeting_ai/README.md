# meeting_ai — 會議摘要（可替換的介面）

> **給 AI 組（Alex、claire）**：這裡的實作是 Ping3227 為了測試整條語音流程先放的。
> 之後照下面的介面 `MeetingSummarizer` 換成你們自己的版本。

## 在流程中的位置

```
/record stop → voice_stt 轉文字存進資料庫 → meeting_ai 整理摘要 → 存進 voice_session_summaries
按「查看摘要」→ show_session 透過 AuthorizedTranscriptReader 讀 → 只給按的人看
```

voice_bot 會執行 `python -m meeting_ai.summarize_session <session_id>`（在 repo 根目錄、用 voice_stt 的 venv）。

文字會議（`/meeting end`）也用同一個摘要器：voice_bot 把那段訊息以 JSON 交給 `python -m meeting_ai.summarize_text_meeting`，結果透過 `sqlite_api` 的 `save_text_meeting()` 存進 `text_meetings` 表。每則訊息是一行，作者一樣標成 S1、S2，所以兩種會議的摘要格式相同。

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
| `openai` | `openai.py` | 呼叫 OpenAI（預設 `gpt-6-luna`），用 JSON schema 固定輸出格式；需要 `openai` 套件和 API key。提示詞、格式和解析和 `claude-code` 共用 `llm.py` |
| `claude-code` | `claude_code.py` | 交給這台電腦已登入的 Claude Code（`claude` 指令），不用 API key，算在該帳號的訂閱額度；測試用 |

由專案根目錄 .env 設定環境變數 `MEETING_SUMMARIZER=simple|openai|claude-code`，或 `模組路徑:類別名稱`（見下一節）。OpenAI 摘要器需要 `OPENAI_API_KEY`，可用 `MEETING_SUMMARY_MODEL` 覆蓋模型。舊的 `claude` 設定已移除，需改成 `openai`。
`voice_bot` 會使用 `voice_stt` 的 Python 環境執行摘要；在 repo 根目錄執行 `voice_bot/voice_stt/.venv/Scripts/python.exe -m pip install -r voice_bot/voice_stt/requirements.txt` 安裝相依套件。完整設定與其他平台指令見[根目錄 README](../README.md#從專案根目錄設定與啟動)。

## 換成你們自己的版本

1. 新增一個 class，例如 `meeting_ai/team.py` 裡的 `TeamSummarizer`，有 `name`、`prompt_version`、`summarize()`。
   只想換模型、提示詞和格式照舊的話，繼承 `llm.LLMSummarizer`，只實作 `generate()`（`claude_code.py` 就是這樣做的）。
2. 用 `MEETING_SUMMARIZER=meeting_ai.team:TeamSummarizer` 執行，不用改 `interface.py`。
   想要短名稱的話，再到 `get_summarizer()` 加一行 `if kind == "team": ...`。
3. 有 `generate()` 的摘要器也能給 `/ai`（ai_demo）用：`AI_DEMO_ENGINE=meeting_ai.team:TeamSummarizer`。

不用改 voice_bot、voice_stt，也不用改資料庫。

## 規則（請保留）

- 每個決定、每項待辦都要附 `source_line_ids`，對應 Spec「任務草案要有來源依據」。
  不存在的行號會被 `MeetingSummary.from_dict(valid_ids=...)` 自動濾掉。
- `uncertain=True` 的句子可能聽錯，不要單憑它就產生決定或待辦。
- 語音摘要存進資料庫，透過 `AuthorizedTranscriptReader` 授權查看。文字會議的 `/meeting end` 會將紀錄貼回來源頻道。自訂輸出仍需根據實際讀者檢查來源權限（見 [docs/ai_memory_api.md](../docs/ai_memory_api.md) 第 5 節）。

## 讀取的範例：`show_session.py`

voice_bot 的「查看摘要」「查看逐字稿」按鈕會執行它，也可以當作 AI 組使用讀取介面的範例：

```python
from sqlite_api import SQLiteStore

reader = AuthorizedTranscriptReader(ChannelAccess(client, guild_id), SQLiteStore(db))
lines = await reader.transcript_for(member_id, session_id)   # 沒權限 → AccessDenied
view = await reader.summary_for(member_id, session_id)       # 沒摘要 → None
```

手動試（要用 `text_bot/.venv`，因為需要 discord.py；使用根目錄 .env 的 `VOICE_BOT_TOKEN` 與 `DISCORD_GUILD_ID` 連上 Discord 幾秒）：

```bash
text_bot/.venv/Scripts/python.exe -m meeting_ai.show_session <session_id> --member <Discord ID> --what summary
```

回傳 `{"ok": true, "text": ...}`，或 `{"ok": false, "error_code": ..., "message": ...}`。錯誤代碼照 `spec.md`：

| `error_code` | 什麼時候 |
|---|---|
| `ACCESS_DENIED_USER` | 這個人看不到那個語音頻道 |
| `PERMISSION_UNVERIFIED` | Discord 暫時無法確認權限（不會因此放行） |
| `NOT_FOUND` | 找不到這場錄音，或這場還沒有摘要（`message` 會說是哪一種） |

`message` 是給使用者看的繁體中文，不會透露對方看不到的頻道或內容。


## 開發 /ask 工具

`/ask` 的一次問答由 `ask_channel.py` 處理。一般問題在第一次 OpenAI 請求直接得到回答。若問題需要目前頻道的紀錄，程式會要求模型先呼叫 `get_current_channel_history`。這個工具會驗證 Bot 和提問者的權限，透過 `AuthorizedMessageReader` 讀取 SQLite，再把結果交給 OpenAI。回覆前會重新驗權。

在 [tools.py](tools.py) 新增參數型別、非同步函式及 `TOOLS` 登記項目。例如可新增一個工具，計算最近訊息中含有某個關鍵字的則數：

```python
class CountMentionsArgs(ToolArguments):
    keyword: str


async def count_mentions(context: ToolContext, args: CountMentionsArgs) -> dict:
    rows = await context.read_history()
    keyword = args.keyword.strip().casefold()
    count = sum(keyword in row["content"].casefold() for row in rows) if keyword else 0
    return {"count": count}
```

在同一檔案的 `TOOLS` 字典加上這一項：

```python
"count_mentions": Tool(
    "計算目前 Discord 頻道最近紀錄中包含關鍵字的訊息則數。",
    CountMentionsArgs,
    count_mentions,
),
```

參數型別會產生 function tool 的 JSON Schema。欄位請明確宣告為必填，需要可空值時可用 `str | None`。`ToolArguments` 會拒絕未宣告的參數和不符型別的輸入。身分和來源由後端的 `ToolContext` 固定，`context.read_history()` 會使用授權 reader。處理函式回傳可 JSON 序列化的字典，供模型產生答案。新登記的工具可在完成首次歷史查詢後由模型選用。

從專案根目錄執行下列測試。它使用暫存 SQLite、模擬 Discord 權限與假 OpenAI client。

```powershell
.\text_bot\.venv\Scripts\python.exe -m unittest meeting_ai.tests.test_ask_channel
```

## 測試

```bash
cd meeting_ai
../voice_bot/voice_stt/.venv/Scripts/python.exe -m pytest
```

OpenAI 版本用假的 client 測，不會真的呼叫 API。
`show_session` 的 6 項測試需要 discord.py，在上面的環境會跳過，請另外跑：

```bash
text_bot/.venv/Scripts/python.exe -m unittest meeting_ai.tests.test_show_session -v   # 在 repo 根目錄
```

手動試一場已存的會議：

```bash
voice_bot/voice_stt/.venv/Scripts/python.exe -m meeting_ai.summarize_session <session_id> --db 資料庫路徑
```
