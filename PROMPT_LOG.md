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

## 2026-11-19 — 測試摘要與讀取介面；錄音訊息改靜音、摘要改用按鈕查看（Ping3227）

**使用者原始要求：**

> 另外我想先測試接口的功能，還有另一部分是關於對話的訊息能不能只發給進聊天室的對象就好
>
> 我想避免吵到大家

AI 用選項確認後，使用者回答：

> 摘要，以及給AI組的讀取介面
>
> 沒參加會議的人，但有在頻道的人還是能看到，其實摘要算是寫在data base 裡面，讀取是AI組的事情，不過我們這邊為了測試，請你幫我寫一下，在頻道的人都可以用按鈕call 摘要或...

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**產出：**

- `meeting_ai/show_session.py`：替某個人讀一場錄音的摘要或逐字稿。
  - 只透過 `AuthorizedTranscriptReader`（Discord 當下確認權限）讀。
  - 回傳 `ok` 或拒絕原因：`denied`、`unavailable`、`not_found`、`no_summary`。
  - 要在 `discord_bot/.venv` 執行。
- `voice_bot/src/commands.js`：
  - 頻道訊息全部靜音。
  - 結束時只用一則訊息更新進度。
  - 摘要不再貼出來。
  - 新增「查看摘要」「查看逐字稿」按鈕，只有按的人看得到；內容太長時改成附件。
- `voice_bot/src/ingest.js`：新增 `runShow`。
- `voice_bot/src/config.js`、`check.js`：新增 `READER_PYTHON`，預設 `discord_bot/.venv`。
- README（voice_bot、meeting_ai）、`docs/ai_memory_api.md`、DECISIONS。

**檢查：**

- 新增 6 項 Python 測試：
  - 看得到頻道的人拿到摘要和名字
  - 看不到的人什麼都拿不到，連名字都不查
  - Discord 無法確認時不回傳
  - 找不到會議或沒有摘要
  - 摘要過時會標註
  - 逐字稿標出可能聽錯的句子
- Node 新增按鈕相關測試，共 13 項通過；meeting_ai 8 項、voice_stt 25 項、discord_bot 24 項也都通過。
- 用真的 Discord 和資料庫裡的會議實測讀取介面：
  - 使用者本人讀得到摘要和逐字稿
  - 不在伺服器的人被拒（`denied`）
  - 不存在的會議回報 `not_found`
  - 每次約 6 秒

**尚未驗證：** 在 Discord 裡實際按按鈕，以及靜音訊息的樣子。要等下一次錄音時確認。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-19 — 拿掉「草稿、待確認」字樣，推一版暫時分支（Ping3227）

**使用者原始要求：**

> （關於「兩份介面都標著草稿，待 Alex、claire 確認」）這個不用寫給他們看
>
> 先推一版吧，記得註明是tmp

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**產出：**

- 拿掉 `docs/ai_memory_api.md`、`meeting_ai/README.md`、`voice_stt/README.md` 裡「草稿、待確認」的字樣。
- `voice_bot/test/units.test.js` 的長度測試改用假的頻道 ID（原本誤用了真的語音頻道 ID）。
- 推到 GitHub 的暫時分支 `ping-voice-tmp`，commit 訊息開頭標 `[tmp]`。沒有開 PR。

**檢查：**

- 推之前掃描這次要推的所有 commit：沒有 token、API key、真實的 Discord ID，也沒有錄音、資料庫或 `.env` 檔。
- 五組測試全部通過。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-20 — 用 Claude Code 做會議摘要（Ping3227）

**使用者原始要求：**

> 可不可以幫我做裡面的摘要處理，我指的是說，傳回claude code 程式裡面再用claude code 都方法call

（承接前面的討論：想讓 app 在需要時呼叫已登入訂閱的 Claude Code，平常不消耗 token）

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版；查證文件用了 claude-code-guide 子代理

**產出：**

