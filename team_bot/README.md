# team_bot — 語音 bot 和文字 bot 合併版

在 Discord 裡只會看到**一個 bot**，語音錄音、文字會議、文字訊息記錄都由它負責。

一個 bot 帳號裡同時跑兩支程式：

| 程式 | 語言 | 負責 |
|---|---|---|
| `voice_bot/` | Node.js | 語音錄音、`/record`、`/meeting`、`/ping`。**所有指令都由它註冊** |
| `team_bot/text_logger.py` | Python | 沿用 `discord_bot/` 的程式，把文字訊息存進資料庫，不註冊指令 |

兩支程式用同一個 token（`voice_bot/.env`），寫進同一個資料庫 `discord_bot/data/messages.sqlite3`。

語音一定要用 Node.js（`@discordjs/voice` 才收得到 Discord 加密後的語音），文字 bot 原本是 Python，所以合併後內部還是兩支程式。

原本的 `discord_bot/bot.py` **沒有改**，還是可以用它自己的 token 單獨跑。不要和合併版同時跑，否則同樣的訊息會被記錄兩次。

## 第一次使用：在 Developer Portal 開兩個權限

文字記錄和 `/meeting` 要讀訊息內容，所以語音 bot 的應用程式要多開兩個權限：

1. 打開 [Discord Developer Portal](https://discord.com/developers/applications)，選語音 bot 的應用程式。
2. 左邊點 **Bot**，往下找到 **Privileged Gateway Intents**。
3. 打開 **Message Content Intent** 和 **Server Members Intent**，按 **Save Changes**。

bot 在要開會的文字頻道還需要「讀取訊息歷史」權限。沒有的話，`/meeting start` 會直接說少了什麼；`npm run check` 印出的邀請連結已經包含這個權限。

## 啟動

```bash
node team_bot/start.mjs
```

- 兩支程式的訊息會加上 `[語音]`、`[文字]` 前綴。
- 啟動參數和 voice_bot 一樣，例如 `node team_bot/start.mjs --summarizer openai --stt openai`；`--help` 會列出全部。
- 按 Ctrl+C 會一起停；語音如果正在錄，會先收尾再結束。
- 文字記錄起不來時（例如還沒開上面的權限），語音和指令照常運作，畫面會說原因。

只想要語音和指令、不要記錄文字訊息：照舊在 `voice_bot/` 執行 `npm start`。`/meeting` 也能用，因為它是開會結束時才直接向 Discord 讀那段訊息，不靠文字記錄。

## 指令

| 指令 | 誰可以用 | 做什麼 |
|---|---|---|
| `/meeting start` | 組長 | 在這個文字頻道開始會議，bot 貼一則「會議開始」 |
| `/meeting end` | 組長 | 結束會議：讀這段期間的發言（bot 的訊息不算），交給摘要器，在同一個頻道貼出會議紀錄 |
| `/meeting status` | 任何人 | 看這個頻道有沒有進行中的會議 |
| `/record …` | 見 [voice_bot](../voice_bot/README.md) | 語音錄音 |
| `/ping` | 任何人 | 確認 bot 在線上 |

組長的判斷和 `/record` 一樣：`LEADER_ROLE_ID` 身分組，沒設的話是有「管理伺服器」權限的人。

## 文字會議怎麼運作

```
/meeting start ─▶ bot 貼「會議開始」（記住這則訊息的位置）
     ……大家在這個頻道討論……
/meeting end ──▶ bot 貼「會議結束」→ 讀兩則之間的發言 → 摘要器整理 → 把那則訊息改成會議紀錄
```

- 摘要器和語音會議用同一個（`MEETING_SUMMARIZER`），所以兩種紀錄的格式一樣。
- 會議進行中 bot 重開也沒關係，開始的位置記在 `voice_bot/recordings/active-meetings.json`。
- 紀錄存進資料庫的 `text_meetings` 表，只存摘要和每項依據的訊息 ID，不另外保存完整訊息（spec：一般聊天不長期完整保存）。
- 待辦只是候選；照 spec R06，正式任務要組長明確指派，這部分是 AI 組的工作。
