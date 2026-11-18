# AI Prompt Log

## 2026-10-28 — Discord bot starter

- **Prompt 1:** 「以python在專案資料夾內初始化一個discord bot的內容」
- **Prompt 2 (path correction):** 「不對，應該要在這 D:\HaoYuan\course\AISP\2026_AISP」
- **Model/tool:** Codex (GPT-6 family), with local Python checks.
- **Produced:** `discord_bot/bot.py`, dependency list, environment template, ignore rules, and setup README. Added a link in the project README and a decision entry.
- **Changes and why:** The first draft was placed in the chat workspace. It was moved into this repository after the user specified the intended path. The bot files live in a subfolder because the repository already had its own README.
## 2026-10-28 — Discord message logging

- **Prompt:** 「我想讓bot有能log伺服器每個頻道內文字的能力，作為未來AI的記憶」
- **Clarification:** 使用者選擇「也要匯入歷史訊息」。
- **Model/tool:** Codex (GPT-6 family), official Discord and discord.py documentation, local Python checks.
- **Produced:** 新增訊息儲存、歷史匯入與續傳、即時新增／編輯／刪除事件處理，以及本機測試。更新設定與使用說明。
- **Changes and why:** 記錄範圍限於設定的單一伺服器和 bot 有權讀取的頻道；SQLite 保留頻道 ID，供未來查詢時執行權限隔離。Discord 訊息內容不能用於訓練模型，這次沒有加入 AI 查詢功能。
- **Checks:** 5 個本機測試通過；未提供 Bot Token 或伺服器 ID，因此未實際連線匯入。
## 2026-11-17 — 頻道可見性與授權讀取

**使用者原始要求：**

> 1. 想讓bot能分辨不同文字頻道內的訊息，並知道這些文字頻道只有那些人看得到
> 2. 此project會和其他人合作，所以在撰寫任何文件必須要讓其他人看得懂

**使用者選擇：** 可見成員名單加讀取時權限檢查；先供程式內部使用；文件中文為主、專有名詞用英文；以查詢當下權限為準；涵蓋所有已記錄內容，包括私人討論串。

**實作提示：** 使用者要求「PLEASE IMPLEMENT THIS PLAN」，並提供以下完整規格：