- `meeting_ai/claude_code.py`：`ClaudeCodeSummarizer`。
  - 用 `claude -p --output-format json --json-schema` 取得固定格式的摘要；逐字稿從標準輸入送入。
  - 安全設定：空資料夾執行、無工具、無 MCP、不存對話、權限詢問一律拒絕、不使用 API key。
  - 「S2（皓元）」這種負責人寫法會整理成「S2」，貼到 Discord 才會變成名字。
- `meeting_ai/interface.py`：`get_summarizer("claude-code")`。
- `voice_bot`：
  - `npm run check` 會確認找得到 `claude` 指令。
  - 摘要器會送出文字時，同意訊息多一行說明。
  - `.env` 設定 `MEETING_SUMMARIZER=claude-code`。
- README（meeting_ai、voice_bot）、`.env.example`、DECISIONS。

**檢查：**

- meeting_ai 新增 7 項測試，用假的 `claude` 指令，不會真的送出：
  - 輸入方式與安全參數
  - 濾掉不存在的行號
  - 負責人整理成代號
  - 接受寫成文字的 JSON
  - 錯誤處理
  - 找不到 claude 指令
  - 不會帶 API key
- Node 13 項（含新的設定與同意訊息判斷）、voice_stt 25 項、discord_bot 24 項、讀取介面 6 項，全部通過。
- 實際執行兩次（結果只印出來，沒有寫進資料庫）：
  - 3 句的假會議：約 7 秒，有 `structured_output`。
  - 2026-11-20 只有 ping 的那場：19 句、5.6 秒，回報「沒有明確決定或待辦」，沒有亂編。

**尚未驗證：** 錄音結束後 bot 自動用 `claude-code` 產生摘要的完整流程，要等下一次錄音。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-20 — 有人進語音頻道就自動錄音（Ping3227）

**使用者原始要求：**

> 需求想要改成，有人進入語音通話時只要bot 上線就自動進行錄音狀態

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**產出：**

- `voice_bot/src/commands.js`：
  - 有人進語音頻道 3 秒後自動開始，bot 剛上線時也會檢查一次。
  - 選人最多、允許、可加入、非 AFK、沒被組長手動停掉的頻道（`pickAutoChannel`）。
  - 手動和自動開始共用同一段流程（`#begin`）。
  - 自動開始卻沒錄到任何東西時，收回訊息、刪掉空資料夾。
  - 錄完會再找其他有人的頻道。
- `voice_bot/src/config.js`：`AUTO_RECORD`（預設開）、`AUTO_RECORD_CHANNELS`。
- `voice_bot/src/index.js`、`check.js`：啟動時顯示並檢查自動錄音設定。
- `.env.example`、README、DECISIONS。

**檢查：** Node 15 項測試通過，新增：

- 頻道選擇：人最多、AFK、被手動停掉、不能加入、限定頻道
- 設定解析：預設開、可關掉、頻道清單格式

**尚未驗證：** 在 Discord 實際進出語音頻道的自動開始與結束，要等使用者測試。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］


## 2026-11-20 — 拒絕原因改用 spec 的錯誤代碼（Ping3227）

**使用者原始要求：**

> （回覆「錯誤原因要用英文代碼，例如 ACCESS_DENIED_USER、SOURCE_UNAVAILABLE_BOT、NOT_FOUND…改名很快」）ok

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**產出：**

- `meeting_ai/show_session.py`：拒絕時回傳 `error_code`（`ACCESS_DENIED_USER`、`PERMISSION_UNVERIFIED`、`NOT_FOUND`）和給人看的 `message`。
- `voice_bot/src/commands.js`：直接顯示 `message`，拿掉自己的訊息對照表。
- 測試、`meeting_ai/README.md`、`voice_bot/src/ingest.js` 註解、DECISIONS。

**檢查：** voice_bot 15 項、meeting_ai 15 項（1 項略過）、show_session 6 項測試通過；拒絕的三種情況都改成檢查新代碼。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］


## 2026-11-20 — 確認 Claude Code 摘要在 bot 的環境跑得動；共同負責人也顯示名字（Ping3227）

**使用者原始要求：**

> 另外你先實作我剛剛提的claude code local AI摘要

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**產出：**

