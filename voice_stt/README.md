# voice_stt — 語音轉文字（F6）

把**一個音檔**轉成**台灣繁體中文逐字稿**。這是語音功能的第一步，還沒接上 Discord 和資料庫
（多人音軌合併、寫進資料庫是下一個 PR）。

- 模型：[Breeze-ASR-25](https://huggingface.co/MediaTek-Research/Breeze-ASR-25)（聯發科，Apache-2.0），
  針對台灣口音和中英夾雜調整過的 Whisper。用 faster-whisper 執行（CTranslate2 格式的社群轉檔
  `SoybeanMilk/faster-whisper-Breeze-ASR-25`，約 3.1 GB，第一次執行時自動下載）。
- **全部在本機跑**，錄音不會傳到任何雲端服務。

## 安裝（Windows，Python 3.11）

```bash
cd voice_stt
py -3.11 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

有 NVIDIA 顯卡會自動用 GPU；沒有的話會改用 CPU（慢很多）。

## 用法

```bash
.venv/Scripts/python.exe -m stt 會議錄音.wav --speaker 組長 --out-dir transcripts
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

## 每一句的欄位（草稿，待和皓元、AI 組確認）

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
| 模型沒把握（avg_logprob < -1.0） | 標 `low_confidence` |
| 一直重複（壓縮比 > 2.4，或同字連續 5 次以上） | 標 `repetitive` |
| 可能根本不是人聲（no_speech_prob > 0.6） | 標 `maybe_no_speech` |

另外有開 VAD（自動跳過靜音），並關掉「拿前文當提示」來避免錯誤一路滾下去。

## 測試

```bash
.venv/Scripts/python.exe -m pytest
```

單元測試不需要下載模型。

## 注意

- 錄音和逐字稿含有別人的發言，**不要 commit**（`.gitignore` 已擋 `*.wav`、`transcripts/` 等）。
- 程式由 Claude 協助撰寫，紀錄見根目錄的 `PROMPT_LOG.md`。