> # Discord 頻道可見成員與訊息存取規劃
>
> ## 摘要
>
> 現有訊息已保存 `guild_id` 與 `channel_id`，因此無須搬移資料。新增一個依 **Discord 查詢當下權限**計算可見成員的內部服務，並讓未來的訊息讀取一律經過權限檢查。涵蓋目前會記錄的頻道及公開、私人討論串。
>
> ## 實作變更
>
> - 新增 `channel_access.py`：以頻道 ID 取得目前名稱、類型、所屬頻道及可見成員的 ID／顯示名稱。使用 `guild.fetch_members()` 取得完整成員名單，再以 `permissions_for(member).view_channel` 判斷一般頻道；不保存權限快照。完整名單需要啟用 [Members Intent](https://discordpy.readthedocs.io/en/stable/intents.html#retrieving-members)。
> - 私人討論串另核對成員資格或父頻道的 `manage_threads` 權限；僅檢查父頻道權限不足以判定私人討論串可見性。[discord.py 討論串說明](https://discordpy.readthedocs.io/en/latest/migrating.html#thread-support)
> - 提供內部 `can_read_history(member_id, channel_id)` 與經授權的近期訊息讀取介面。讀取舊訊息須同時具備 `view_channel`、`read_message_history`，私人討論串還須通過成員資格檢查。頻道、成員或權限無法確認時拒絕讀取，不回傳部分名單。
> - `bot.py` 啟用 Members Intent；以穩定的頻道 ID 區分儲存資料，顯示名稱在查詢時取得，以反映改名。這一階段只提供程式內部介面，不新增公開斜線指令或 AI 回答功能。
>
> ## 驗證與文件
>
> - 測試不同頻道的成員覆寫、角色權限、管理員權限、私人討論串邀請、權限撤銷，以及 Discord 查詢失敗時拒絕讀取；確認不能用另一頻道的權限取得訊息。
> - 更新 bot README、`DECISIONS.md` 與 `PROMPT_LOG.md`。文件以**中文為主、專有名詞保留英文**，用兩個頻道和不同可見成員的例子說明資料流、權限設定與使用限制。
>
> ## 已確認的預設
>
> 可見名單與讀取權限都依查詢當下狀態計算；成員失去權限後不能再透過 bot 讀舊訊息。名單只列人類成員，不持久保存。實作後仍需在 Discord Developer Portal 啟用 Members Intent，並以測試伺服器驗收實際權限結果。

**模型／工具：** Codex（GPT-6 系列）、本機 Python／discord.py 2.7.1、官方 discord.py 文件。

**產出與調整：** 新增 `channel_access.py` 與權限測試，修改 `bot.py` 啟用 Members Intent 並提供內部授權讀取服務；更新 bot README。依檢查結果，討論串父頻道權限改為每次重新取得，避免使用快取的舊權限。未改動訊息資料庫 schema。

**檢查：** 在專案的 `.venv` 中執行 10 項本機測試全部通過；尚未使用測試伺服器驗證實際 Discord 權限設定。

## 2026-11-18 — 語音轉文字模組 `voice_stt/`（Ping3227）

**使用者原始要求：**

> 你就先按照這個分工做，然後別人的part你最多寫一些簡單的東西測試，我們後面再考慮要不要寫完

**前情：** 同一段對話中先討論並同意了計畫：第一步只做「給一個音檔 → 輸出台灣繁體逐字稿」，使用 Breeze-ASR-25 + faster-whisper、VAD、OpenCC、幻覺過濾、低信心標記；先不接 Discord 與資料庫。之後依團隊開發分支，從 `services/stt/` 改放到根目錄的 `voice_stt/`，與 `discord_bot/` 並列。

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版；本機 Python 3.11、faster-whisper 1.2.1、CTranslate2 4.9.0、OpenCC 1.4.2。

**產出：** 根目錄 `.gitignore`（擋 `.env`、錄音、逐字稿、資料庫、`.venv`）；`voice_stt/stt/`（`schema.py`、`engine.py`、`postprocess.py`、`output.py`、`cli.py`、`cuda_dlls.py`）；13 個不需下載模型的單元測試；`voice_stt/README.md`、`requirements.txt`、`glossary.example.txt`；`DECISIONS.md` 新增一筆。

**檢查：** `pytest` 13 項通過；CTranslate2 偵測得到 RTX 5070 Ti，支援 float16／int8。尚未下載模型做實際辨識。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-18 — 語音逐字稿進資料庫＋給 AI 組的讀取介面（Ping3227）

**使用者原始要求：**

> 我理解了，你開始做吧，但我有兩個擔憂，一個是接給LLM功能那邊的api有定義嗎? 再來是，我們有沒有必要做一個資訊的暫時整理處理區，就是不是raw資料的，這樣才不用一直reprocess，這部分會式做在我們這還是LLM那邊

**前情：** 讀過皓元的 `discord_bot/` 後，提議「沿用為主、小修」：語音另開新表、沿用 `ChannelAccess`、資料庫開 WAL、AI 輸出前檢查聽眾。使用者同意後開始實作。

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版；本機 Python 3.11、discord.py 2.7、pytest／unittest。

**產出：**

- `discord_bot/transcript_store.py`、`transcript_reader.py`
- `test_transcript_store.py`（8 項）、`test_transcript_reader.py`（6 項）
- `bot.py`：建立 `transcripts` 與 `transcript_reader`；刪除頻道或被移出伺服器時一起刪除逐字稿（共 6 行）
- `voice_stt/stt/session.py`、`import_session.py`、`botdb.py`，以及 `tests/test_session.py`（4 項）
- `docs/ai_memory_api.md`
- `discord_bot/README.md`、`voice_stt/README.md` 新增說明
- `DECISIONS.md` 新增一筆

**檢查：**

- `discord_bot`：皓元原本的 10 項測試加上新增的 14 項，共 24 項通過。
- `voice_stt`：17 項通過，以假的辨識器測試合併與寫入，未使用真模型。
- 第一次執行時有一項測試因 Windows 無法刪除未關閉的 SQLite 檔而失敗；改用 `contextlib.closing` 關閉連線後通過。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-18 — 用真模型實測 `voice_stt`（Ping3227）

**使用者原始要求：** 「下載吧」（同意下載模型實測），以及「好，補上」（把實測結果記進 prompt log）。

**模型／工具：**

- Claude Opus 5.5（`claude-opus-5-5`）協助執行測試與除錯
- 辨識模型：`SoybeanMilk/faster-whisper-Breeze-ASR-25`（fp16，約 2.9 GB）
- 硬體：RTX 5070 Ti Laptop（12 GB VRAM）
- 測試音檔：Windows 內建 TTS 合成（Hanhan zh-TW、Huihui zh-CN），沒有錄任何人

**結果：**

| 測試 | 結果 |
|---|---|
| 台灣腔、中英夾雜，30 秒 | 5 句，只有 "main" 聽成 "man"；1.9 秒完成（約 15 倍速） |
| 大陸腔，19 秒 | 3 句全對；模型直接輸出繁體，OpenCC 把「軟件」改成「軟體」；1.7 秒 |
| `import_session` 兩軌（成員晚 3 秒開始） | 8 句依時間正確合併，寫入測試資料庫（暫存資料夾，未使用 `discord_bot/data/`）；用 `AuthorizedTranscriptReader` 讀回正常，沒有權限的人被拒；`journal_mode` 確認為 `wal` |
| 加上 `glossary.example.txt` | "main" 認對了，但「分支」變成「分枝」：詞彙表會把相近的字帶偏 |

另外：模型載入約 6 秒；第一次在這張 GPU 上執行要先暖機，約 15 秒，之後就是上表的速度。

**失敗 → 修改 → 再測：**

1. 第一次辨識只出現英文單字，中文全部不見。
2. 檢查 tokenizer 編解碼與 `suppress_ids`，都正常。
3. 發現問題在測試音檔：PowerShell 的 `PromptBuilder` 預設英文語系，TTS 直接跳過中文。
4. 改成指定 `zh-TW`／`zh-CN` 重新產生音檔後再測，結果正常。程式碼不需修改。

**據此調整：** 在 `glossary.example.txt` 加註：只放模型常聽錯的英文詞，並用真人錄音比較加與不加的差別。

**尚未測試：** 真人聲音（口音、語速、噪音）、兩人同時說話、Discord 即時錄音、真實的 Discord 權限設定。

## 2026-11-18 — 語音錄音 bot 與摘要介面（Ping3227）

**使用者原始要求：**

> 我覺得測試可以晚點，你先弄bot

（實作中追加）

> 你也用那個互動的mod跟我說明清楚，操作跟各種東西該怎麼使用，另外我想要簡單弄一下LLM那端的東西，但要用接口做，只是要讓我測試，之後可能會換成LLM那組的東西

**模型／工具：**

- Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版
- 套件：discord.js 14.28.1、@discordjs/voice 0.19.2（附帶 @snazzah/davey 0.1.12）、@discordjs/opus 0.11.0、prism-media 1.3.5、anthropic Python SDK 2.10.0
- 先查過 npm 的版本與 `@discordjs/voice` 的型別定義，確認 DAVE 加密與收音的 API

**產出：**

- `voice_bot/`：`src/` 共 7 個檔（config、consent、wav、manifest、recorder、commands、index、ingest）、`test/units.test.js`（8 項）、README、`.env.example`
- `voice_stt/stt/ingest_recording.py` 與 2 項測試
- `meeting_ai/`：`interface.py`、`simple.py`、`claude.py`、`summarize_session.py`，以及 8 項測試和 README
- `docs/ai_memory_api.md` 補上摘要介面說明，`DECISIONS.md` 新增一筆

**檢查：**

- voice_bot 8 項、voice_stt 19 項、meeting_ai 8 項、discord_bot 24 項測試全部通過。
- 不經 Discord 的串接測試：
  1. 用 voice_bot 自己的程式寫出錄音資料夾（合成語音，兩人，另含一位撤回者）。
  2. 由 Node 呼叫 Python 轉文字（存了 8 句，含載入模型 9.7 秒）。
  3. 摘要找出 2 項待辦，負責人正確對應到兩人。
  4. 錄音檔已刪除。
- 沒有 token 時，啟動 bot 會顯示清楚的錯誤訊息並結束。
- ClaudeSummarizer 只用假的 client 測過，沒有實際呼叫 API。

**尚未測試：** 在真的 Discord 伺服器上的收音、同意按鈕、暱稱，以及多人同時說話。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-18 — 語音 bot 的 token 設定與檢查指令（Ping3227）

**使用者原始要求：**

> 有沒有辦法你能幫我記錄一下權杖馬

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**AI 的回應：** 不建議把 token 貼進 AI 對話（對話紀錄會留存）。改成由 AI 建好 `voice_bot/.env`，由使用者自己貼上 token，再用不會顯示 token 的指令檢查。

**產出：**

- `voice_bot/src/check.js`（`npm run check`）：
  - 檢查 `.env` 的每一項。token 只顯示它屬於哪個 bot ID，不顯示內容。
  - 只向 Discord 確認 token 有效、bot 是否已在伺服器裡。還沒邀請時會印出邀請網址（權限已勾好）。
  - 加 `--offline` 可以不連網。
- `src/config.js`：新增 `botIdFromToken`、`tokenProblems`（抓「多了 Bot 」、空白、引號、格式不對）、`inviteUrl`。token 沒填時的錯誤訊息改得更清楚。
- `.env.example` 補上 `MEETING_SUMMARIZER`、`ANTHROPIC_API_KEY`（註解）。README 與互動窗格的操作手冊補上 `npm run check`。

**檢查：**

- voice_bot 9 項測試通過（新增 1 項，使用編造的 token）。
- 用編造的 token 執行 `npm run check`：離線全部 ✅；連 Discord 時正確回報「token 無效」。
- 確認 `voice_bot/.env` 被 `.gitignore` 排除。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-19 — 錄音品質診斷：保留錄音與掉封包估計（Ping3227）

**使用者原始要求：**

> 效果好像不太好，有沒有甚麼改善方案

> 不太好吧，她錄音錄出來感覺很多都不正確

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**AI 的判斷：** 第一次在 Discord 實測，7 句裡有好幾句錯（含整句變英文）。可能是錄音本身不好（例如 discord.js 有人回報 DAVE 換金鑰時會靜靜地掉封包，issue #11441），也可能是每段太短導致辨識不好。先做能分辨兩者的工具，再決定怎麼改。

**產出：**

- `voice_bot/.env` 新增測試開關 `KEEP_AUDIO=1`：轉完文字不刪錄音（只保留有同意的人）。`npm run check` 開著時會提醒。
- `src/recorder.js` 新增 `PacketCounter`：依封包抵達時間估計每段掉了多少聲音（停頓不算）。超過 10% 時在終端機警告，並把比例記在 `manifest.json` 每段的 `lost`。
- README「出問題時」補上分辨方法。

**檢查：** voice_bot 10 項、voice_stt 19 項測試通過；新增的掉封包測試涵蓋穩定、抖動、一半遺失、中間停頓四種情況。

**尚未驗證：** 真實 Discord 錄音的掉封包比例。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-19 — 錄音品質診斷（續）：DAVE 解密問題偵測（Ping3227）

**使用者原始要求：**

> 你看一下（第二次實測後）

**AI 的發現：**

- 第二次實測時 bot 沒有重開，跑的還是舊版，所以錄音照樣被刪了。
- 讀了 `@discordjs/voice` 0.19.2 的收音程式，有兩種情況會讓錄音變差，而且都不會報錯：
  1. DAVE 解密失敗時，封包會被直接丟掉，聲音因此斷斷續續。
  2. DAVE 還沒準備好時，加密中的封包會原封不動送出來。拿它解碼會變成雜音，模型就會「聽」出不存在的句子。

**產出：**

- `src/recorder.js`：
  - 開啟連線的 debug 訊息，統計 `[DAVE] Failed to decrypt` 的次數。
  - 在收音和解碼中間加一道過濾：結尾是 `FA FA`（DAVE 加密標記）的封包丟掉不解碼，並計數。
  - 每段的 `undecrypted`、整場的 `diagnostics` 記進 `manifest.json`，錄音結束時在終端機摘要。
- 新增測試：判斷加密封包（11 項全部通過）。

**尚未驗證：** 真實錄音中這兩種情況有沒有發生、發生多少。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-19 — 逐字稿的發言順序：錄音補上停頓、逐字稿用名字（Ping3227）

**使用者原始要求：**

> 感覺也要能分出彼此講話的順序

> 你可不可以幫我重開／這些調整你來做是不是比較方便比較快，我這樣也不會用錯

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**AI 的判斷：** 每一句本來就有時間，資料庫也是照時間排序。但說話者短暫停頓時，Discord 不會傳送封包，錄音檔裡就少了那段時間，同一段裡後面句子的時間會偏早，兩個人的句子可能排錯順序。

**產出：**

- `voice_bot/src/recorder.js` 新增 `ClipTimeline`：依封包抵達時間，用 Discord 的靜音封包（20 毫秒）補上停頓與漏收的空洞，讓錄音長度和真實時間一致（60 毫秒以內的延遲視為網路抖動，不補）。
- `voice_stt/stt/output.py`：`transcript.md` 改用 Discord 顯示名稱，不再顯示使用者 ID。
- 測試：voice_bot 12 項（新增補停頓與靜音封包長度）、voice_stt 20 項（新增名字顯示）全部通過。
- AI 代為在 `voice_bot/.env` 加上 `KEEP_AUDIO=1`（沒有讀取或顯示 token），停止舊的 bot（先確認沒有錄音在進行），並用新版重新啟動。

**尚未驗證：** 真實多人對話中，補停頓後的順序是否正確。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-19 — 提高辨識準確度：合併短片段、團隊詞彙表、過濾短英文雜訊（Ping3227）

**使用者原始要求：**

> 好，三項都做

（承接上一輪 AI 的建議：照稿念的實測錯字率約 9%，短片段大多辨識錯，人名和英文術語常錯）

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**怎麼決定詞彙表內容：** 用保留下來的同一段真人錄音（照稿念 10 句）重跑四次比較：

| 設定 | 錯字率 |
|---|---|
| 不加 | 9.4% |
| 名字 + 英文術語 | 10.5% |
| 名字 + 英文術語（不含 SQLite、PostgreSQL） | 10.5% |
| 只放名字 | 8.8% |

只放名字時「皓元」認對了；加英文術語則會把「SQLite」帶偏。樣本只有一段錄音，結論還不穩。

**產出：**

- `voice_stt/stt/ingest_recording.py`：
  - 同一人的片段若下一段在 3 秒內開始，而且中間沒有別人講話，就接成一段再辨識（最長 60 秒），空檔補靜音，讓時間不變。
  - 自動使用 `voice_stt/glossary.txt`。
  - 結果多回報 `pieces`（實際辨識了幾段）。
- `voice_stt/glossary.txt`：皓元、Alex、claire，並附上實測數字。
- `voice_stt/stt/postprocess.py`：3.5 秒以內、沒有中文字、把握度 < 0.6 的句子丟掉（`stray_non_chinese`）。
- README、DECISIONS 的「尚未測試」改成實測結果。

**檢查：**

- voice_stt 25 項測試通過，新增：雜訊過濾、分組不跨別人發言、接起來的音檔長度與靜音、讀不到的音檔不處理、詞彙表。
- 用保留的錄音副本和暫存資料庫跑完整流程：3 段接成 1 段，存了 17 句，「皓元」「沒有的話」都正確，結尾兩句英文雜訊也消失了。

**尚未驗證：** 兩人以上對話時，合併後的發言順序。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］
