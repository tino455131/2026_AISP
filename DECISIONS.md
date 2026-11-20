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

## 2026-11-19 — 錄音結束不主動貼摘要：靜音訊息＋「查看」按鈕，透過讀取介面讀

**What:**

- voice_bot 在語音頻道發的訊息全部改成靜音（Discord 的 SuppressNotifications：只有未讀紅點，不跳通知、不發聲）。
- `/record stop` 之後的進度只用**一則訊息**更新：從「正在轉成文字」到「完成」。
- 摘要不再貼到頻道，只存進資料庫。完成訊息附「查看摘要」「查看逐字稿」按鈕，按的人才看得到（ephemeral）。
- 按鈕執行新的 `meeting_ai/show_session.py`，它只透過 `AuthorizedTranscriptReader` 讀，由 Discord 當下確認按的人能不能讀這個語音頻道，同時當作 AI 組使用讀取介面的範例。
- 程式由 AI（Claude）協助撰寫，見 `PROMPT_LOG.md`。

**Why:**

- 使用者希望不要吵到伺服器裡的其他人。
- 摘要屬於資料庫裡的資料，讀取應該是 AI 組（透過 reader）的事；按鈕是為了現在就能測試這條讀取路線。
- 摘要只留在資料庫，撤回同意或刪頻道時仍能一起刪除。私訊或貼在頻道的副本則刪不到。

**Alternative rejected:**

- 私訊每位參加者：私訊裡的副本無法跟著刪除規則刪掉，關閉私訊的人也收不到。
- 只改成靜音、照樣貼在頻道：看得到頻道的人都會看到全文，也就繞過了 reader。

**Open questions:**

- 看得到語音頻道、但沒參加會議的人，按鈕也能看。這是目前 reader 的規則，測試期間先維持，待團隊決定。
- 為了確認權限，每按一次都會用同一個 bot 帳號短暫連上 Discord，要幾秒。這只適合測試；正式版應由 AI 組在 bot 程式裡直接呼叫 reader。

**Led by:** Ping3227

## 2026-11-20 — 新增摘要器 `claude-code`：用主機上已登入的 Claude Code 整理會議（測試用）

**What:**

- `meeting_ai/claude_code.py` 新增 `ClaudeCodeSummarizer`，用 `MEETING_SUMMARIZER=claude-code` 選用。
- 每次摘要執行一次 `claude -p`，提示和 JSON schema 與 `claude` 版相同，做完就結束。
- 安全設定：
  - 在空的暫存資料夾執行
  - 關掉所有工具和 MCP
  - 不把對話存到硬碟
  - 執行時拿掉 `ANTHROPIC_API_KEY`，確保用的是登入帳號
- 摘要器會把文字送到 Anthropic 時（`claude`、`claude-code`），錄音開始的同意訊息會多一行說明。
- 程式由 AI（Claude）協助撰寫，見 `PROMPT_LOG.md`。

**Why:**

- 使用者想在不申請 API key 的情況下，用自己的 Claude Code 訂閱測試真正的 AI 摘要。
- 沒有摘要要做時沒有常駐程式，不佔用額度。

**Alternative rejected:**

- 常駐的 Claude Code 加 Channels：還是預覽版，自己寫的程式只能用開發者測試模式接。
- 透過 Claude 內的介面（mod）轉交：不是官方支援的串接方式。

**Open questions:**

- Anthropic 規定給別人用的產品要用 API key，所以這只用於測試，正式上線要改用 `claude`（API key）或 AI 組的版本。
- 主機（皓元的電腦）要另外安裝並登入 Claude Code。
- 逐字稿會送到 Anthropic：同意訊息已加註，但要請全組確認可以接受。

**Led by:** Ping3227

## 2026-11-20 — bot 在線上時，有人進語音頻道就自動開始錄音

**What:**

- voice_bot 新增自動錄音，預設開啟，`AUTO_RECORD=0` 可以關掉。
- 有人進入語音頻道約 3 秒後，bot 自動加入並貼出同意按鈕，不必再等組長下 `/record start`。同意規則不變：**只錄按了同意的人**。
- 一個伺服器同時只錄一個頻道，選人最多的那個；AFK 頻道不錄。`AUTO_RECORD_CHANNELS` 可以只指定某些頻道。
- 自動開始、但最後什麼都沒錄到時，收回 bot 發的訊息，也刪掉空的錄音資料夾。
- 組長手動 `/record stop` 後，那個頻道清空前不會再自動開始。
- `/record start`、`/record stop` 照舊可用。
- 程式由 AI（Claude）協助撰寫，見 `PROMPT_LOG.md`。

**Why:**

- 使用者希望開會時不用記得下指令，只要 bot 在線上就會進入錄音狀態。
- 同意仍然一人一按，所以自動加入不會錄到沒同意的人。

**Alternative rejected:**