- 確認 `claude-code` 摘要器（先前已完成）照 bot 的方式執行可以成功：
  - 用 bot 的指令 `python -m meeting_ai.summarize_session`，`MEETING_SUMMARIZER=claude-code`。
  - 測試資料是 `Demo_Script.md` 的 30 句對話，放在暫存資料庫，沒有用到真實錄音。
  - 約 21 秒完成，得到 9 項決定、8 項待辦。
  - 在一般終端機（沒有 Claude Code 桌面版的環境變數）也能用本機登入的帳號執行 `claude -p`。
- `meeting_ai/interface.py`：待辦的負責人是「S1、S2」時，兩個標籤都換成名字（原本只換得了單一標籤）。
- 測試：新增共同負責人的顯示測試（S12 不會被誤認成 S1）。

**檢查：** meeting_ai 16 項（1 項略過）、show_session 6 項測試通過。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-20 — 用舊錄音測查看按鈕；摘要文字不寫行號（Ping3227）

**使用者原始要求：**

> 現在的摘要按鈕可以測試原先之前錄的檔案嗎，我需要setup甚麼嗎

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**產出：**

- 查了資料庫：6 場舊錄音都有逐字稿，摘要都是當時的關鍵字版（`keyword-rules`）。
- 只有使用者本人說話的那場（11/20 16:49）改用 `claude-code` 重新摘要，覆蓋舊摘要。有組員的那場沒動：錄音時沒告知逐字稿會交給 Claude。
- `meeting_ai/claude.py` 的提示詞加兩條規則，版本改成 `claude-2`：
  - 摘要文字裡不寫資料庫行號（原本會出現「第 72～90 行」）。
  - 文字裡提到人時用名字，不用 S1 這種代號。

**檢查：** meeting_ai 16 項測試通過（1 項略過）；同一場重跑後，摘要裡沒有行號和代號。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-20 — 4 人測試錄音改用 Claude Code 重做摘要（Ping3227）

**使用者原始要求：**

> 他們同意了，重做

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**產出：** 4 人那場（11/20 16:54）的摘要改用 `claude-code`（提示詞 `claude-2`）重做，覆蓋原本的關鍵字版。約 8 秒完成：0 項決定、2 項待辦，並且標明內容主要是測試收音和閒聊。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-20 — 語音頻道改成進來就錄（Ping3227）

**使用者原始要求：**

> agent進到語音聊天是不需要詢問同意，進來的人就是直接問
> （追問選項後）直接錄，我講錯了

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**產出：**

- `voice_bot/src/consent.js`：新增 `included` 狀態（沒按任何按鈕就被錄）。按過「不要錄我」的人不會再被自動加入。
- `voice_bot/src/config.js`：`CONSENT_MODE`，可設 `direct`（預設）或 `ask`。
- `voice_bot/src/commands.js`：
  - 開始時把頻道裡的人都加入錄音，中途進來的人也加入並 @ 他告知。
  - 按鈕改成「不要錄我」「繼續錄我」。
  - `/record status` 改成列出正在錄的人。
- `recorder.js`、`index.js`、`check.js`、`.env.example`、README、DECISIONS 跟著更新。

**檢查：** voice_bot 17 項測試通過；新增「按了不要錄我、重新進來也不會再錄」和設定解析的測試。`npm run check` 顯示「錄音同意：direct」。

**尚未驗證：** 在 Discord 實際進出語音頻道。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-20 — 摘要器做得更有彈性，方便換成 API 或其他來源（Ping3227）

**使用者原始要求：**

> 阿claude 摘要的部分希望你可以做的彈性一點，我之後有機會的話也許能換成api，也就是我可以很容易改成其他來源的

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**產出：**

- `meeting_ai/llm.py`（新）：`LLMSummarizer`，提示詞、格式、解析和檢查共用，子類別只寫 `generate()`。
- `meeting_ai/claude.py`、`claude_code.py`：改成它的子類別。Claude API 的呼叫方式沒有變。
- `meeting_ai/interface.py`：`MEETING_SUMMARIZER` 支援「模組路徑:類別名稱」。
- `voice_bot/src/config.js`、`commands.js`：錄音通知改用 `summaryRecipient`，可以用 `MEETING_SUMMARY_SENDS_TO` 指定名稱。
- README、`.env.example`、測試、DECISIONS。

