# 2026_AISP

Discord 團隊助理提供文字記錄、語音與文字會議摘要，以及私人 AI 問答。第一次使用，從下方安裝與啟動開始。

| 要做什麼 | 去哪裡看 |
|---|---|
| 安裝、設定、啟動 | [本頁的快速開始](#從專案根目錄設定與啟動) |
| 操作 Discord Bot、查已知限制 | [Team Bot 使用說明](team_bot/README.md) |
| 開發 AI tool、用假資料測試 | [AI 團隊接手指南](docs/ai_team_guide.md) |
| 串接與設定會議摘要器 | [摘要器介面](meeting_ai/README.md) |
| 查詢 SQL 方法、資料表及授權規則 | [SQLite API](SQL_API_README.md) · [資料表](docs/database_schema.md) · [Discord 授權讀取](docs/ai_memory_api.md) |
| 了解程式與資料流 | [系統流程圖](docs/SystemWorkflow.html) |
| 查模組的操作與測試 | [文字 Bot](text_bot/README.md) · [語音 Bot](voice_bot/README.md) · [語音轉寫](voice_bot/voice_stt/README.md) · [AI demo](ai_demo/README.md) |
| 查需求或準備展示 | [專案規格](spec.md) · [Demo 劇本](Demo_Script.md) |

## 從專案根目錄設定與啟動

需要 Python 3.11 和 Node.js 22.12 以上。以下指令都在專案根目錄執行。兩個 Python 虛擬環境各自安裝所需套件，並共用同一份根目錄 .env。

升級既有專案時，請依下方指令在新路徑建立虛擬環境。若有自訂 `STT_PYTHON` 或 `READER_PYTHON`，請確認指向新位置。

### 1-1. 一鍵安裝 (注意: 套件大小約 6 GB)

先安裝 Python 3.11 與 Node.js 22.12 以上（含 npm），再執行對應的安裝腳本。腳本會先列出將安裝的套件與磁碟空間估算，再請你確認。輸入 Y 才會安裝兩個 Python 虛擬環境和語音 Bot 的 Node.js 套件。輸入 N 或直接按 Enter 會取消。只想查看安裝內容時，PowerShell 命令加上 `-Plan`，Bash 命令則加上 `--plan`。

| 作業系統 | 使用的終端機 | 從專案根目錄執行 |
|---|---|---|
| Windows x86-64 | PowerShell | `.\SETUP_Windows.ps1` |
| macOS | Terminal | `bash SETUP_macOS` |
| Linux（glibc）或 WSL | Bash | `bash SETUP_Linux` |

若 PowerShell 的執行原則封鎖腳本，可用以下命令只對本次執行放行。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\SETUP_Windows.ps1
```

估算依作業系統與 CPU 架構而異，已計入安裝暫存。首次執行語音轉寫時，預設的 [Breeze-ASR-25 模型](https://huggingface.co/SoybeanMilk/faster-whisper-Breeze-ASR-25/tree/main) 還需要約 3.1 GB。Windows 若出現 CTranslate2 載入 DLL 的錯誤，請確認已安裝 [Microsoft Visual C++ Redistributable x64](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist)。

安裝後再編輯根目錄的 `.env`。腳本會保留既有設定，並檢查本機的 Python 與 Node.js 版本。

### 1-2. 手動安裝

#### Windows PowerShell

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
py -3.11 -m venv text_bot/.venv
py -3.11 -m venv voice_bot/voice_stt/.venv
./text_bot/.venv/Scripts/python.exe -m pip install -r text_bot/requirements.txt -e .
./voice_bot/voice_stt/.venv/Scripts/python.exe -m pip install -r voice_bot/voice_stt/requirements.txt -e .
npm.cmd --prefix voice_bot ci
```

#### macOS Terminal／Linux Bash

```sh
[ -f .env ] || cp .env.example .env
python3.11 -m venv text_bot/.venv
python3.11 -m venv voice_bot/voice_stt/.venv
./text_bot/.venv/bin/python -m pip install -r text_bot/requirements.txt -e .
./voice_bot/voice_stt/.venv/bin/python -m pip install -r voice_bot/voice_stt/requirements.txt -e .
npm --prefix voice_bot ci
```

Linux 若使用 NVIDIA GPU 和 Python 環境內的 cuBLAS／cuDNN，請在啟動語音 Bot 或手動轉寫的終端機設定程式庫路徑。CPU 使用者可略過，GPU 驅動程式由作業系統管理。詳見 [faster-whisper 的 Linux GPU 說明](https://github.com/SYSTRAN/faster-whisper#gpu)。

```bash
cuda_libs="$(./voice_bot/voice_stt/.venv/bin/python -c 'from pathlib import Path; import nvidia.cublas, nvidia.cudnn; print(":".join(str(Path(package.__path__[0]) / "lib") for package in (nvidia.cublas, nvidia.cudnn)))')"
export LD_LIBRARY_PATH="$cuda_libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
```

### 2. `.env`填寫設定

| 欄位 | 用途 |
|---|---|
| `TEXT_BOT_TOKEN` | 文字 Bot 的 Discord Token。只有單獨跑 `text_bot/bot.py` 時才用。 |
| `VOICE_BOT_TOKEN` | 語音 Bot 的 Discord Token，也用於查看逐字稿與摘要。合併版（`team_bot`）的語音、指令、文字記錄都用這個帳號。 |
| `DISCORD_GUILD_ID` | 兩個 Bot 共用的 Discord 伺服器 ID。 |
| `BOT_DB` | 選填，預設為 `data/messages.sqlite3`。相對路徑以根目錄為準。 |
| `OPENAI_API_KEY` | 使用 `/ask` 或選擇 OpenAI 摘要、轉寫時需要。 |
| `MEETING_SUMMARIZER` | 預設 `simple`。其他摘要器見 [meeting_ai](meeting_ai/README.md#內建的實作)。 |
| `MEETING_SUMMARY_MODEL` | OpenAI 摘要和 `/ask` 使用的模型，預設為 `gpt-6-luna`。 |

其他錄音與路徑選項見 [.env.example](.env.example)。環境變數優先於 .env。已有舊設定者，從各 Bot 原本的 .env 將 `DISCORD_TOKEN` 分別填入兩個新欄位，並確認兩個 Bot 使用同一個伺服器 ID。既有資料庫可用 `BOT_DB` 指定，路徑解析見 [SQLite API](SQL_API_README.md#安裝與路徑)。

### 執行

依 [Team Bot 的 Discord 權限](team_bot/README.md#discord-權限)設定 `VOICE_BOT_TOKEN` 對應的應用程式。確認根目錄 `.env` 已填好 `VOICE_BOT_TOKEN` 和 `DISCORD_GUILD_ID`，再執行。

```sh
node team_bot/start.mjs
```

在 Discord 用 `/help` 查看目前註冊的指令。要分開啟動或測試元件，請使用上方文件索引。
