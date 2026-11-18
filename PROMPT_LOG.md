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
