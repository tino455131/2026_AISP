# Decisions Log

## 2026-09-21 — Initial code steward (example)
**What:** [Name] is the initial code steward for the team.
**Why:** [one sentence — e.g. "volunteered," "has the most git experience so far," "assigned by team agreement"]

## 2026-10-23 - Develop platform decided
**What:** Discord Bot is our develop platform.
**Why:** Discord is a common platform for collaboration, and the developer platform of bot is mature to integrate AI model. It also provided text and voice modality to fullfil our develop demand. 

## 2026-10-28 — Python Discord bot starter

**What:** 新增 `discord_bot/`，以 `discord.py` 建立提供 `/ping` 的斜線指令 bot。
**Why:** 將 bot 起始程式放在既有課程專案內，並以獨立資料夾避免覆蓋專案文件；斜線指令不需要 Message Content Intent。

## 2026-10-28 — 指定伺服器訊息紀錄與歷史匯入

**What:** 依使用者本次要求，bot 記錄指定伺服器中它有權讀取的文字頻道與討論串訊息，首次啟動並匯入可存取的歷史訊息。此決定取代上方起始版本「不需要 Message Content Intent」的設定。
**Why:** 為未來 AI 記憶建立有伺服器與頻道來源的原始資料。以本機 SQLite 保存，查詢介面限定單一頻道；目前不提供 AI 回答或跨頻道讀取。資料保留期限及成員知情方式仍待團隊決定。
## 2026-11-17 — 依目前 Discord 權限限制訊息讀取

**What:** 新增內部 ChannelAccess 與 AuthorizedMessageReader。訊息仍按 guild_id／channel_id 保存；每次查詢重新取得頻道、成員及權限，可列出目前能看見頻道的人類成員。讀取已存訊息須有 View Channel 與 Read Message History；私人討論串另須為成員或在父頻道有 Manage Threads。無法確認權限時不回傳資料。
**Why:** 讓未來 AI 記憶能區分來源頻道，並避免把私人頻道文字交給沒有目前存取權的人。可見名單不持久保存，避免角色、覆寫或成員資格變更後使用過期資料。此決定需要 Server Members Intent；目前仍未加入公開查詢指令或 AI 回答功能。

## 2026-11-18 — 語音轉文字模組 `voice_stt/`（F6）

**What:** 新增 `voice_stt/`，把一個音檔轉成台灣繁體中文逐字稿（JSONL 給程式、Markdown 給人看）。在本機 GPU 以 faster-whisper 執行聯發科的 Breeze-ASR-25（Apache-2.0），並做 VAD 跳過靜音、OpenCC `s2twp` 轉台灣繁體、過濾模型在靜音時亂生的句子，沒把握的句子標 ⚠️。與 `discord_bot/` 分開資料夾與 `.venv`，因為語音辨識的套件（含 CUDA 函式庫）很大，bot 本身不需要。程式由 AI（Claude）協助撰寫，見 `PROMPT_LOG.md`。
**Why:** F6「語音輸入、文字輸出」需要能處理台灣口音與中英夾雜（PR、merge、token）的語音辨識；Breeze-ASR-25 正是為此調整的模型。在本機執行，會議錄音不會離開主機。不採用雲端語音 API（例如 OpenAI、Gemini 的音訊模型），因為會把私人會議錄音交給第三方，而且依分鐘計費。Discord 本來就把每個人的聲音分開送給 bot，因此不需要另外做說話者辨識。
**Led by:** Ping3227

## 2026-11-18 — 語音逐字稿存進 bot 資料庫，沿用頻道權限