**檢查：**

- 測試全部通過：
  - meeting_ai 18 項（1 項略過）。新增兩項：「新來源只寫 generate()」、「用模組路徑掛上」。
  - show_session 6 項。
  - voice_bot 17 項。
- 用 Demo_Script 假會議實際跑一次 claude-code：11 項決定、9 項待辦。
- Claude API 沒有實際呼叫（要付費）。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-21 — 合併語音 bot 和文字 bot；新增文字會議指令（Ping3227）

**使用者原始要求：**

> 我可以把語音bot 跟文字bot 合併嗎，原先文字bot先不要刪掉，然後文字bot 現在的功能我不確定完成到哪了，但像之前說的有一些功能要有，比如指令，開始文字會議
> （選擇）同一個 bot 帳號；文字會議做基本可用版

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**產出：**

- `voice_bot/src/meetings.js`（新）：`/meeting start|end|status`。進行中的會議記在檔案裡，重開 bot 不會遺失；結束時讀兩則 bot 訊息之間的發言，貼出紀錄。
- `voice_bot/src/index.js`：註冊 `/record`、`/meeting`、`/ping`；啟動時提醒有沒有開 Message Content Intent。
- `voice_bot/src/ingest.js`：Python 步驟可以從標準輸入接資料；新增 `runTextMeeting`。
- `voice_bot/src/config.js`：邀請權限加上「讀取訊息歷史」「附加檔案」。
- `meeting_ai/summarize_text_meeting.py`、`text_meeting_store.py`（新）：文字會議的摘要與存檔。
- `team_bot/`（新）：`start.mjs` 一起啟動兩支程式；`text_logger.py` 用同一個帳號跑原本文字 bot 的記錄、不註冊指令；README 寫了設定步驟。
- `discord_bot/` 沒有改。

**檢查：**

- voice_bot 18 項測試通過，新增「只取會議範圍內、人寫的、有文字的訊息，照時間排」的測試。
- meeting_ai 21 項通過（1 項略過），新增文字會議的轉換、存檔、指令列測試。
- 用假資料實際跑一次 Node → Python：摘要和存檔都正常。

**尚未驗證：**

- 在 Discord 實際用 `/meeting`。
- 文字記錄用同一個帳號登入：要先在 Developer Portal 開權限。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-21 — ChatGPT 版摘要、可換的語音辨識、啟動參數、測試用 AI 單元（Ping3227）

**使用者原始要求：**

> 幫我寫一下claude code 摘要改成用chatgpt api 使用的版本，我現在還是使用原本的，事之後如果換到別人電腦上，希望方便快速能改，另外還有STT也是，摘要跟STT都幫我寫成容易換掉的獨立unit，我是指說這些功能都先不開啟，我在思考會是讓他開啟程式時，輸入args 決定用甚麼是不是比較好操作，另外拿取資料的接口，先假設在我local 端，拿資料庫這邊的系統你是寫好的嗎，寫好的話我在想你可能就先寫幾個簡單的東西，這是一個獨立的unit 可以拿sqlite 的東西，然後去做後面那邊AI要做的功能，你甚至可以自己先做完，我們標成測試，然後跟摘要那邊一樣先使用claude code 本身的做
> 記得要參照spec

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**產出：**

- `meeting_ai/openai_summarizer.py`（新）：ChatGPT API 摘要器（structured outputs），預設不開。
- `voice_stt/stt/engines.py`、`openai_engine.py`（新）：可換的語音辨識引擎；`ingest_recording` 加 `--engine`。
- `voice_bot/src/config.js`、`index.js`、`check.js`、`commands.js`：啟動參數（`argsToEnv`）、STT 的告知文字、檢查 OpenAI 設定。
- `team_bot/start.mjs`：啟動參數轉給 voice_bot，`--help`。
- `ai_demo/`（新，測試用）：`local_data.py`（唯讀讀 SQLite）、`tasks.py`、`ask.py`、`cli.py`、README、測試。
- `meeting_ai/text_meeting_store.py`：多存 `speakers`。
- 各 README、`.env.example`、DECISIONS。