- 自動錄下頻道裡所有人：違反知情同意。
- 只要有人進來就一直留紀錄：短暫進出也會在聊天室留下訊息，吵到大家。

**Open questions:**

- bot 會自動進入任何有人的語音頻道（包括閒聊用的），要請全組確認可以接受，或用 `AUTO_RECORD_CHANNELS` 限定開會用的頻道。
- 改成自動之後，錄音開始的時間點變成「第一個人進來」，不再是「組長宣布開會」。

**Led by:** Ping3227


## 2026-11-20 — 「查看」按鈕的拒絕原因改用 spec 的英文錯誤代碼

**Decision:**

- `meeting_ai.show_session` 拒絕時回傳 `{"ok": false, "error_code", "message"}`，代碼照 `spec.md` v1.1 的 `ErrorCode`：
  - 看不到語音頻道：`ACCESS_DENIED_USER`（原本叫 `denied`）
  - Discord 暫時無法確認權限：`PERMISSION_UNVERIFIED`（原本叫 `unavailable`）
  - 找不到錄音、或這場沒有摘要：`NOT_FOUND`（原本叫 `not_found`、`no_summary`），用 `message` 說明是哪一種
- 給使用者看的繁體中文訊息統一由 `show_session` 產生，voice_bot 只負責顯示。
- 程式由 AI（Claude）協助撰寫，見 `PROMPT_LOG.md`。

**Why:**

- `spec.md` 規定程式用英文 `ErrorCode` 判斷原因，繁體中文 `message` 給人看；全組用同一套代碼，AI 組讀取時才不用另外對照。

**Alternative rejected:**

- 保留舊的小寫原因名稱：和 spec 不一致。
- 「沒有摘要」另外新增代碼：spec 的代碼表沒有這一項，而它本來就是「找不到資料」，用 `message` 區分就夠了。

**Led by:** Ping3227

## 2026-11-20 — 語音頻道改成進來就錄，保留「不要錄我」

**Decision:**

- voice_bot 新增 `CONSENT_MODE`，預設 `direct`：
  - 語音頻道裡的人都會被錄，中途進來的人也一樣，bot 會在聊天室 @ 他告知。
  - 不用再按「同意錄音」。
- 按鈕改成「不要錄我」和「繼續錄我」：
  - 按「不要錄我」：刪掉他這次已錄的部分，這次錄音不會再錄他，離開再回來也一樣。
  - 按錯可以按「繼續錄我」恢復。
- `CONSENT_MODE=ask` 可以改回原本「按了同意才錄」。
- 程式由 AI（Claude）協助撰寫，見 `PROMPT_LOG.md`。

**Why:**

- 使用者決定 bot 進語音頻道不用逐一徵求同意，進來的人直接錄。

**Alternative rejected:**

- 完全拿掉退出的方法：不想被錄的人沒辦法刪掉自己的聲音。
- 每個人進來都私訊或 @ 他、要他按同意：使用者不要這種逐一詢問。

**Open questions:**

- 全組要先知道並同意「語音頻道會被錄音」，可以在伺服器公告。也可以用 `AUTO_RECORD_CHANNELS` 只錄開會用的頻道，閒聊頻道不錄。
- spec 沒有錄音同意的規則，見 spec 問題 V3。

**Led by:** Ping3227

## 2026-11-20 — 摘要器拆成「共用流程＋各來源一個方法」，換來源不用改程式

**Decision:**

- 新增 `meeting_ai/llm.py` 的 `LLMSummarizer`。這些都放在這裡共用：
  - 提示詞、輸出格式（JSON schema）
  - 逐字稿排法
  - 回覆解析（JSON 字串、dict、包在程式碼區塊裡的都可以）
  - 負責人代號修正、去掉不存在的行號
- `claude`（API）和 `claude-code` 都改成它的子類別，各自只寫「怎麼呼叫模型」的 `generate()`，所以摘要格式完全一樣。
- `MEETING_SUMMARIZER` 可以填「模組路徑:類別名稱」，掛上任何其他來源，不用改 meeting_ai 的檔案。
- voice_bot 錄音通知裡「逐字稿會交給誰」不再寫死 Claude：
  - simple、claude、claude-code 會自動判斷。
  - 其他來源用 `MEETING_SUMMARY_SENDS_TO` 寫名稱，在這台電腦上跑的模型填 `none`。
- 程式由 AI（Claude）協助撰寫，見 `PROMPT_LOG.md`。

**Why:**

- 使用者之後可能從 claude-code 換成 Claude API 或其他來源，希望很容易切換。

**Alternative rejected:**

- 每多一個來源就在 `get_summarizer()` 加一個判斷：每次都要改 meeting_ai 的檔案。
- 每個來源各寫一份提示詞：摘要格式會不一致，讀取端要分別處理。

**Led by:** Ping3227

