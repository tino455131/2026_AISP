# voice_bot — Discord 語音頻道錄音 bot（F6）

在 Discord 語音頻道錄下**有按「同意」的人**的聲音，結束後自動：

1. 交給 [`voice_stt`](../voice_stt/README.md) 轉成台灣繁體逐字稿，存進 bot 的資料庫（`discord_bot/data/messages.sqlite3`）
2. 交給 [`meeting_ai`](../meeting_ai/README.md) 整理摘要（可替換的介面），貼回語音頻道的聊天室

為什麼用 Node.js：Discord 從 2026 年 3 月起語音強制端對端加密（DAVE），目前只有
`@discordjs/voice`（0.19.2 起）能正確「聽」別人說話；Python 的套件還不行。所以這支只負責錄音，
其餘都交給 Python。

## 一次性設定

1. **建立語音 bot（和皓元的文字 bot 分開）**：[Discord Developer Portal](https://discord.com/developers/applications) → New Application → Bot → Reset Token，複製 token。
   不需要開任何 Privileged Gateway Intents。
2. **邀請進伺服器**：OAuth2 → URL Generator，scopes 勾 `bot`、`applications.commands`；
   權限勾 **View Channels、Send Messages、Connect、Change Nickname**。用產生的網址邀請進（測試）伺服器。
3. **安裝**（需要 Node.js 22.12 以上）：

   ```bash
   cd voice_bot
   npm install
   cp .env.example .env
   ```

4. **填 `.env`**：`DISCORD_TOKEN`、`DISCORD_GUILD_ID`，以及（選填）可以開始錄音的組長身分組 `LEADER_ROLE_ID`。
   token 等於密碼：只貼進 `.env`，不要貼到聊天室、Discord、Notion 或 AI 對話裡。弄丟了就到 Developer Portal 按 Reset Token 重新產生。
5. 確認 `voice_stt/.venv` 已經裝好（見 voice_stt 的 README）；摘要也用同一個環境執行。
6. **檢查設定**：

   ```bash
   npm run check
   ```

   它不會印出 token，只會告訴你：token 格式對不對、Discord 認不認得它、bot 在不在伺服器裡。bot 還沒被邀進伺服器時，它會直接印出邀請網址（權限已勾好），可以取代第 2 步。
   加 `-- --offline` 則只檢查檔案、不連 Discord。

## 啟動

```bash
cd voice_bot
npm start
```

看到「語音錄音 bot 已上線」就可以用了。`/record` 指令會自動註冊到 `.env` 指定的伺服器。

## 使用

| 指令／按鈕 | 誰可以用 | 做什麼 |
|---|---|---|
| `/record start` | 組長 | bot 加入你所在的語音頻道，暱稱變成 `[REC] …`，並在頻道聊天室貼出同意按鈕 |
| 「同意錄音」按鈕 | 任何人 | 從現在起錄你的聲音 |
| 「不同意／撤回同意」按鈕 | 任何人 | 不錄你；如果之前同意過，**刪掉你這次已錄的部分** |
| `/record status` | 任何人 | 看錄了多久、誰同意了 |
| `/record stop` | 組長 | 停止錄音 → 轉文字 → 摘要 → 貼回頻道 |

- 沒按同意的人，聲音**不會被解碼或存檔**。
- 中途加入的人會被提醒按按鈕。
- 所有人都離開時會自動停止。

## 檔案和資料在哪

| 東西 | 位置 | 說明 |
|---|---|---|
| 錄音 | `voice_bot/recordings/<session>/<使用者ID>/<毫秒>.wav` | 一句話一個檔；**轉完文字就刪除** |
| 錄音資訊 | `voice_bot/recordings/<session>/manifest.json` | 誰同意、每段的時間、顯示名稱 |
| 給人看的逐字稿 | `voice_bot/recordings/<session>/transcript.md` | 和資料庫內容相同 |
| 逐字稿 | 資料庫 `voice_sessions`、`voice_lines` | AI 透過 `AuthorizedTranscriptReader` 讀，見 [docs/ai_memory_api.md](../docs/ai_memory_api.md) |
| 摘要 | 資料庫 `voice_session_summaries`，並貼在語音頻道聊天室 | |

`recordings/`、`.env` 都在 `.gitignore` 裡，不會被 commit。

## 換摘要器

預設是 `simple`（關鍵字規則，不用 API，只是讓流程能測）。要用 Claude：

```bash
# voice_stt 的 venv 要先裝 anthropic：voice_stt/.venv/Scripts/python.exe -m pip install anthropic
MEETING_SUMMARIZER=claude ANTHROPIC_API_KEY=... npm start
```

AI 組要換成自己的版本，見 [meeting_ai/README.md](../meeting_ai/README.md)。

## 出問題時

- **bot 在錄音中途關掉**：錄音資料夾還在，可以手動轉文字：

  ```bash
  cd voice_stt
  .venv/Scripts/python.exe -m stt.ingest_recording ../voice_bot/recordings/<session>
  ```

- **改不了暱稱**：bot 缺「更改暱稱」權限，錄音照常進行，但大家看不到 `[REC]`。
- **連不上語音頻道**：確認 bot 在那個頻道有 Connect 權限。
- **逐字稿錯很多**：先分清楚是「錄音本身就不好」還是「辨識不好」。
  1. 在 `.env` 加 `KEEP_AUDIO=1`，重開 bot 再錄一次，轉完文字後錄音會保留在 `recordings/<session>/<使用者 ID>/`。
  2. 直接聽那些 WAV：有斷斷續續、機器人聲或怪聲，就是錄音的問題；聽起來正常，就是辨識的問題。
  3. bot 的視窗如果出現「大約掉了 X% 的聲音」，代表封包沒收到。`manifest.json` 裡每段的 `lost` 也記著這個比例。
  4. 測完把 `KEEP_AUDIO` 改回 0，並刪掉 `recordings/` 裡的檔案。

## 測試

```bash
npm test
```

8 項單元測試，不需要連 Discord。目前還沒有在真的 Discord 伺服器上測過收音。
