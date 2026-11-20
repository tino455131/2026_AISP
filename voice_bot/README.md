# voice_bot — Discord 語音頻道錄音 bot（F6）

在 Discord 語音頻道錄下大家的聲音（預設進來就錄，不想被錄的人可以按「不要錄我」），結束後自動：

1. 交給 [`voice_stt`](../voice_stt/README.md) 轉成台灣繁體逐字稿，存進 bot 的資料庫（`discord_bot/data/messages.sqlite3`）
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
3. **安裝**（需要 Node.js 22.12 以上）：

   ```bash
   cd voice_bot
   npm install
   cp .env.example .env
   ```

4. **填 `.env`**：`DISCORD_TOKEN`、`DISCORD_GUILD_ID`，以及（選填）可以開始錄音的組長身分組 `LEADER_ROLE_ID`。
   token 等於密碼：只貼進 `.env`，不要貼到聊天室、Discord、Notion 或 AI 對話裡。弄丟了就到 Developer Portal 按 Reset Token 重新產生。
5. 確認 `voice_stt/.venv` 已經裝好（見 voice_stt 的 README）；摘要也用同一個環境執行。
   「查看」按鈕用 `discord_bot/.venv`（需要 discord.py，見 discord_bot 的 README）。
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

看到「語音錄音 bot 已上線」就可以用了。

**啟動時臨時換設定**：參數會蓋過 `.env`，只對這次啟動有效，適合換電腦或測試時快速切換：

```bash
npm start -- --summarizer openai --stt openai
```

| 參數 | 可以填 |
|---|---|
| `--summarizer` | `simple`、`claude-code`、`claude`、`openai`、`模組路徑:類別名稱` |
| `--stt` | `local`（本機 Breeze）、`openai`、`模組路徑:類別名稱` |
| `--consent` | `direct`（進來就錄）、`ask`（按了同意才錄） |
| `--auto-record` | `on`、`off` |

`npm start -- --help` 會列出來。API key 只能放 `.env`，不能當參數，因為參數會出現在命令列和紀錄裡。
長期用的設定寫在 `.env`，臨時換用參數。`/record` 指令會自動註冊到 `.env` 指定的伺服器。

## 使用

| 指令／按鈕 | 誰可以用 | 做什麼 |
|---|---|---|
| （自動）有人進入語音頻道 | — | bot 在線上時自動加入並開始錄音，流程和 `/record start` 一樣（`AUTO_RECORD`，預設開啟） |
| `/record start` | 組長 | bot 加入你所在的語音頻道，暱稱變成 `[REC] …`，並在頻道聊天室貼出錄音通知和按鈕 |
| 「不要錄我」按鈕 | 任何人 | 這次不再錄你，並**刪掉你這次已錄的部分** |
| 「繼續錄我」按鈕 | 任何人 | 按錯「不要錄我」時，從現在起恢復錄你 |
| `/record status` | 任何人 | 看錄了多久、正在錄哪些人 |
| `/meeting start`、`/meeting end` | 組長 | 文字會議：結束後在同一個頻道貼出會議紀錄（見 [team_bot](../team_bot/README.md)） |
| `/ping` | 任何人 | 確認 bot 在線上 |
| `/record stop` | 組長 | 停止錄音 → 轉文字 → 摘要，頻道裡那則訊息會隨進度更新 |
| 「查看摘要」「查看逐字稿」按鈕 | 看得到這個語音頻道的人（沒參加會議也可以） | 只有按的人看得到；約 5 秒，太長時改成附件 |

- **錄音同意方式**（`.env` 的 `CONSENT_MODE`）：
  - `direct`（預設）：語音頻道裡的人**都會被錄**，中途進來的人也是，並在聊天室 @ 他告知。按了「不要錄我」的人，這次錄音就不會再錄他，離開再回來也一樣。
  - `ask`：只錄按了「同意錄音」的人，按鈕改成「同意錄音」「不同意／撤回同意」；沒按的人聲音**不會被解碼或存檔**。
- 被刪掉或沒被錄的人，聲音不會被保存。
- 所有人都離開時會自動停止。
- **自動錄音**（預設開啟，`.env` 設 `AUTO_RECORD=0` 可以關掉）：
  - 有人進入語音頻道約 3 秒後，bot 自動加入並開始錄音，同意方式照 `CONSENT_MODE`。
  - 一個伺服器同時只能錄一個語音頻道（Discord 的限制），會選人最多的那個；錄完會再看看別的頻道有沒有人。
  - 自動開始的錄音如果最後什麼都沒錄到（沒人講話，或大家都按了不要錄），會把它發的訊息收回，也不留資料夾，聊天室不會多出紀錄。
  - 組長用 `/record stop` 停掉後，那個頻道要等所有人都離開、再有人進來，才會再自動開始。
  - 只想在某些頻道自動錄音：`AUTO_RECORD_CHANNELS=頻道ID,頻道ID`。AFK 頻道一律不錄。
- bot 在頻道發的訊息都是**靜音**的（只有未讀紅點，不會跳通知或發出聲音），結束時的進度只用一則訊息更新。
- 「查看」按鈕是透過 AI 組的讀取介面 `AuthorizedTranscriptReader` 讀的，由 Discord 當下確認按的人能不能讀這個語音頻道（View Channel + Read Message History）。
  為了確認權限，每按一次會用同一個 bot 帳號短暫連上 Discord（所以要幾秒）；這是測試用的做法，正式版由 AI 組在 bot 程式裡直接呼叫 reader。

## 檔案和資料在哪

| 東西 | 位置 | 說明 |
|---|---|---|
| 錄音 | `voice_bot/recordings/<session>/<使用者ID>/<毫秒>.wav` | 一句話一個檔；**轉完文字就刪除** |
| 錄音資訊 | `voice_bot/recordings/<session>/manifest.json` | 每個人的錄音狀態、每段的時間、顯示名稱 |
| 給人看的逐字稿 | `voice_bot/recordings/<session>/transcript.md` | 和資料庫內容相同 |
| 逐字稿 | 資料庫 `voice_sessions`、`voice_lines` | AI 透過 `AuthorizedTranscriptReader` 讀，見 [docs/ai_memory_api.md](../docs/ai_memory_api.md) |
| 摘要 | 資料庫 `voice_session_summaries` | 不貼在頻道，用「查看摘要」按鈕看 |

`recordings/`、`.env` 都在 `.gitignore` 裡，不會被 commit。

## 換摘要器

預設是 `simple`（關鍵字規則，不用 API，只是讓流程能測）。

用這台電腦已登入的 Claude Code（不用 API key，算在訂閱額度，測試用）：在 `.env` 加上 `MEETING_SUMMARIZER=claude-code`，然後重開 bot。`npm run check` 會確認找得到 `claude` 指令。

要用 Claude API：

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