**檢查：**

- 測試全部通過：
  - voice_bot 19 項，新增啟動參數和 STT 告知的測試。
  - meeting_ai 25 項（2 項略過），新增 OpenAI 摘要器的假 client 測試。
  - voice_stt 30 項，新增引擎選擇和 OpenAI 引擎的假 client 測試。
  - ai_demo 6 項。
- 用 Demo_Script 假會議和 Claude Code 實際跑 ai_demo：
  - 整理任務約 31 秒：正式任務 0 項、提案 12 項。原因是劇本大多沒講期限，或不是組長說的。
  - 問「誰負責期中考出題」有答案和依據；問「期末考在哪一天」回 `NOT_FOUND`。
- OpenAI 沒有實際呼叫。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-21 — Discord 測試指令 /ai（Ping3227）

**使用者原始要求：**

> 我是說你有沒有一些可以直接跟bot 互動的功能，我要用這個測試，然後這個bot 互動單元會去用那個api拿取東西

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**產出：**

- `voice_bot/src/ai.js`（新）：
  - `/ai tasks`、`/ai ask`。
  - 會議選項可以打字搜尋，只列出看得到的頻道裡的會議。
  - 先檢查權限（`accessTo`），結果只回給本人。
- `voice_bot/src/index.js`：註冊 `/ai`；指令分派改成一張對照表。
- `voice_bot/src/ingest.js`：`runAiDemo`。
- `ai_demo/cli.py`：`--bot` 模式，Discord ID 用字串；錯誤照 spec 的錯誤代碼。
- `ai_demo/engine.py`：沒指定時跟著目前的摘要器。
- 測試、README、DECISIONS。

**檢查：**

- voice_bot 20 項、ai_demo 7 項測試通過。
- 從 Node 實際呼叫：
  - 列出真實資料庫的 6 場會議，頻道 ID 是字串。
  - 對 Demo_Script 假會議問「小考是紙本還是電腦作答」，Claude Code 4 秒回答並附依據。

**尚未驗證：** 在 Discord 實際下 `/ai`。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-21 — 資料怎麼從 SQLite 拿、資料庫架構、詢問是否追蹤進度（Ping3227）

**使用者原始要求：**

> 我試了，所以目前接口是好的對嗎，我問的這些問題個別都是怎麼從sqlite 拿data的，另外我想要sqlite 存資料的資料庫架構，我說我們現在有存的這些東西，在來你能先簡單做一個詢問是否要追蹤進度的程式嗎

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**產出：**

- `docs/database_schema.md`（新）：所有資料表、關係圖、每個功能讀寫哪些表。
- `ai_demo/tracking.py`（新）：`demo_tasks`、`demo_inquiries`、`demo_progress_updates`。
  - 確認不重複建立任務。
  - 只有負責人能回報。
  - 送不出去的詢問不算沒回。
- `ai_demo/cli.py`：新增 `track`、`inquiry`、`progress`、`tracked`；`--stdin` 接 bot 傳來的資料。
- `ai_demo/local_data.py`：文字會議可以用 bot 當場讀到的原文。
- `meeting_ai/summarize_text_meeting.py`：被 @ 的人也有代號，`<@id>` 換成「@名字（S3）」。
- `voice_bot/src/ai.js`：
  - 「追蹤」按鈕、私訊詢問、處理負責人回報、`/ai tracked`。
  - 文字會議當場讀原文。
- `voice_bot/src/meetings.js`：讀會議訊息的函式拿出來共用；記錄被 @ 的人。
- `voice_bot/src/index.js`：接受私訊裡的進度按鈕。
- 測試、README、DECISIONS。

**檢查：**

- 測試全部通過：voice_bot 21 項、ai_demo 11 項、meeting_ai 26 項（2 項略過）。
- 用暫時資料庫從 Node 實際跑追蹤流程：
  - 建立、重送不重複、記詢問都正常。
  - 別人回報被拒（`ROLE_REQUIRED`）。
  - 負責人回報後狀態變成 `in_progress`。
