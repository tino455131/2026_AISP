# 給 AI 組：語音和資料介面使用說明（F6）

> 這份指南以合併版 Team Bot 為入口。文字記錄在 `text_bot/`，語音轉寫在 `voice_bot/voice_stt/`，環境設定與 SQLite API 位於專案根目錄。
> 標「🧪 測試」的是 AI 組正式版出來前的示範，照 `spec.md` v1.1 寫，正式版請 AI 組自己做。

## 一、有哪些東西可以用

| 東西 | 做什麼 | 狀態 | 在哪 |
|---|---|---|---|
| **合併版 bot** | Discord 裡只有一個 bot，語音錄音、所有指令、文字訊息記錄都是它（見第五節） | ✅ 可用 | `team_bot/` |
| 文字訊息記錄 | 把文字頻道的訊息存進 `messages` 表，`AuthorizedMessageReader` 讀的就是這些 | ✅ 可用（用合併版啟動才有） | `team_bot/text_logger.py`（沿用 `text_bot/`） |
| **共用資料庫介面** | 文字、語音、會議和測試追蹤共用的 SQLite 入口 | ✅ 可用 | `sqlite_api.py`，用法見 [SQL_API_README.md](../SQL_API_README.md) |
| 語音錄音 → 逐字稿 → 摘要 | 有人進語音頻道就錄音；結束後轉成逐字稿，再做摘要 | ✅ 可用 | `voice_bot/`（語音辨識在 `voice_bot/voice_stt/`）、`meeting_ai/` |
| **讀取介面** | AI 組的 tool 拿資料的入口，每次讀之前都會先確認權限 | ✅ 正式用 | `text_bot/transcript_reader.py`、`text_bot/channel_access.py` |
| 摘要介面 | 換摘要器只要改一個名字（simple、claude-code、openai、自訂） | ✅ 可用 | `meeting_ai/interface.py` |
| `/meeting` 文字會議 | 組長開始／結束，結束後在原頻道發布紀錄 | ✅ 基本版 | `voice_bot/src/meetings.js` |
| `/ai` 指令和追蹤進度 | 在 Discord 裡整理任務、問問題、追蹤進度 | 🧪 測試 | `voice_bot/src/ai.js`、`ai_demo/` |
| `/help`、`/ask` | 查看指令、私人 OpenAI 問答。需要目前頻道歷史才呼叫讀取工具 | ✅ 可用 | [工具開發指南](../meeting_ai/README.md#開發-ask-工具) |
| `ai_demo` | 在終端機跑測試用的會議問答與任務流程 | 🧪 測試 | `ai_demo/` |
| **假資料庫** | 用 `Demo_Script.md` 產生假的 bot 資料庫，讓你們在自己電腦上測 | 🧪 測試 | `demo_data/` |
| 資料庫架構 | 每張表的欄位，以及每個功能讀寫哪些表 | 📄 文件 | [database_schema.md](database_schema.md) |

```
你們的 tool ──▶ 讀取介面（先確認權限）──▶ sqlite_api.SQLiteStore ──▶ SQLite
                   │
                   ├─ 開發時：FakeAccess（查表）  ＋ demo_data 產生的假資料庫
                   └─ 正式時：ChannelAccess（問 Discord）＋ 主機上的真資料庫
```

正式上線時，所有東西都跑在同一台主機上。你們的程式直接讀主機上的資料庫，不需要網路 API。開發時用假資料庫，正式時換成真的，兩邊的程式完全一樣。

---

## 二、語音 bot：從錄音到你們拿得到資料

### 1. 整個流程

```
有人進語音頻道 ──▶ 錄音（每個人分開錄）──▶ 所有人離開，或組長 /record stop
    ──▶ voice_stt 轉成逐字稿（本機 Breeze 模型）──▶ voice_sessions、voice_lines
    ──▶ meeting_ai 做摘要 ──▶ voice_session_summaries
    ──▶ 語音頻道的聊天室留一則靜音訊息，附「查看摘要」「查看逐字稿」按鈕
```

**錄音結束後才有逐字稿**，錄音途中讀不到。結束時那則訊息會依序更新：轉文字中 → 已轉成 N 句 → 會議紀錄完成。

### 2. 什麼時候錄、錄誰

| 情況 | 會怎樣 |
|---|---|
| 有人進語音頻道 | 約 3 秒後 bot 自動加入並開始錄（`AUTO_RECORD`，預設開） |
| 組長下 `/record start` | 手動開始錄，bot 暱稱會變成 `[REC] …` |
| 中途有人進來 | 也會錄，bot 在聊天室 @ 他告知 |
| 有人按「不要錄我」 | 這次不再錄他，**已錄的部分也刪掉**。按錯可以按「繼續錄我」 |
| 所有人離開，或組長 `/record stop` | 停止錄音，開始轉文字 |
| 自動開始，但什麼都沒錄到 | 收回 bot 發的訊息，不留任何紀錄 |

- 同一個伺服器同時只能錄一個語音頻道（Discord 的限制），會選人最多的那個。
- 上面是預設的 `CONSENT_MODE=direct`。改成 `ask` 的話，只錄按了「同意錄音」的人。
- `/record status` 可以看錄了多久、正在錄誰。

### 3. 逐字稿的特性（寫 tool 時要知道）

- **說話的人是準的。** Discord 本來就把每個人的聲音分開送，`speaker_id` 就是那個人的 Discord ID，不用另外判斷誰在說話。
- **一句怎麼來的：** 一個人停頓超過 0.8 秒就切成一段錄音（`SILENCE_MS`）。同一個人間隔 3 秒內的錄音會合起來一起辨識，最長 60 秒，辨識結果再分成句子。短於 0.3 秒的聲音（咳嗽、雜音）不錄。
- **時間：** 每句都有 `started_at`、`ended_at`，是 UTC 的真實時間，可以和文字訊息排在同一條時間線上。
- **文字：** `text` 是轉成台灣繁體（OpenCC `s2twp`）後的文字，用這個。`text_raw` 是辨識原文，只用來除錯。
- **`confidence`：** 0～1，模型平均有多確定。
- **`flags`：** 可能有問題的句子會標記，標了的句子不要當成確定的依據：

  | flag | 意思 |
  |---|---|
  | `low_confidence` | 模型不太確定 |
  | `repetitive` | 同樣的字一直重複，例如「對對對對對對」 |
  | `maybe_no_speech` | 可能根本沒人說話 |
  | `hallucination_suspect` | 像常見的辨識幻覺句 |

- **已經先丟掉的：** 空白、完全是幻覺句的、很短又不確定的非中文（通常是咳嗽或「嗯」被聽成英文）。
- **名字：** 資料庫只存 Discord ID。錄音當時的顯示名稱在 `voice_bot/recordings/<session>/manifest.json`，`ai_demo` 就是讀這裡。
- **專有名詞：** `voice_bot/voice_stt/glossary.txt` 裡的詞會提示模型，常聽錯的詞可以加進去。
- **錄音檔：** 轉完文字就刪除，只留逐字稿（`.env` 設 `KEEP_AUDIO=1` 才保留，只用來除錯）。

### 4. 摘要

- 摘要器預設使用 `simple`。以 `MEETING_SUMMARIZER` 或 `--summarizer` 選用 OpenAI、Claude Code 或自訂實作，見 [meeting_ai/README.md](../meeting_ai/README.md)。
- 格式：

  ```json
  {
    "summary": "一段話的摘要",
    "decisions": [{"text": "決定了什麼", "source_line_ids": [3, 4]}],
    "action_items": [{"task": "要做的事", "owner": "S1", "due": "期限原文", "source_line_ids": [7]}]
  }
  ```

  - `owner` 通常是 `S1`、`S2`… 這類代號（照第一次說話的順序編），也可能是會議裡提到的人名，不會是 Discord ID。
  - `due` 照會議裡的原話，例如「下週五前」，不是確定的日期。
  - `source_line_ids` 是 `voice_lines` 的 `line_id`，每一項都要有依據。
- `summary_for` 回傳的 `is_stale` 是 `True` 時，代表摘要寫完後句數變了（例如有人補轉文字），要重做。
- 摘要不貼在頻道，要按按鈕才看得到。

### 5. 誰看得到

- 「查看摘要」「查看逐字稿」按鈕：看得到這個語音頻道的人都能按（要有「檢視頻道」＋「讀取訊息歷史」），沒參加會議也可以。內容只有按的人看得到。
- 這些按鈕走的就是你們要用的 `AuthorizedTranscriptReader`，[meeting_ai/show_session.py](../meeting_ai/show_session.py) 是完整範例。讀取介面的規則見 [docs/ai_memory_api.md](ai_memory_api.md)。

### 6. 資料在哪

| 東西 | 位置 |
|---|---|
| 一場錄音 | `voice_sessions`。`session_id` 是 `rec-<語音頻道 ID>-<主機當地時間 年月日-時分秒>` |
| 逐字稿 | `voice_lines`，每句一列 |
| 摘要 | `voice_session_summaries`，一場一份 |
| 顯示名稱、每段錄音的時間 | `voice_bot/recordings/<session>/manifest.json` |
| 給人看的逐字稿 | `voice_bot/recordings/<session>/transcript.md`，內容和資料庫相同 |

每張表的欄位見 [database_schema.md](database_schema.md)。`recordings/` 不會進 git。

### 7. 限制

- 沒有即時逐字稿，要等錄音結束、轉完文字。
- 辨識偶爾會聽錯專有名詞或同音字，請看 `flags` 和 `confidence`。
- bot 在錄音途中被關掉的話，錄音資料夾還在，可以手動轉文字，步驟見 [voice_bot/README.md](../voice_bot/README.md) 的「出問題時」。

---

## 三、在自己電腦上測（不用 Discord、不用真資料）

### 1. 準備（只要做一次）

需要 Python 3.11。測讀取介面和 ai_demo 只需要文字 bot 的環境，不用裝語音辨識（要好幾 GB）。在 repo 根目錄執行：

```bash
python -m venv text_bot/.venv
```

```bash
text_bot/.venv/Scripts/python.exe -m pip install -r text_bot/requirements.txt -e . pytest
```

- `-e .` 會安裝共用的 `sqlite_api`，每個環境都要裝。
- macOS／Linux 把 `text_bot/.venv/Scripts/python.exe` 換成 `text_bot/.venv/bin/python`。下面的指令都一樣。
- 要把整套 bot 都裝起來（含語音辨識和 Node.js），改執行根目錄的 `SETUP_Windows.ps1`，見[根目錄 README](../README.md)。

### 2. 產生假資料庫

```bash
text_bot/.venv/Scripts/python.exe demo_data/make_demo_db.py
```

結果放在 `demo_data/out/`，這個資料夾不會進 git。

| 產生的資料 | ID | 內容 |
|---|---|---|
| 語音錄音 | `rec-demo-voice` | 語音頻道 `20`，31 句逐字稿和一份摘要 |
| 文字會議 | `mtg-30-3000` | 文字頻道 `30`，31 則訊息和會議紀錄 |
| 只有組長能看的頻道 | `40` | 沒有資料，用來測「沒有權限」 |
| 人 | A=`1001`、B=`1002`、C=`1003`、D=`1004`、E=`1005` | **A 是組長**；`9999` 是團隊外的人 |

劇本裡的期限都是「下週五」這種講法，照 spec 只會變成待確認提案。所以最後另外加了一句組長的明確指派：「C 負責第一次小考出題，2026/11/27 18:00 前完成」，用來測正式任務。

### 3. 用讀取介面拿資料（你們的 tool 要走這裡）

先跑一次示範，會印出 7 個例子：讀到資料的、被拒絕的、找不到的。

```bash
text_bot/.venv/Scripts/python.exe demo_data/try_readers.py
```

程式裡這樣用（完整例子見 `demo_data/try_readers.py`）：

```python
from fake_access import FakeAccess                     # 正式：ChannelAccess(client, guild_id)
from sqlite_api import SQLiteStore                     # 所有元件共用的資料庫介面
from transcript_reader import AuthorizedTranscriptReader  # 在 text_bot/，要先加進 sys.path（見 try_readers.py）

reader = AuthorizedTranscriptReader(FakeAccess(), SQLiteStore(db_path))
lines = await reader.transcript_for(member_id=1001, session_id="rec-demo-voice")
```

| 函式 | 拿到什麼 |
|---|---|
| `AuthorizedTranscriptReader.recent_sessions_for(member_id, channel_id, limit=20)` | 一個語音頻道的錄音列表，新的在前（`VoiceSession`） |
| `AuthorizedTranscriptReader.transcript_for(member_id, session_id)` | 一場錄音的每一句，照時間排（`TranscriptLine`：說話的人 ID、時間、文字、信心、`flags`） |
| `AuthorizedTranscriptReader.summary_for(member_id, session_id)` | 摘要：`.summary.content` 是 JSON，`.is_stale` 代表摘要之後逐字稿有變。還沒有摘要時是 `None` |
| `AuthorizedMessageReader.recent_messages_for(member_id, channel_id, limit=100)` | 文字頻道最近的訊息（用 `team_bot/start.mjs` 啟動、有開文字記錄才有） |

摘要的 JSON 長這樣：

```json
{"summary": "…", "decisions": [{"text": "…", "source_line_ids": [16]}],
 "action_items": [{"task": "…", "owner": "S1", "due": "週五前", "source_line_ids": [12]}]}
```

`owner` 是說話者代號（S1、S2…），照第一次說話的順序編。`source_line_ids` 是依據的句子編號。

讀取失敗會拋出例外，請照 spec 換成 ErrorCode 和訊息：

| 例外 | ErrorCode | 對使用者說 |
|---|---|---|
| `AccessDenied` | `ACCESS_DENIED_USER` | 你沒有權限取得所要求的資訊 |
| `AccessUnavailable` | `PERMISSION_UNVERIFIED` | 暫時無法確認你的權限 |
| `SessionNotFound` | `NOT_FOUND` | 沒有找到符合條件的資料 |

`FakeAccess` 可以自己設定誰看得到哪個頻道：

```python
FakeAccess()                     # 預設：A～E 看得到頻道 20、30；頻道 40 只有 A
FakeAccess({20: {1001}})         # 只有 1001 看得到頻道 20
FakeAccess(unavailable=True)     # 假裝 Discord 無法確認 → AccessUnavailable
```

### 4. 用 ai_demo 試 AI 功能

`ai_demo` 是 spec 裡「會議 → 正式任務／提案」和「問會議問題」的示範。它在終端機透過 `SQLiteStore(path, read_only=True)` 查詢會議。在本機以假資料測試，Discord 使用者的權限由 Bot 驗證。

每個指令都要加 `--db demo_data/out/messages.sqlite3 --recordings demo_data/out/recordings`，下面用 `…` 代替：

| 指令 | 做什麼 | 要 AI 嗎 |
|---|---|---|
| `python -m ai_demo … list` | 列出所有會議 | 不用 |
| `python -m ai_demo … show rec-demo-voice` | 看一場會議的內容 | 不用 |
| `python -m ai_demo … tasks mtg-30-3000 --leader 1001` | 整理正式任務和待確認提案 | 要 |
| `python -m ai_demo … ask rec-demo-voice "誰負責期中考出題？"` | 問這場會議的問題 | 要 |

例如：

```bash
text_bot/.venv/Scripts/python.exe -m ai_demo --db demo_data/out/messages.sqlite3 --recordings demo_data/out/recordings tasks mtg-30-3000 --leader 1001
```

- AI 預設用電腦上已經登入的 Claude Code（`claude` 指令），大約 30 秒。
- 也可以改用 OpenAI：加 `--ai openai`，並在根目錄 `.env` 填 `OPENAI_API_KEY`（這個環境要另外 `pip install openai`）。API 照用量計費。
- 假資料的文字會議應該得到 **1 項正式任務**（C 出小考，2026-11-27 18:00）和大約 10 項待確認提案。AI 每次的結果會有一點不同。
- 想模仿 bot 傳原文的方式，可以加 `--stdin`，並把 `demo_data/out/text_meeting_messages.json` 從標準輸入傳進去。

### 5. 跑測試

```bash
text_bot/.venv/Scripts/python.exe -m unittest discover -s demo_data
```

```bash
text_bot/.venv/Scripts/python.exe -m pytest ai_demo -q
```

---

## 四、在 Discord 上測（bot 要在主機上跑著）

| 指令 | 誰可以用 | 做什麼 |
|---|---|---|
| 進語音頻道 | 任何人 | bot 自動加入並開始錄音；可以按「不要錄我」 |
| `/record start`、`/record stop` | 組長 | 手動開始／結束錄音 |
| `/meeting start`、`/meeting end` | 組長 | 開始／結束文字會議；結束後在原頻道發布紀錄 |
| `/ai tasks meeting:<會議>` | 看得到那場會議頻道的人 | 🧪 整理正式任務和提案，可以接著按「追蹤」 |
| `/ai ask meeting:<會議> question:<問題>` | 同上 | 🧪 問這場會議的問題 |
| `/ai tracked` | 任何人（只列你看得到的頻道） | 🧪 看追蹤中的任務和最新進度 |

`/ai` 的回覆**只有下指令的人看得到**。

**組長是誰：** 有設定 `LEADER_ROLE_ID` 的話，就是那個身分組的人；沒設定的話，就是有「管理伺服器」權限的人。

**測試追蹤進度：**

1. 組長在文字頻道下 `/meeting start`。
2. 組長打一句明確指派，要有負責人和日期時間，例如「@某人 負責寫報告，11/25 18:00 前完成」。指派給自己也可以。
3. 組長下 `/meeting end`。
4. 組長下 `/ai tasks`，選剛剛那場會議，按「追蹤這 N 項正式任務的進度」。
5. 負責人收到私訊，按「還沒開始／進行中／卡住了／完成了」其中一個。
6. 組長收到私訊，內容是回報的進度。用 `/ai tracked` 可以看到最新狀態。

要收到私訊，Discord 的「伺服器 → 隱私設定 → 私人訊息」要打開。沒開的話，bot 會記下「送不出去」，不會改貼到公開頻道。

---

## 五、啟動 bot 和切換功能（主機上）

### 語音 bot 和文字 bot 合併成一個

Discord 裡只會看到**一個 bot**。它內部跑兩支程式，都讀根目錄的 `.env`、用同一個 token（`VOICE_BOT_TOKEN`），透過 `sqlite_api` 寫進同一個資料庫：

| 程式 | 負責 |
|---|---|
| `voice_bot/`（Node.js） | 語音錄音，以及**所有指令**（用 `/help` 查看完整清單，包含 `/record`、`/meeting`、`/ai`、`/ask` 和 `/summary_this_channel`） |
| `team_bot/text_logger.py`（Python，沿用 `text_bot/` 的程式） | 把文字訊息存進 `messages` 表，不註冊指令 |

語音一定要用 Node.js 才收得到，文字 bot 原本是 Python，所以合併後內部還是兩支程式。

| 怎麼啟動 | 有什麼 |
|---|---|
| `node team_bot/start.mjs`（在 repo 根目錄） | 全部：語音、指令、文字記錄 |
| `npm --prefix voice_bot start`（在 repo 根目錄） | 只有語音和指令，**沒有文字記錄**。`/meeting` 還是能用，因為它結束時直接向 Discord 讀訊息 |

- 不要和 `text_bot/bot.py` 同時跑，否則同樣的訊息會被記兩次。`TEXT_BOT_TOKEN` 只有單獨跑文字 bot 時才用。
- 第一次用合併版，要在 Developer Portal 打開 Message Content Intent 和 Server Members Intent，步驟見 [team_bot/README.md](../team_bot/README.md)。

### 啟動選項

```bash
node team_bot/start.mjs --help
```

| 選項 | 可以填 | 預設 |
|---|---|---|
| `--summarizer` | `simple`、`claude-code`、`openai`、`模組:類別` | `.env` 的 `MEETING_SUMMARIZER` |
| `--stt` | `local`（本機 Breeze）、`openai`、`模組:類別` | `local` |
| `--consent` | `direct`（進來就錄）、`ask`（按同意才錄） | `direct` |
| `--auto-record` | `on`、`off` | `.env` 的 `AUTO_RECORD` |

沒給的選項用根目錄 `.env` 的設定，所有欄位的說明在根目錄的 `.env.example`。**API key 和 token 只能放在 `.env`**，不能當參數，也不能 commit。

---

## 六、對照 spec v1.1 的檢查結果

### ✅ 符合

| spec | 怎麼做的 |
|---|---|
| R03 群聊只回應 @Bot 或明確指令 | 只回應 `/` 指令（還沒做 @Bot） |
| R05 組長開始／結束文字會議 | 只有組長能下 `/meeting`；會議範圍用開始和結束的訊息 ID 記錄 |
| R06 正式任務要有明確指派、負責人、期限、依據 | 由程式檢查這 4 個條件。AI 說「確定」不算，缺一個就變成提案 |
| R07、R11 只有負責人能回報，不推定完成 | 回報只能從四個按鈕選，沒有百分比；別人按會被拒絕（`ROLE_REQUIRED`） |
| R10、AC10 私訊失敗不改公開 | 記成 `delivery_failed`；結果不明記成 `delivery_unknown`，不重送 |
| R12 分享前先告知 | 詢問私訊附上「本次提交的任務進度將分享給有來源權限的組長」 |
| R15 衍生資料沿用來源權限 | 讀之前先確認「檢視頻道＋讀取訊息歷史」；`unknown` 不當成 `allow` |
| R15 分清楚三種「拿不到」 | 你沒有權限、Bot 沒有權限、沒有找到，三種分開回答 |
| R16 跨來源的回答私下交付 | `/ai` 的回覆只有提問的人看得到 |
| R18、AC04 負責人看不到來源頻道 | 不私訊，任務標成 `awaiting_leader_decision`，等組長決定 |
| ConfirmationPolicy | 組長確認的就是當時顯示的那幾項，按一次就失效，不再讓 AI 改寫 |
| AC03、AC24 重送不重複 | 同一次確認重送，回傳同樣的任務 |
| AC23 送出前再確認權限 | AI 跑完、送出答案前，再檢查一次權限（這次補上） |
| AC26 私人討論串 | 要是討論串成員，或有「管理討論串」權限（這次補上） |
| ContextIsolationPolicy | 每次呼叫 AI 都是全新的，只放一場會議的內容，不留對話紀錄 |
| 命名規則 | 欄位和狀態用英文 snake_case，ErrorCode 用 UPPER_SNAKE_CASE；時間存 UTC RFC 3339 |

### 🔧 這次檢查後修正的

| 問題 | 修正 | spec |
|---|---|---|
| 負責人回報「完成」後還能改回進行中 | 完成後只有組長能重新開啟 | 任務狀態與異動 |
| 回報後詢問停在 `reply_received`（意思是「待釐清」） | 按鈕回報就是確認過的版本，詢問直接結案（`closed`） | Inquiry.state |
| 私訊沒有回應也記成「失敗」 | 結果不明記成 `delivery_unknown` | PTC 與執行可靠性 |
| Bot 讀不到文字會議的頻道時，沒有說明原因 | 回覆「Bot 沒有權限讀取所要求的來源」 | `SOURCE_UNAVAILABLE_BOT` |
| AI 跑完後沒有再檢查權限 | 送出前再檢查一次 | AC23 |
| 私人討論串只看上層頻道的權限 | 另外確認是不是討論串成員 | AC26 |

另外修了兩個 bug：ai_demo 讀資料庫後沒有關閉連線，Windows 上會鎖住檔案；在終端機讀文字會議時，@ 的人沒有換成代號，導致負責人認不出來。

### ⚠️ 和 spec 不一樣，要團隊決定

文字記錄程序目前會匯入與保存一般聊天。文字會議紀錄本身保存摘要、範圍和引用，`/ai` 向 Discord 讀取會議原文。

| 項目 | spec | 現在 |
|---|---|---|
| 語音 | 語音轉錄不在本次範圍 | 有做，逐字稿長期保存 |
| 文字記錄 | 一般聊天不長期完整保存 | `text_bot/bot.py`、`team_bot/text_logger.py` 會把所有訊息長期存進 `messages` 表 |
| 組長 | Administrator 設定「一位」TeamLeader | 用身分組；沒設定時，有「管理伺服器」權限的人都算 |
| team_id | 所有資料都要帶 `team_id` | 只有 `guild_id` |
| 時區 | 組長確認過的 timezone | 固定 `Asia/Taipei` |
| `/meeting end` 的紀錄 | 分列正式任務和待確認提案 | 摘要、決議、待辦；正式任務要另外下 `/ai tasks` |
| R16 改用私訊 | 頻道裡說「將以私訊回答」，再私訊 | 用「只有你看得到」的回覆代替，效果一樣是只有提問的人看得到 |
| Bot 讀不到來源（Python 讀取介面） | 回 `SOURCE_UNAVAILABLE_BOT` | `ChannelAccess` 一律拋 `AccessUnavailable`，沒有分開 |
| 進度的分享草稿 | 先給負責人確認草稿，確認後才分享 | 只有四個按鈕、沒有自由文字，所以按下去就是確認。之後有自由文字的話，要照 spec 加草稿確認 |

### ❌ 還沒做（AI 組的範圍）

- R04 初始化設定（`TeamSettings`）
- R09 排程提醒、追問、可發訊息時段（測試版只在確認時問一次）
- R13 每日摘要
- R14 代組長轉達
- 組長取消、改期限、改負責人、重新開啟任務
- `TaskChange`、`AuditEvent` 紀錄
- @Bot 提問
- PTC

---

## 七、注意事項

- **不要把真的資料庫、錄音或逐字稿放進 git。** repo 是公開的，`.gitignore` 已經擋掉 `*.sqlite3` 和 `recordings/`。測試一律用 `demo_data` 的假資料。
- 假資料的 ID 都是編的。真的 Discord ID 是 18～19 位數，傳給 JavaScript 時要轉成字串。
- `ai_demo` 在終端機不檢查權限，結果不要直接貼給別人。正式功能請走讀取介面。
- 以下還沒在 Discord 上實際試過：追蹤按鈕、私訊、回報這一整段，以及這次補上的 AC23、AC26。程式的部分有單元測試，也用暫時資料庫從 Node 實際跑過。
