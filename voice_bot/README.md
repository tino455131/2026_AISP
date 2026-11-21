# voice_bot — Discord 語音頻道錄音 bot（F6）

在 Discord 語音頻道錄下**有按「同意」的人**的聲音，結束後自動：

1. 交給 [`voice_stt`](voice_stt/README.md) 轉成台灣繁體逐字稿，存進 bot 的資料庫（`data/messages.sqlite3`）
2. 交給 [`meeting_ai`](../meeting_ai/README.md) 整理摘要（可替換的介面），存進資料庫
3. 在語音頻道聊天室留一則**靜音**訊息和「查看摘要」「查看逐字稿」按鈕：按的人才看得到內容，不會吵到其他人

為什麼用 Node.js：Discord 從 2026 年 3 月起語音強制端對端加密（DAVE），目前只有
`@discordjs/voice`（0.19.2 起）能正確「聽」別人說話；Python 的套件還不行。所以這支只負責錄音，
其餘都交給 Python。

## 一次性設定

1. **建立語音 bot（和皓元的文字 bot 分開）**：[Discord Developer Portal](https://discord.com/developers/applications) → New Application → Bot → Reset Token，複製 token。
   不需要開任何 Privileged Gateway Intents。
2. **邀請進伺服器**：OAuth2 → URL Generator，scopes 勾 `bot`、`applications.commands`；
   權限勾 **View Channels、Send Messages、Connect、Change Nickname**。用產生的網址邀請進（測試）伺服器。
3. **安裝**。依[根目錄 README](../README.md#從專案根目錄設定與啟動)從根目錄安裝 Node.js 與 Python 依賴。摘要用 `voice_bot/voice_stt/.venv`，查看按鈕用 `text_bot/.venv`。
4. **填寫根目錄 .env**。設定 `VOICE_BOT_TOKEN`、`DISCORD_GUILD_ID`，並視需要設定允許開始錄音的 `LEADER_ROLE_ID`。
5. **從根目錄檢查設定**。

   ```sh
   npm --prefix voice_bot run check
   ```

   它不會印出 token，只會告訴你：token 格式對不對、Discord 認不認得它、bot 在不在伺服器裡。bot 還沒被邀進伺服器時，它會直接印出邀請網址（權限已勾好），可以取代第 2 步。
   加 `-- --offline` 則只檢查檔案、不連 Discord。

## 啟動

```bash
npm --prefix voice_bot start
```

看到「語音錄音 bot 已上線」就可以用了。`/record` 指令會自動註冊到 `.env` 指定的伺服器。

## 使用

| 指令／按鈕 | 誰可以用 | 做什麼 |
|---|---|---|
| `/record start` | 組長 | bot 加入你所在的語音頻道，暱稱變成 `[REC] …`，並在頻道聊天室貼出同意按鈕 |
| 「同意錄音」按鈕 | 任何人 | 從現在起錄你的聲音 |
| 「不同意／撤回同意」按鈕 | 任何人 | 不錄你；如果之前同意過，**刪掉你這次已錄的部分** |
| `/record status` | 任何人 | 看錄了多久、誰同意了 |
| `/record stop` | 組長 | 停止錄音 → 轉文字 → 摘要，頻道裡那則訊息會隨進度更新 |
| 「查看摘要」「查看逐字稿」按鈕 | 看得到這個語音頻道的人（沒參加會議也可以） | 只有按的人看得到；約 5 秒，太長時改成附件 |

- 沒按同意的人，聲音**不會被解碼或存檔**。
- 中途加入的人會被提醒按按鈕。
- 所有人都離開時會自動停止。
- bot 在頻道發的訊息都是**靜音**的（只有未讀紅點，不會跳通知或發出聲音），結束時的進度只用一則訊息更新。
- 「查看」按鈕是透過 AI 組的讀取介面 `AuthorizedTranscriptReader` 讀的，由 Discord 當下確認按的人能不能讀這個語音頻道（View Channel + Read Message History）。
  為了確認權限，每按一次會用同一個 bot 帳號短暫連上 Discord（所以要幾秒）；這是測試用的做法，正式版由 AI 組在 bot 程式裡直接呼叫 reader。

## 檔案和資料在哪

| 東西 | 位置 | 說明 |
|---|---|---|
| 錄音 | `voice_bot/recordings/<session>/<使用者ID>/<毫秒>.wav` | 一句話一個檔；**轉完文字就刪除** |
| 錄音資訊 | `voice_bot/recordings/<session>/manifest.json` | 誰同意、每段的時間、顯示名稱 |
| 給人看的逐字稿 | `voice_bot/recordings/<session>/transcript.md` | 和資料庫內容相同 |
| 逐字稿 | 資料庫 `voice_sessions`、`voice_lines` | AI 透過 `AuthorizedTranscriptReader` 讀，見 [docs/ai_memory_api.md](../docs/ai_memory_api.md) |
| 摘要 | 資料庫 `voice_session_summaries` | 不貼在頻道，用「查看摘要」按鈕看 |

`recordings/`、`.env` 都在 `.gitignore` 裡，不會被 commit。

## 換摘要器

預設是 `simple`（關鍵字規則，不用 API，只是讓流程能測）。要用 OpenAI：

1. 在 repo 根目錄執行 `voice_bot/voice_stt/.venv/Scripts/python.exe -m pip install -r voice_bot/voice_stt/requirements.txt`，將 OpenAI 套件裝進摘要實際使用的環境。
2. 在根目錄 .env 設定 `MEETING_SUMMARIZER=openai` 和 `OPENAI_API_KEY`；可選擇設定 `MEETING_SUMMARY_MODEL`，預設為 `gpt-6-luna`。
3. 執行 `npm --prefix voice_bot run check` 確認設定，再用 `npm --prefix voice_bot start` 啟動。

若原本設定 `MEETING_SUMMARIZER=claude`，請改成 `openai`，並以 `OPENAI_API_KEY` 取代 `ANTHROPIC_API_KEY`。

AI 組要換成自己的版本，見 [meeting_ai/README.md](../meeting_ai/README.md)。

## 出問題時

- **bot 在錄音中途關掉**：錄音資料夾還在，可以手動轉文字：

  ```bash
  ./voice_bot/voice_stt/.venv/Scripts/python.exe -m voice_bot.voice_stt.stt.ingest_recording voice_bot/recordings/錄音資料夾名稱
  ```

  macOS 請把 Python 路徑換成 `./voice_bot/voice_stt/.venv/bin/python`。

- **改不了暱稱**：bot 缺「更改暱稱」權限，錄音照常進行，但大家看不到 `[REC]`。
- **連不上語音頻道**：確認 bot 在那個頻道有 Connect 權限。
- **逐字稿錯很多**：先分清楚是「錄音本身就不好」還是「辨識不好」。
  1. 在 `.env` 加 `KEEP_AUDIO=1`，重開 bot 再錄一次，轉完文字後錄音會保留在 `recordings/<session>/<使用者 ID>/`。
  2. 直接聽那些 WAV：有斷斷續續、機器人聲或怪聲，就是錄音的問題；聽起來正常，就是辨識的問題。
  3. bot 的視窗如果出現「大約掉了 X% 的聲音」，代表封包沒收到。`manifest.json` 裡每段的 `lost` 也記著這個比例。
  4. 測完把 `KEEP_AUDIO` 改回 0，並刪掉 `recordings/` 裡的檔案。

## 測試

```bash
npm --prefix voice_bot test
```

單元測試不需要連 Discord。