- bot 紀錄裡，使用者前面試的 `/ai` 沒有錯誤。

**尚未驗證：** 在 Discord 實際按追蹤、收私訊、回報。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-21 — 給 AI 組的說明文件、假資料庫、對照 spec 檢查（Ping3227）

**使用者原始要求：**

> 確定我這邊要給AI端那邊的功能暫時都是可以用的，做一個說明檔案，說明如何使用包含啟用測是那些相關用得到的功能，然後也檢查有沒有按照spec

（前一輪的討論：要不要 push 含語音資料的 SQLite 和開 SQL API 給 AI 組測試。）

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**產出：**

- `docs/ai_team_guide.md`（新）：
  - 有哪些功能可以用。
  - 在自己電腦上怎麼測（假資料庫、讀取介面、ai_demo）。
  - 在 Discord 上怎麼測，以及啟動選項。
  - 對照 spec v1.1 的結果。
- `demo_data/`（新）：`make_demo_db.py`、`fake_access.py`、`try_readers.py`、`test_demo_data.py`、README。
- `ai_demo/tracking.py`：完成後負責人不能再改；按鈕回報後詢問結案。
- `ai_demo/local_data.py`：
  - 讀完資料庫會關閉連線（原本 Windows 會鎖住檔案）。
  - 在終端機讀文字會議時，@ 的人也換成代號。
- `voice_bot/src/ai.js`：
  - Bot 讀不到來源時，回覆 `SOURCE_UNAVAILABLE_BOT`。
  - AI 跑完、送出前再確認權限（AC23）。
  - 私人討論串要確認成員（AC26）。
  - 結果不明的私訊記成 `delivery_unknown`。
- 測試、README、`docs/database_schema.md`、`.gitignore`（`demo_data/out/`）、DECISIONS。

**檢查：**

- 測試全部通過：
  - voice_bot 21 項。
  - discord_bot 24 項。
  - demo_data 3 項。
  - ai_demo 12 項。
  - meeting_ai 26 項（2 項略過）。
  - voice_stt 30 項。
- 用 main 上的 `Demo_Script.md` 實際產生假資料庫：
  - `try_readers.py` 的 7 個例子都正確，包括允許、拒絕、找不到、無法確認。
  - `ai_demo tasks` 用 Claude Code 跑文字會議，得到 1 項正式任務和 10 項提案。
- bot 已重開，跑的是新程式。

**尚未驗證：** 在 Discord 上實際試追蹤按鈕、私訊、回報，以及 AC23、AC26 的新檢查。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-22 — 統一 SQLite API、搬移資料庫並集中環境設定

**使用者原始要求：**

> 將讀取/寫入SQL Llite的介面統一到一個file內，並寫幾個tests確保運作正常。同步更新html
>
> sqlite_access.py檔案放置的位置不太合理，因為其他資料夾的檔案會使用它，建議我好方法。檔案名稱改為sqlite_api.py

接續提出三項要求。

> 1. 將discord_bot的data資料夾以及其內容移動至根資料夾，並同步修改其他相關程式，確保相依性
> 2. 未來其他合作開發者會根據 sqlite_api.py 中的api讀寫SOL的文字資料，以進行AI tool的設計。請統一各function的命名方式。請寫好google docstring和SQL_API_README.md。
> 3. 使環境設定方式可以統一在根資料夾設定，而不用各別到discord_bot或voice_stt資料夾內分別設定

**使用者選擇：** 採用根目錄的 `sqlite_api.py` 與單一 `SQLiteStore`，移除舊儲存模組，Discord 權限檢查由獨立的 reader 負責。兩個 Python 虛擬環境各自安裝共用 API，執行設定集中在同一份根目錄 `.env`。

**實作提示：** 使用者以「PLEASE IMPLEMENT THIS PLAN」核准實作，要求保留既有資料與資料表行為、更新所有呼叫端、驗證搬移前後結果，並同步更新開發者文件及流程圖。

