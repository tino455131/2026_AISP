# AI 團隊接手指南

這份指南帶你用假資料驗證 Discord 授權讀取，並替 Team Bot 的 `/ask` 新增第一個 OpenAI function tool。若要替換會議摘要器，請看[摘要器介面](../meeting_ai/README.md#介面)。

## 1. 準備環境與假資料

先依[根目錄 README](../README.md#從專案根目錄設定與啟動)安裝文字 Bot 的 Python 環境。只開發 `/ask` 工具時，採手動安裝步驟中的 `text_bot/.venv` 與專案的 editable install 即可。下列指令都從專案根目錄執行。

Windows PowerShell

```powershell
.\text_bot\.venv\Scripts\python.exe demo_data/make_demo_db.py
.\text_bot\.venv\Scripts\python.exe demo_data/try_readers.py
```

macOS／Linux

```sh
./text_bot/.venv/bin/python demo_data/make_demo_db.py
./text_bot/.venv/bin/python demo_data/try_readers.py
```

第一支程式把 [Demo_Script.md](../Demo_Script.md) 轉成 `demo_data/out/messages.sqlite3` 和模擬錄音資料。重跑會重新產生該資料庫。第二支用 `FakeAccess` 模擬 Discord 權限，示範哪些人能讀指定的文字、逐字稿和摘要，也會示範權限確認失敗的情況。這些離線指令使用假資料，執行時不需要 Discord Token 或 OpenAI API key。

## 2. 了解工具如何取得資料

- 一般問題，例如「解釋 Python 的 async」，直接由 OpenAI 回答。需要目前頻道紀錄時，`/ask` 先呼叫 `get_current_channel_history`，之後模型才可選用其他已登記工具。明確詢問其他頻道時，Bot 會提示查詢範圍。
- 工具用 `await context.read_history()` 取得目前頻道最近最多 100 則已存文字。伺服器、頻道與提問者來自 Discord interaction，後端確認 Bot 及提問者的權限，再透過 `AuthorizedMessageReader` 讀取 `SQLiteStore`。
- 自訂工具只需回傳模型回答所需的欄位。下方的計數工具只回傳 `count`。回答含頻道資料時，Bot 會在送出前重新驗權，並只顯示給提問者。

開發者可對照 [Discord 授權讀取](ai_memory_api.md)、[SQLite 方法](../SQL_API_README.md)和[資料表結構](database_schema.md)。

## 3. 新增第一個 tool

在 [meeting_ai/tools.py](../meeting_ai/tools.py) 的 `TOOLS` 字典定義結束後、`execute_tool()` 前貼上整段。參數 `keyword` 是必填字串，結果 `count` 是包含該字串的訊息則數。比對會忽略英文大小寫，同一則訊息只計一次。

```python
class CountMentionsArgs(ToolArguments):
    keyword: str


async def count_mentions(context: ToolContext, args: CountMentionsArgs) -> dict:
    keyword = args.keyword.strip().casefold()
    if not keyword:
        return {"count": 0}

    rows = await context.read_history()
    return {"count": sum(keyword in row["content"].casefold() for row in rows)}


TOOLS["count_mentions"] = Tool(
    "計算目前 Discord 頻道最近紀錄中包含指定關鍵字的訊息則數。",
    CountMentionsArgs,
    count_mentions,
)
```

`ToolArguments` 負責產生 OpenAI 所需的 JSON Schema，也會驗證模型傳入的型別與欄位。`Tool` 的說明應清楚寫出何時用這個工具。處理函式回傳可序列化成 JSON 的字典。

## 4. 用假 OpenAI client 跑通工具

將下面的方法放入 [test_ask_channel.py](../meeting_ai/tests/test_ask_channel.py) 的 `ChannelAskTests` 類別。它沿用測試檔內的假 client 和 `self.read`，依序模擬模型判定需要歷史、呼叫既有歷史工具、呼叫自訂工具，再回覆答案。

```python
    async def test_count_mentions_example(self):
        self.read.return_value = [
            {"message_id": 1, "author_id": 2, "created_at": "2026-11-22", "content": "報告、報告"},
            {"message_id": 2, "author_id": 2, "created_at": "2026-11-22", "content": "下週開會"},
        ]
        client = client_with(
            routing("current_channel"),
            tool_call(),
            tool_call("count_mentions", '{"keyword": "報告"}', call_id="call_count"),
            reply("最近有 1 則訊息提到報告。"),
        )
        result = await ask_channel.ask_question(client, "fake", "有幾則訊息提到報告？", self.context)
        self.assertTrue(result["ok"])
        output = client.responses.create.await_args.kwargs["input"][-1]
        self.assertEqual(output["call_id"], "call_count")
        self.assertEqual(json.loads(output["output"]), {"count": 1})
```

從根目錄跑同一組測試。現有案例同時涵蓋工具參數不符、其他頻道、找不到資料和拒絕存取。

```powershell
.\text_bot\.venv\Scripts\python.exe -m unittest meeting_ai.tests.test_ask_channel demo_data.test_demo_data
```

```sh
./text_bot/.venv/bin/python -m unittest meeting_ai.tests.test_ask_channel demo_data.test_demo_data
```

## 5. 在 Discord 試用

在測試伺服器啟動 Team Bot。依[啟動與設定](../README.md#從專案根目錄設定與啟動)設定 `OPENAI_API_KEY`，準備幾則 Bot 已寫入 SQLite 的測試訊息，再試 `/ask question:請用 count_mentions 計算這個頻道最近有幾則訊息提到「報告」？`。模型是否選擇自訂工具由當次請求決定，上一節的假 client 測試可固定驗證工具確實被執行。Bot 操作與部署限制見 [Team Bot 使用說明](../team_bot/README.md)。
