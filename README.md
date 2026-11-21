# 2026_AISP

## 從專案根目錄設定與啟動

需要 Python 3.11 和 Node.js 22.12 以上。以下指令都在專案根目錄執行。兩個 Python 虛擬環境各自安裝所需套件，並共用同一份根目錄 .env。

升級既有專案時，請依下方指令在新路徑建立虛擬環境。若有自訂 `STT_PYTHON` 或 `READER_PYTHON`，請確認指向新位置。

### 一鍵安裝

先安裝 Python 3.11 與 Node.js 22.12 以上（含 npm），再執行對應的安裝腳本。腳本會先列出將安裝的套件與磁碟空間估算，再請你確認。輸入 Y 才會安裝兩個 Python 虛擬環境和語音 Bot 的 Node.js 套件。輸入 N 或直接按 Enter 會取消。只想查看安裝內容時，PowerShell 命令加上 `-Plan`，Bash 命令則加上 `--plan`。

| 作業系統 | 使用的終端機 | 從專案根目錄執行 |
|---|---|---|
| Windows x86-64 | PowerShell | `.\SETUP_Windows.ps1` |
| Windows x86-64 | Git Bash | `bash SETUP_Windows` |
| macOS | Terminal | `bash SETUP_macOS` |
| Linux（glibc）或 WSL | Bash | `bash SETUP_Linux` |

若 PowerShell 的執行原則封鎖腳本，可用以下命令只對本次執行放行。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\SETUP_Windows.ps1
```

估算依作業系統與 CPU 架構而異，已計入安裝暫存。首次執行語音轉寫時，預設的 [Breeze-ASR-25 模型](https://huggingface.co/SoybeanMilk/faster-whisper-Breeze-ASR-25/tree/main) 還需要約 3.1 GB。Windows 若出現 CTranslate2 載入 DLL 的錯誤，請確認已安裝 [Microsoft Visual C++ Redistributable x64](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist)。

安裝後再編輯根目錄的 `.env`。腳本會保留既有設定，並檢查本機的 Python 與 Node.js 版本。

### 手動安裝

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

### `.env`填寫設定

| 欄位 | 用途 |
|---|---|
| `TEXT_BOT_TOKEN` | 文字 Bot 的 Discord Token。只有單獨跑 `text_bot/bot.py` 時才用。 |
| `VOICE_BOT_TOKEN` | 語音 Bot 的 Discord Token，也用於查看逐字稿與摘要。合併版（`team_bot`）的語音、指令、文字記錄都用這個帳號。 |
| `DISCORD_GUILD_ID` | 兩個 Bot 共用的 Discord 伺服器 ID。 |
| `BOT_DB` | 選填，預設為 `data/messages.sqlite3`。相對路徑以根目錄為準。 |
| `MEETING_SUMMARIZER` | 預設 `simple`。使用 `openai` 時需填 `OPENAI_API_KEY`，可用 `MEETING_SUMMARY_MODEL` 選模型。也可以填 `claude-code`（這台電腦已登入的 Claude Code，測試用）或 `模組路徑:類別名稱`。 |

其他錄音與路徑選項見 [.env.example](.env.example)。環境變數優先於 .env。已有舊設定者，從各 Bot 原本的 .env 將 `DISCORD_TOKEN` 分別填入兩個新欄位，並確認兩個 Bot 使用同一個伺服器 ID。現有資料庫的搬移步驟見 [SQL API 文件](SQL_API_README.md#搬移既有資料庫)。

### 執行

**合併版（建議）**：Discord 裡只有一個 bot，語音錄音、所有指令（`/record`、`/meeting`、`/ai`、`/ping`）和文字訊息記錄都由它負責，只需要 `VOICE_BOT_TOKEN`。第一次使用前要在 Developer Portal 為這個 bot 開 Message Content Intent 和 Server Members Intent，見 [team_bot](team_bot/README.md)。

也可以照舊用兩個終端機分別啟動文字及語音 Bot（兩個帳號）。先依 [文字 Bot](text_bot/README.md) 與 [語音 Bot](voice_bot/README.md) 的說明，設定各自的 Discord 應用程式與邀請權限。合併版和單獨的文字 Bot 不要同時跑，否則訊息會記兩次。

| 操作 | Windows PowerShell | macOS／Linux |
|---|---|---|
| 合併版（一個 bot） | `node team_bot/start.mjs` | `node team_bot/start.mjs` |
| 文字 Bot | `./text_bot/.venv/Scripts/python.exe text_bot/bot.py` | `./text_bot/.venv/bin/python text_bot/bot.py` |
| 語音 Bot | `npm.cmd --prefix voice_bot start` | `npm --prefix voice_bot start` |
| 離線檢查語音 Bot 設定 | `npm.cmd --prefix voice_bot run check -- --offline` | `npm --prefix voice_bot run check -- --offline` |
| 手動轉寫音檔 | `./voice_bot/voice_stt/.venv/Scripts/python.exe -m voice_bot.voice_stt.stt 會議錄音.wav` | `./voice_bot/voice_stt/.venv/bin/python -m voice_bot.voice_stt.stt 會議錄音.wav` |
| 文字 Bot 與 SQLite 測試 | `./text_bot/.venv/Scripts/python.exe -m unittest discover -s text_bot/test -t text_bot` | `./text_bot/.venv/bin/python -m unittest discover -s text_bot/test -t text_bot` |
| 摘要與逐字稿授權測試 | `./text_bot/.venv/Scripts/python.exe -m unittest meeting_ai.tests.test_show_session` | `./text_bot/.venv/bin/python -m unittest meeting_ai.tests.test_show_session` |
| 轉寫測試 | `./voice_bot/voice_stt/.venv/Scripts/python.exe -m pytest -c voice_bot/voice_stt/pytest.ini voice_bot/voice_stt/tests` | `./voice_bot/voice_stt/.venv/bin/python -m pytest -c voice_bot/voice_stt/pytest.ini voice_bot/voice_stt/tests` |
| 摘要測試 | `./voice_bot/voice_stt/.venv/Scripts/python.exe -m pytest meeting_ai/tests/test_meeting_ai.py` | `./voice_bot/voice_stt/.venv/bin/python -m pytest meeting_ai/tests/test_meeting_ai.py` |
| 語音 Bot 測試 | `npm.cmd --prefix voice_bot test` | `npm --prefix voice_bot test` |

## 共用 SQLite 介面

API 使用方式、欄位與方法命名對照見 [SQL_API_README.md](SQL_API_README.md)。各元件的資料流見 [SystemWorkflow.html](docs/SystemWorkflow.html)。