**模型／工具：** Codex（GPT-6 系列），搭配本機 SQLite、Python unittest／pytest 與 Node 測試。

**產出：**

- 將文字訊息、語音逐字稿和會議摘要的 SQLite 操作集中到 `sqlite_api.py`，以 `list_recent_messages`、`save_historical_message` 等動詞開頭的方法統一命名，並補上 Google-style docstring。
- 將本機 `discord_bot/data/` 搬到根目錄 `data/`，所有入口採同一預設路徑。支援以 `BOT_DB` 指定共用資料庫，CLI 可用 `--db` 個別覆寫。
- 新增根目錄 `.env.example`，集中 `TEXT_BOT_TOKEN`、`VOICE_BOT_TOKEN`、`DISCORD_GUILD_ID` 和摘要相關設定。將本機既有文字 Bot 設定帶入根目錄 `.env`。
- 新增 [SQL API 使用指南](SQL_API_README.md)，同步更新根目錄安裝指令、[AI 授權讀取說明](docs/ai_memory_api.md)與[系統流程圖](docs/SystemWorkflow.html)。文件依目前程式說明 `meeting_ai` 的 OpenAI 摘要選項。

**檢查：** 搬移前後 `PRAGMA quick_check` 均為 `ok`，27 筆訊息、3 筆匯入進度與 0 筆刪除標記一致。75 項 Python 測試與 13 項 Node 測試通過，另確認文件範例、`BOT_DB`／`--db` 優先順序及離線設定檢查。

**尚未驗證：** 實際連線 Discord、以真實音檔轉寫，以及實際呼叫 OpenAI 摘要 API。本機的語音 Bot Token 欄位仍待填寫。

**我改了什麼、為什麼：** 將共用 API 與資料庫放在根目錄，讓各元件可以從同一個入口取得資料，也讓合作開發者能從文件找到正確用法。保留兩個 Python 環境以分開文字 Bot 與語音辨識的依賴，並集中設定，減少不同元件讀到不同路徑或憑證的機會。

## 2026-11-22 — 說明檔補上語音和文字 bot 合併（Ping3227）

**使用者原始要求：**

> 阿你沒有寫voice 和text bot合併喔?

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**產出：** `docs/ai_team_guide.md`

- 第一節總表加上合併版 bot（`team_bot/`）和文字訊息記錄。
- 第四節說明一個 bot 內部跑兩支程式，以及 `node team_bot/start.mjs` 和 `npm start` 的差別（後者沒有文字記錄）。
- 開頭的分支名稱改成 GitHub 上的 `ping-voice-tmp`。

**檢查：** 內容對照 `team_bot/README.md`，只改文件，沒有改程式。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-22 — 說明檔擴寫語音 bot（Ping3227）

**使用者原始要求：**

> 你先擴寫一下voice bot 吧

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**產出：** `docs/ai_team_guide.md` 新增第二節「語音 bot：從錄音到你們拿得到資料」，後面各節往後編號。

- 流程圖、什麼時候錄和錄誰。
- 逐字稿的特性：說話的人是準的、句子怎麼切、時間、`text` 和 `text_raw`、`confidence`、四種 `flags`、名字放在哪。
- 摘要格式、`is_stale`、誰看得到、資料在哪、限制。

**檢查：** 數字和行為都對照程式確認過：`SILENCE_MS` 800、合併間隔 3 秒／最長 60 秒、最短 0.3 秒、自動錄音延遲 3 秒、flags 名稱、`session_id` 格式、摘要欄位。只改文件，沒有改程式。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-22 — 檢查皓元重構後的連接，統一到 team_bot（Ping3227）

**使用者原始要求：** 轉貼皓元在 Discord 說的話：

> 目前應該是爛的，主要是我把discord_bot名稱改成text_bot，並且根目錄下有sqlite_api，統一所有元件讀寫SQL的API
> 我覺得可以的話，你讓AI檢查一遍確保各項連接沒問題，然後統一文字/語音功能到team_bot

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**做法：** 在另一個資料夾（worktree，分支 `ping/merge-fix`，從 `ping-voice-tmp-merge` 的 `42def15` 開始）檢查和修改，主機上原本的資料夾沒有動。