## 2026-11-21 — 語音 bot 和文字 bot 合併成同一個 bot 帳號；新增文字會議 /meeting

**Decision:**

- 合併成一個 bot 帳號，用語音 bot 的 token。內部還是兩支程式：
  - Node（voice_bot）負責語音，並註冊所有指令。
  - Python（`team_bot/text_logger.py`，沿用 discord_bot 的程式）負責記錄文字訊息，不註冊指令。
  - 兩支寫同一個資料庫，用 `node team_bot/start.mjs` 一起啟動。
- 原本的 `discord_bot/bot.py` 不改、不刪，還是可以用它自己的 token 單獨跑。
- 新增 `/meeting start`、`/meeting end`、`/meeting status`（spec R05），只有組長能開始和結束：
  - 結束時，直接向 Discord 讀兩則 bot 訊息之間的發言，bot 的訊息不算。
  - 交給和語音會議同一個摘要器，在原頻道貼出會議紀錄。
  - 紀錄存進 `text_meetings` 表，只存摘要和依據的訊息 ID。
- 邀請連結多要「讀取訊息歷史」和「附加檔案」兩個權限。
- 程式由 AI（Claude）協助撰寫，見 `PROMPT_LOG.md`。

**Why:**

- 使用者想在 Discord 裡只看到一個 bot，並且要有開始文字會議的指令。
- 收 Discord 的語音只能用 Node.js（`@discordjs/voice`），文字 bot 是 Python，所以不改寫任何一邊，只讓兩支程式共用帳號。
- `/meeting end` 直接向 Discord 讀那段訊息，不依賴文字記錄有沒有在跑，也符合 spec「結束後按邊界讀取可取得的成員訊息」。

**Alternative rejected:**

- 把文字 bot 改寫成 Node.js：要重寫別人的程式和測試。
- 保留兩個 bot 帳號：Discord 裡會看到兩個 bot，而且要拿到文字 bot 的 token。

**Open questions:**

- 正式任務的建立、提醒、彙報（spec R06–R10）是 AI 組的部分，這裡的待辦只是候選。
- 組長判斷還是用 Discord 身分組，spec 是由管理者設定（spec 問題 O1）。
- 文字記錄會把伺服器的歷史訊息全部存進資料庫，和 spec「一般聊天不長期完整保存」不一致（spec 問題 S3）。

**Led by:** Ping3227

## 2026-11-21 — 摘要和語音辨識都做成可換的單元；ChatGPT 版本先寫好不開；新增測試用 AI 單元 ai_demo

**Decision:**

- 摘要新增 `openai`（ChatGPT API），和 Claude 共用提示詞、格式和檢查。預設不開，現在照舊用 `claude-code`。
- 語音辨識改成可以換的引擎（`voice_stt/stt/engines.py`）：
  - `local`（預設，本機 Breeze）
  - `openai`（OpenAI 語音轉文字 API，預設不開）
  - `模組路徑:類別名稱`
- voice_bot 和 team_bot 啟動時可以加參數，只對這次啟動有效，會蓋過 `.env`：`--summarizer`、`--stt`、`--consent`、`--auto-record`。API key 只能放 `.env`。
- 錄音通知會依設定寫出「錄音交給誰轉文字」「逐字稿交給誰整理」。用本機 STT 時才寫「錄音檔不會送出去」。
- 新增 `ai_demo/`（標成測試用）：唯讀讀本機 SQLite，照 spec 做兩件事：
  - 整理任務：AI 只能提案，由程式檢查四個條件才算正式任務，其餘是待確認提案。
  - 問會議問題：只根據會議內容回答並附依據，找不到就回 `NOT_FOUND`。
  - AI 預設用 Claude Code。
- 文字會議的紀錄多存「代號對應的作者」（`speakers`），之後的 AI 功能才知道 S1、S2 是誰。
- 程式由 AI（Claude）協助撰寫，見 `PROMPT_LOG.md`。

**Why:**

- 使用者之後可能把系統搬到別人的電腦，希望摘要和語音辨識能快速換來源；啟動參數比改設定檔方便。
- AI 組的功能還沒出來，先有一個照 spec 的測試版，可以拿真資料試流程，也讓 AI 組參考。

**Alternative rejected:**

- 只用參數、不用 `.env`：每次啟動都要記得打一長串，API key 放在參數裡也不安全。
- 讓 AI 自己決定是不是正式任務：spec 規定後端要驗證，AI 說是明確指派不能取代驗證。

**Open questions:**

- `ai_demo` 不檢查 Discord 權限，只能在開發者自己的電腦上用。正式版要由 AI 組接上讀取介面和確認流程（R15、R18、ConfirmationPolicy）。
- OpenAI 的摘要和語音辨識都沒有實際呼叫過（沒有 API key，而且要付費）。

**Led by:** Ping3227
