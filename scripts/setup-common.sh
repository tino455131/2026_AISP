#!/usr/bin/env bash
# Shared implementation sourced by the platform entry points.
set -euo pipefail

setup_error() {
    printf '設定失敗：%s\n' "$*" >&2
    exit 1
}

setup_project() {
    local platform="$1"
    shift
    local text_env="text_bot/.venv"
    local speech_env="voice_bot/voice_stt/.venv"
    local python_suffix="bin/python"
    local estimate=""
    local shell_help=""
    case "$platform" in
        Windows)
            python_suffix="Scripts/python.exe"
            estimate="約 3–5 GB，建議預留 6 GB（含 NVIDIA 套件與安裝暫存）。"
            shell_help="請使用 Git Bash（Windows x86-64）。"
            ;;
        macOS)
            estimate="約 0.5–1.5 GB，建議預留 2 GB（含安裝暫存）。"
            shell_help="請使用 macOS Terminal。"
            ;;
        Linux)
            estimate="x86-64 約 3–5 GB，建議預留 6 GB；ARM64 約 0.5–1.5 GB，建議預留 2 GB（含安裝暫存）。"
            shell_help="請使用 Linux 或 WSL 的 Bash。"
            ;;
        *) setup_error "不認得的安裝平台：$platform" ;;
    esac

    printf '%s\n' \
        "2026 AISP｜$platform 環境安裝" \
        '將建立或沿用兩個 Python 虛擬環境，安裝下列套件：' \
        '  文字 Bot：discord.py、python-dotenv、共用 SQLite API。' \
        '  語音轉寫和摘要：faster-whisper、CTranslate2、OpenCC、OpenAI SDK、pytest、共用 SQLite API。' \
        '  語音 Bot：依 package-lock.json 安裝 Node.js 套件和 Opus 解碼器。'
    if [[ "$platform" != macOS ]]; then
        printf '%s\n' '  Windows/Linux x86-64 另安裝 cuBLAS 和 cuDNN。'
    fi
    printf '%s\n' \
        "磁碟空間估算：$estimate" \
        '首次轉寫將另外下載約 3.1 GB 的模型。安裝腳本不會下載模型。' \
        '請先備妥 Python 3.11、Node.js 22.12 以上與 npm。' \
        '若根目錄還沒有 .env，會從範本建立一份供你填寫。' \
        ''

    case "${1:-}" in
        --plan|--help|-h)
            [[ $# == 1 ]] || setup_error "用法：bash SETUP_$platform [--plan]"
            printf '用法：bash SETUP_%s [--plan]\n' "$platform"
            return
            ;;
        '') [[ $# == 0 ]] || setup_error "用法：bash SETUP_$platform [--plan]" ;;
        *) setup_error "用法：bash SETUP_$platform [--plan]" ;;
    esac

    local answer
    while true; do
        printf '%s' '是否開始安裝？[y/N] '
        if ! read -r answer; then
            printf '\n%s\n' '已取消安裝。'
            return 0
        fi
        case "$answer" in
            [Yy]) break ;;
            [Nn]|'') printf '%s\n' '已取消安裝。'; return 0 ;;
            *) printf '%s\n' '請輸入 Y 或 N。' ;;
        esac
    done

    case "$platform:$(uname -s)" in
        Windows:MINGW*|Windows:MSYS*|macOS:Darwin|Linux:Linux) ;;
        *) setup_error "$shell_help" ;;
    esac
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

    local version_check='import sys; raise SystemExit(sys.version_info[:2] != (3, 11))'
    local -a python=()
    if [[ "$platform" == Windows ]] && command -v py >/dev/null 2>&1 &&
        py -3.11 -c "$version_check" >/dev/null 2>&1; then
        python=(py -3.11)
    elif command -v python3.11 >/dev/null 2>&1 &&
        python3.11 -c "$version_check" >/dev/null 2>&1; then
        python=(python3.11)
    elif command -v python3 >/dev/null 2>&1 &&
        python3 -c "$version_check" >/dev/null 2>&1; then
        python=(python3)
    elif command -v python >/dev/null 2>&1 &&
        python -c "$version_check" >/dev/null 2>&1; then
        python=(python)
    else
        setup_error "找不到 Python 3.11。請先安裝並確認終端機可以執行。"
    fi

    if ! command -v node >/dev/null 2>&1 ||
        ! node -e 'const [major, minor] = process.versions.node.split(".").map(Number); process.exit(major > 22 || (major === 22 && minor >= 12) ? 0 : 1);'; then
        setup_error "需要 Node.js 22.12 以上。"
    fi
    command -v npm >/dev/null 2>&1 && npm --version >/dev/null 2>&1 ||
        setup_error "找不到可用的 npm。"
    if [[ "$platform" == Windows ]] &&
        ! "${python[@]}" -c 'import sysconfig; raise SystemExit(sysconfig.get_platform() != "win-amd64")'; then
        setup_error "Windows 轉寫套件需要 x86-64 版的 Python 3.11。"
    fi

    check_existing_venv "$text_env" "$python_suffix" 'import sys; raise SystemExit(sys.version_info < (3, 11))'
    check_existing_venv "$speech_env" "$python_suffix" "$version_check"
    install_python_env "$text_env" "$python_suffix" 'text_bot/requirements.txt' "${python[@]}"
    install_python_env "$speech_env" "$python_suffix" 'voice_bot/voice_stt/requirements.txt' "${python[@]}"

    printf '\n[3/3] 安裝語音 Bot 的 Node.js 套件\n'
    npm --prefix voice_bot ci

    if [[ ! -e .env && ! -L .env ]]; then
        (umask 077; set -C; cat .env.example > .env)
    fi
    printf '\n%s\n' '安裝完成。請在根目錄 .env 填寫 Discord Bot Token 和伺服器 ID。' \
        '若要啟用 OpenAI 摘要，請設定 MEETING_SUMMARIZER=openai 並填寫 OPENAI_API_KEY。' \
        '啟動指令請見 README.md。'
}

check_existing_venv() {
    local folder="$1" suffix="$2" version_check="$3"
    if [[ -e "$folder" || -L "$folder" ]]; then
        if [[ ! -x "$folder/$suffix" ]] ||
            ! "$folder/$suffix" -c "$version_check" ||
            ! "$folder/$suffix" -m pip --version >/dev/null 2>&1; then
            setup_error "$folder 的 Python 環境無法使用或版本不相容。請先將該環境改名，再重跑。"
        fi
    fi
}

install_python_env() {
    local folder="$1" suffix="$2" requirements="$3"
    shift 3
    if [[ "$folder" == 'text_bot/.venv' ]]; then
        printf '\n[1/3] 安裝文字 Bot 的 Python 套件\n'
    else
        printf '\n[2/3] 安裝語音轉寫和摘要的 Python 套件\n'
    fi
    if [[ ! -e "$folder" && ! -L "$folder" ]]; then
        "$@" -m venv "$folder"
    fi
    "$folder/$suffix" -m pip install -r "$requirements" -e .
    "$folder/$suffix" -m pip check
}