**產出：**

- `meeting_ai`：摘要器補回 `claude-code` 和「模組:類別」；`openai.py` 補 import、加 `generate()`；刪除重複的 `openai_summarizer.py` 和它的測試；測試補上 import。
- `voice_bot`：`index.js` 改讀根目錄 `.env`；測試改用 `VOICE_BOT_TOKEN`；說明文字更新。
- `team_bot`：`text_logger.py`、`start.mjs` 改用 `text_bot/`、`sqlite_api`、根目錄 `.env` 和 `VOICE_BOT_TOKEN`。
- `ai_demo`、`demo_data`、`meeting_ai/summarize_text_meeting.py`：改用 `sqlite_api` 和新的資料庫路徑。
- `.env.example`、根目錄 README、各資料夾 README、`docs/ai_team_guide.md`、`docs/database_schema.md`、DECISIONS。

**檢查：**

- 修改前：text_bot、voice_stt 通過；meeting_ai 7 項失敗、查看按鈕 3 項錯誤、voice_bot 4 項失敗，ai_demo 和 demo_data 無法載入。
- 修改後全部通過：text_bot 34、查看按鈕 7、demo_data 3、voice_stt 30、meeting_ai 26（1 略過）、ai_demo 12、voice_bot 21。text_bot 的環境是照 SETUP 的方式另建的（`pip install -e .`）。
- 實際跑 bot 會呼叫的程式：假資料庫、讀取介面 7 個例子、`ai_demo list/show`、摘要、三個 `--help` 都正常；`ai_demo tasks` 用 Claude Code 跑出 1 項正式任務和 10 項提案，和重構前一樣。

**尚未驗證：** 在 Discord 上實際啟動合併版；主機上的資料庫和 `.env` 還沒搬到新位置；OpenAI 沒有實際呼叫。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-22 — 統一文字會議的資料庫存取和 OpenAI 提示詞（Ping3227）

**使用者原始要求：**

> 你能夠統一一下他們嗎，你有建議怎麼做嗎

（指上一輪留下的兩件事：文字會議紀錄沒有走 `sqlite_api`、OpenAI 摘要用舊的提示詞。）

**模型／工具：** Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code 桌面版

**產出：**

- `sqlite_api.py`：新增 `text_meetings` 表、`save_text_meeting()`、`get_text_meeting()`；`delete_channel`、`delete_guild` 一起刪文字會議紀錄。
- 刪除 `meeting_ai/text_meeting_store.py`；`summarize_text_meeting.py`、`demo_data/make_demo_db.py` 和測試改用 `SQLiteStore`。
- `meeting_ai/openai.py`：改繼承 `LLMSummarizer`，刪掉自己那份提示詞；`llm.py` 的 `PROMPT_VERSION` 改成 `meeting-3`。
- 測試：`test_sqlite_api.py` 加文字會議的存取和刪除；`test_meeting_ai.py` 加「OpenAI 用共用提示詞」和 `generate()`。
- 文件：`SQL_API_README.md`、`docs/database_schema.md`、`meeting_ai/README.md`、DECISIONS。

**檢查：** 全部通過：text_bot 35、查看按鈕 7、demo_data 3、voice_stt 30、meeting_ai 27（1 略過）、ai_demo 12、voice_bot 21。重新產生假資料庫後，文字會議紀錄可以從 `get_text_meeting()` 讀回來，`try_readers` 7 個例子和 `ai_demo list` 都正常。

**我改了什麼、為什麼：** ［待 Ping3227 填寫］

## 2026-11-25 — Week 12 AI usage guidelines

- **Prompt:** Add the three revised Lab 12 rules to the repository and open a PR.
- **Tool:** Codex.
- **Produced:** Added the rules to `docs/ai-usage-guidelines.md` and linked the guide from `README.md` so teammates can find it.
- **Checks:** Compared the three rules with the lab submission and checked the relative links and diff.
