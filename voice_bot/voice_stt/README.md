# voice_stt — 語音轉文字（F6）

把音檔轉成台灣繁體中文逐字稿。語音 Bot 可在錄音結束後呼叫轉寫程式，依時間合併各說話者的文字並寫入共用 SQLite。

- 模型：[Breeze-ASR-25](https://huggingface.co/MediaTek-Research/Breeze-ASR-25)（聯發科，Apache-2.0），
  針對台灣口音和中英夾雜調整過的 Whisper。用 faster-whisper 執行（CTranslate2 格式的社群轉檔
  `SoybeanMilk/faster-whisper-Breeze-ASR-25`，約 3.1 GB，第一次執行時自動下載）。
- **全部在本機跑**，錄音不會傳到任何雲端服務。

## 安裝

從專案根目錄依 [README](../../README.md#從專案根目錄設定與啟動)建立 `voice_bot/voice_stt/.venv`、安裝依賴與共用 SQLite API。下面的 Windows 範例也從根目錄執行。macOS 請把 Python 路徑換成 `./voice_bot/voice_stt/.venv/bin/python`。

## 用法

```bash
./voice_bot/voice_stt/.venv/Scripts/python.exe -m voice_bot.voice_stt.stt 會議錄音.wav --speaker 組長 --out-dir transcripts
```

| 參數 | 說明 |
|---|---|
| `--speaker` | 說話者名字（預設用檔名；一個音軌 = 一個人） |
| `--out-dir` | 輸出資料夾（預設 `transcripts/`，已在 `.gitignore`） |
| `--glossary` | 詞彙表檔案，幫模型認出專有名詞，見 `glossary.example.txt` |
| `--compute-type` | `float16`（預設，最準，約 4.5 GB VRAM）或 `int8_float16`（較省記憶體） |
| `--device` | `auto` / `cuda` / `cpu` |
| `--no-opencc` | 不做繁體轉換 |

輸出兩個檔案：

- `檔名.jsonl`：給程式用，一行一句
- `檔名.md`：給人看的逐字稿，沒把握的句子標 ⚠️

## 一場會議 → 存進 bot 的資料庫

每人一個音檔（例如 Craig 錄的多軌檔），用 Discord 使用者 ID 標明是誰：

```bash
./voice_bot/voice_stt/.venv/Scripts/python.exe -m voice_bot.voice_stt.stt.import_session --channel-id 語音頻道ID --started-at 2026-11-18T14:00:00+08:00 --started-by 組長ID --track 組長ID=leader.wav --track 成員ID=member.wav
```

- 伺服器 ID 預設使用根目錄 .env 的 `DISCORD_GUILD_ID`，可用 `--guild-id` 指定。
- 每個音軌各自辨識，再依時間合併；某個檔案晚開始錄，可以寫 `成員ID=member.wav@2.5`（晚 2.5 秒）。
- 結果預設寫進根目錄 `data/messages.sqlite3`（可用 `BOT_DB` 或 `--db` 覆寫） 的 `voice_sessions`／`voice_lines`，
  另外在 `transcripts/` 存一份給人看的 Markdown。
- AI 組怎麼讀這些資料，見 [docs/ai_memory_api.md](../../docs/ai_memory_api.md)。

## 錄音 bot 的資料夾 → 資料庫（`stt.ingest_recording`）

voice_bot 在 `/record stop` 後會自動執行，通常不用手動跑。它比上面多做兩件事：

- **把同一個人相近的片段接起來再辨識**：下一段在 3 秒內開始、中間沒有別人講話，就接成一段（最長 60 秒），片段間的空檔補上靜音，所以句子時間不變、發言順序也不會亂。
  原因：Discord 實測時，1–2 秒的短片段大多辨識錯；同一段 48 秒的錄音，錯字率約 9%。
- **自動使用團隊詞彙表** [glossary.txt](glossary.txt)：目前只放組員名字，因為實測加英文術語反而變差（檔案裡有數字）。用 `--glossary 其他檔案` 可以換掉。

## 每一句的欄位

| 欄位 | 意思 |
|---|---|
| `session_id` | 哪一次錄音／會議 |
| `speaker` | 誰說的 |
| `start` / `end` | 從錄音開始算的秒數 |
| `text_raw` | 模型原始輸出（除錯用） |
| `text` | 轉成台灣繁體後的文字 |
| `confidence` | 0–1，模型的平均把握程度 |
| `flags` | 警告，見下表 |
| `source` | 音檔名稱 |

## 自動清理和警告

| 情況 | 處理 |
|---|---|
| 整句是模型在安靜時亂生的話（例如「謝謝觀看」「字幕由 Amara.org 社群提供」） | 丟掉，並在終端機列出 |
| 句子裡含有上面那種話 | 保留，標 `hallucination_suspect` |
| 3.5 秒以內、完全沒有中文字、把握度低於 0.6（例如「Yeah.」「OK.」「Squid.」，通常是咳嗽、笑聲或「嗯」被猜成英文） | 丟掉，並在終端機列出 |
| 模型沒把握（avg_logprob < -1.0） | 標 `low_confidence` |
| 一直重複（壓縮比 > 2.4，或同字連續 5 次以上） | 標 `repetitive` |
| 可能根本不是人聲（no_speech_prob > 0.6） | 標 `maybe_no_speech` |

另外有開 VAD（自動跳過靜音），並關掉「拿前文當提示」來避免錯誤一路滾下去。

## 換語音辨識引擎

預設是本機的 Breeze-ASR-25（`stt/engine.py`）。引擎是可以換的獨立單元，選法在 `stt/engines.py`：

| 名稱 | 檔案 | 說明 |
|---|---|---|
| `local`（預設） | `engine.py` | 本機 GPU，錄音不離開這台電腦 |
| `openai` | `openai_engine.py` | OpenAI 語音轉文字 API（預設 `whisper-1`）。**預設沒開**；要先 `pip install openai`，並在 `voice_bot/.env` 填 `OPENAI_API_KEY`。錄音會傳到 OpenAI，一個檔案最多 25 MB |
| `模組路徑:類別名稱` | 自己寫 | 任何有 `transcribe(audio_path, on_segment=None) -> (segments, 秒數)` 的類別，建立時接受 `hotwords=` |

選法（後面的會蓋過前面的）：`voice_bot/.env` 的 `STT_ENGINE` → voice_bot 啟動參數 `--stt` → 直接執行時的 `python -m stt.ingest_recording … --engine openai`。

換引擎之後，後面的清理、合併、存資料庫都不用改；只要 segments 有時間和信心分數，「可能聽錯」的判斷就照常運作。

## 測試

```bash
./voice_bot/voice_stt/.venv/Scripts/python.exe -m pytest -c voice_bot/voice_stt/pytest.ini voice_bot/voice_stt/tests
```

單元測試不需要下載模型。

## 注意

- 錄音和逐字稿含有別人的發言，**不要 commit**（`.gitignore` 已擋 `*.wav`、`transcripts/` 等）。
- 程式由 Claude 協助撰寫，紀錄見根目錄的 `PROMPT_LOG.md`。