**What:** 新增 `discord_bot/transcript_store.py` 與 `transcript_reader.py`。逐字稿存在與文字訊息相同的 `data/messages.sqlite3`，新增三張表：`voice_sessions`、`voice_lines`、`voice_session_summaries`。資料庫改用 WAL 模式。`AuthorizedTranscriptReader` 沿用 `ChannelAccess`，以語音頻道的 View Channel + Read Message History 判斷能否讀取。`bot.py` 在刪除語音頻道或被移出伺服器時，連同逐字稿與摘要一起刪除。`voice_stt` 新增 `python -m stt.import_session`：每人一個音檔，分別辨識後依時間合併寫入。另新增 `docs/ai_memory_api.md`，作為給 AI 組的讀取介面草稿。程式由 AI（Claude）協助撰寫，見 `PROMPT_LOG.md`。
**Why:**
- 另開新表而不塞進 `messages`：語音句子沒有 Discord 訊息 ID，又多了信心分數與警告標記；分開也讓皓元的表與測試完全不受影響。
- 沿用 `ChannelAccess`：私人語音頻道自動得到和文字相同的保護。
- 開 WAL：bot 與 `voice_stt` 是兩個程式，可以同時寫入，不會互相卡住。
- 會議摘要的「存放、權限、失效」放在資料層，「內容與 prompt」由 AI 組負責：摘要含有原始內容，必須和原始資料遵守同一套權限與刪除規則（撤回同意、刪頻道時一起刪），不能變成繞過權限的後門。
**Alternative rejected:** 把逐字稿寫成 `messages` 表的假訊息；跨頻道的摘要（權限無法沿用單一頻道）。
**Open questions:**
- 沒參加會議但看得到語音頻道的人，能否讀逐字稿？
- 輸出前的聽眾檢查由 AI 組實作。
**Led by:** Ping3227

## 2026-11-18 — 語音錄音 bot `voice_bot/`（Node.js）與可替換的摘要介面 `meeting_ai/`

**What:**

- `voice_bot/` 是另一個 Discord 應用程式（自己的 token），用 discord.js 14.28.1 加 @discordjs/voice 0.19.2（內建 DAVE 加密）錄音。
- 組長用 `/record start` 開始錄音。bot 暱稱改成 `[REC]`，並在語音頻道聊天室貼出同意按鈕。**只錄有按「同意」的人**，一句話存成一個 WAV。
- 撤回同意會立刻刪掉那個人的錄音。所有人離開時會自動停止。
- `/record stop` 之後的流程：
  1. 執行 `voice_stt` 的 `stt.ingest_recording`，轉文字寫進資料庫，然後刪除錄音。
  2. 執行 `meeting_ai.summarize_session` 產生摘要：存進 `voice_session_summaries`，並貼回同一個語音頻道（不發 @ 通知）。
- `meeting_ai/` 定義 `MeetingSummarizer` 介面，內建兩個版本：
  - `simple`：關鍵字，不用 API，供測試
  - `claude`：Claude API，用 JSON schema 固定輸出
  - 用 `MEETING_SUMMARIZER` 切換；AI 組可以換成自己的實作。
- 程式由 AI（Claude）協助撰寫，見 `PROMPT_LOG.md`。

**Why:**

- 收音只能用 Node：Python 有 DAVE 解密函式庫（`davey`、`dave.py`），但到 2026-11-18 為止，還沒有正式版的 Python Discord 套件把它接進收音（見下方 Open questions）。Node 的 `@discordjs/voice` 0.19.2 已經可以收音。所以 Node 只負責錄音和同意流程，轉文字與摘要都在 Python，沿用已測過的 `voice_stt`。
- 用獨立的 bot 帳號：同一個 token 不能被兩個程式同時登入，分開也讓錄音出錯不會影響文字紀錄。
- 一句話一個檔：可以精準刪掉撤回者的部分，時間位移也直接記在 `manifest.json`。
- 摘要用介面隔開：使用者想先測完整流程，正式的摘要由 AI 組負責，換實作時不需要改錄音或資料庫。

**Alternative rejected:**

- 用 Craig 等第三方錄音 bot：錄音會經過第三方伺服器，同意流程也無法自訂。
- 把錄音功能塞進皓元的 Python bot：Python 無法收音。

**Open questions:**

- 已在 Discord 實測收音（2026-11-19）：錄到的片段沒有漏收；照稿念 10 句時錯字率約 9%，主要錯在英文術語。1–2 秒的短片段辨識很差，因此轉文字前會把同一人相近的片段接起來。兩人對話的發言順序還沒照稿驗證。
- 錄音同意的公告文字要請全組確認。
- 什麼時候可以改用 Python 錄音（2026-11-18 查到的狀況）：
  - discord.py 本體不支援收音；它的收音外掛 `discord-ext-voice-recv` 有多個社群送的 DAVE 修補，都還沒合併。
  - py-cord 的 DAVE 收音在 PR #3159，預計進 2.9.0rc1；正式版 2.8.1 還不行。
  - 重新評估的條件：py-cord 出了包含 DAVE 收音的正式版，而且有人實測可用。
  - 即使改用也要注意：py-cord 和 discord.py 的模組都叫 `discord`，不能裝在同一個環境。錄音仍然要是獨立的程式和 bot 帳號，省下的只是「多一種語言」。

**Led by:** Ping3227
