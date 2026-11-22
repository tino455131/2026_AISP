# team_bot — 語音 bot 和文字 bot 合併版

在 Discord 裡只會看到**一個 bot**，語音錄音、文字會議、文字訊息記錄都由它負責。

一個 bot 帳號裡同時跑兩支程式：

| 程式 | 語言 | 負責 |
|---|---|---|
| `voice_bot/` | Node.js | 語音錄音、`/record`、`/meeting`、`/ai`、`/summary_this_channel`、`/ask`、`/help`、`/ping`。**所有指令都由它註冊** |
| `team_bot/text_logger.py` | Python | 沿用 `text_bot/` 的程式，把文字訊息存進資料庫，不註冊指令 |

兩支程式都讀根目錄的 `.env`，用同一個 token（`VOICE_BOT_TOKEN`），透過 `sqlite_api` 寫進同一個資料庫（預設 `data/messages.sqlite3`）。`TEXT_BOT_TOKEN` 只有單獨跑文字 bot 時才用。

語音一定要用 Node.js（`@discordjs/voice` 才收得到 Discord 加密後的語音），文字 bot 原本是 Python，所以合併後內部還是兩支程式。

`text_bot/bot.py` **沒有改**，還是可以用 `TEXT_BOT_TOKEN` 單獨跑。不要和合併版同時跑，否則同樣的訊息會被記錄兩次。

## 第一次使用：在 Developer Portal 開兩個權限

文字記錄和 `/meeting` 要讀訊息內容，所以語音 bot 的應用程式要多開兩個權限：

1. 打開 [Discord Developer Portal](https://discord.com/developers/applications)，選語音 bot 的應用程式。
2. 左邊點 **Bot**，往下找到 **Privileged Gateway Intents**。
3. 打開 **Message Content Intent** 和 **Server Members Intent**，按 **Save Changes**。

bot 在要開會的文字頻道還需要「讀取訊息歷史」權限。沒有的話，`/meeting start` 會直接說少了什麼；`npm run check` 印出的邀請連結已經包含這個權限。

## 啟動

先在根目錄執行 `SETUP_Windows.ps1`（或 macOS／Linux 的腳本），它會建立 `text_bot/.venv`、`voice_bot/voice_stt/.venv`，安裝 `sqlite_api`，並從 `.env.example` 建立 `.env`。在 `.env` 填好 `VOICE_BOT_TOKEN` 和 `DISCORD_GUILD_ID` 後，在 repo 根目錄執行：

```bash
node team_bot/start.mjs
```

- 兩支程式的訊息會加上 `[語音]`、`[文字]` 前綴。
- 啟動參數和 voice_bot 一樣，例如 `node team_bot/start.mjs --summarizer openai --stt openai`；`--help` 會列出全部。
- 按 Ctrl+C 會一起停；語音如果正在錄，會先收尾再結束。
- 文字記錄起不來時（例如還沒開上面的權限），語音和指令照常運作，畫面會說原因。

只想要語音和指令、不要記錄文字訊息：在 repo 根目錄執行 `npm --prefix voice_bot start`。`/meeting` 也能用，因為它是開會結束時才直接向 Discord 讀那段訊息，不靠文字記錄。

## 指令

在 Discord 執行 `/help` 可查看目前所有指令和子指令。

| 指令 | 誰可以用 | 做什麼 |
|---|---|---|
| `/meeting start` | 組長 | 在這個文字頻道開始會議，bot 貼一則「會議開始」 |
| `/meeting end` | 組長 | 結束會議：讀這段期間的發言（bot 的訊息不算），交給摘要器，在同一個頻道貼出會議紀錄 |
| `/meeting status` | 任何人 | 看這個頻道有沒有進行中的會議 |
| `/help` | 任何人 | 查看已註冊的指令與用途，清單只顯示給執行者 |
| `/ask question:<問題>` | 任何人，查詢歷史時須有頻道歷史讀取權限 | 私人 OpenAI 問答，可問一般知識、寫作、程式或目前頻道最近的討論 |
| `/summary_this_channel` | 能讀取頻道歷史的成員 | 用 `MEETING_SUMMARIZER` 摘要目前頻道最近 100 則已存入 SQLite 的文字，結果只顯示給提問者 |
| `/record …` | 見 [voice_bot](../voice_bot/README.md) | 語音錄音 |
| `/ai tasks`、`/ai ask` | 看得到那場會議頻道的人 | 【測試】AI 整理任務、問會議問題，結果只有你看得到（見 [ai_demo](../ai_demo/README.md)） |
| `/ping` | 任何人 | 確認 bot 在線上 |

組長的判斷和 `/record` 一樣：`LEADER_ROLE_ID` 身分組，沒設的話是有「管理伺服器」權限的人。

## 私人 AI 問答

在根目錄的 `.env` 設定 `OPENAI_API_KEY`。`/ask` 使用 `MEETING_SUMMARY_MODEL` 指定的 OpenAI 模型，預設是 `gpt-6-luna`。既有虛擬環境更新後，請從根目錄重新安裝文字 Bot 的依賴，再重啟 Team Bot。

- Windows PowerShell 使用 `.\text_bot\.venv\Scripts\python.exe -m pip install -r text_bot/requirements.txt`。
- macOS 使用 `./text_bot/.venv/bin/python -m pip install -r text_bot/requirements.txt`。
- 如有覆寫 `READER_PYTHON`，請用該 Python 安裝同一份依賴。

`/ask question:解釋 Python 的 async` 直接回答。`/ask question:我們剛才決定了什麼？` 會驗證來源頻道權限，再交給 OpenAI 整理 SQLite 已記錄的文字。每次最多讀取最近 100 則，並保留最多 12,000 個文字字元。答案留在原頻道，只有提問者看得到。`/ai ask` 仍用於指定會議的問答，`/summary_this_channel` 仍由 `MEETING_SUMMARIZER` 產生摘要。

工具開發方式見 [meeting_ai/README.md](../meeting_ai/README.md#開發-ask-工具)。

## 文字會議怎麼運作

```
/meeting start ─▶ bot 貼「會議開始」（記住這則訊息的位置）
     ……大家在這個頻道討論……
/meeting end ──▶ bot 貼「會議結束」→ 讀兩則之間的發言 → 摘要器整理 → 把那則訊息改成會議紀錄
```

- 摘要器和語音會議用同一個（`MEETING_SUMMARIZER`），所以兩種紀錄的格式一樣。
- `/summary_this_channel` 可直接執行，讀取 SQLite 已記錄的文字。指令會在整理前確認 Bot 和提問者的來源頻道權限，回覆前再次驗權。
- 會議進行中 bot 重開也沒關係，開始的位置記在 `voice_bot/recordings/active-meetings.json`。
- 紀錄存進資料庫的 `text_meetings` 表，只存摘要和每項依據的訊息 ID，不另外保存完整訊息（spec：一般聊天不長期完整保存）。
- 待辦只是候選；照 spec R06，正式任務要組長明確指派，這部分是 AI 組的工作。
