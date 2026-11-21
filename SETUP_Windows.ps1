[CmdletBinding()]
param(
    [switch]$Plan
)

$ErrorActionPreference = 'Stop'

@(
    '2026 AISP｜Windows PowerShell 環境安裝'
    '將建立或沿用兩個 Python 虛擬環境，安裝下列套件：'
    '  文字 Bot：discord.py、python-dotenv、共用 SQLite API。'
    '  語音轉寫和摘要：faster-whisper、CTranslate2、OpenCC、OpenAI SDK、pytest、cuBLAS 和 cuDNN。'
    '  語音 Bot：依 package-lock.json 安裝 Node.js 套件和 Opus 解碼器。'
    '磁碟空間估算：約 3–5 GB，建議預留 6 GB（含 NVIDIA 套件與安裝暫存）。'
    '首次轉寫會另外下載約 3.1 GB 的模型。'
    '請先備妥 x86-64 版 Python 3.11、Node.js 22.12 以上與 npm。'
    '若根目錄尚無 .env，會從範本建立一份供你填寫。'
    ''
) | Write-Host

if ($Plan) {
    return
}

while ($true) {
    try {
        $answer = Read-Host '是否開始安裝？[y/N]'
    } catch {
        Write-Host '已取消安裝。'
        return
    }
    $answer = ([string]$answer).Trim()
    if ($answer -eq 'Y') {
        break
    }
    if ($answer -eq 'N' -or $answer -eq '') {
        Write-Host '已取消安裝。'
        return
    }
    Write-Host '請輸入 Y 或 N。'
}

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw '請在 Windows PowerShell 執行此腳本。'
}

function Test-SetupCommand {
    param([string]$Executable, [string[]]$Arguments)

    try {
        & $Executable @Arguments 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Invoke-SetupCommand {
    param([string]$Executable, [string[]]$Arguments, [string]$Description)

    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Description 失敗。結束碼 $LASTEXITCODE。"
    }
}

function Test-ExistingVenv {
    param([string]$Directory, [string]$PythonCheck)

    if (Test-Path -LiteralPath $Directory) {
        $interpreter = Join-Path -Path $Directory -ChildPath 'Scripts/python.exe'
        if (-not (Test-Path -LiteralPath $interpreter -PathType Leaf) -or
            -not (Test-SetupCommand $interpreter @('-c', $PythonCheck)) -or
            -not (Test-SetupCommand $interpreter @('-m', 'pip', '--version'))) {
            throw "$Directory 的 Python 環境無法使用或版本不相容。請先將該環境改名，再重跑。"
        }
    }
}

function Install-PythonEnvironment {
    param(
        [string]$Directory,
        [string]$Requirements,
        [string]$Launcher,
        [string[]]$LauncherArguments
    )

    if (-not (Test-Path -LiteralPath $Directory)) {
        Invoke-SetupCommand $Launcher ($LauncherArguments + @('-m', 'venv', $Directory)) '建立虛擬環境'
    }
    $interpreter = Join-Path -Path $Directory -ChildPath 'Scripts/python.exe'
    Invoke-SetupCommand $interpreter @('-m', 'pip', 'install', '-r', $Requirements, '-e', '.') '安裝 Python 套件'
    Invoke-SetupCommand $interpreter @('-m', 'pip', 'check') '檢查 Python 相依性'
}

$python311Check = "import sys, sysconfig; raise SystemExit(sys.version_info[:2] != (3, 11) or sysconfig.get_platform() != 'win-amd64')"
$textPythonCheck = 'import sys; raise SystemExit(sys.version_info < (3, 11))'
$python = $null
$pythonArguments = @()

foreach ($name in @('py.exe', 'python3.11.exe', 'python3.exe', 'python.exe')) {
    $command = Get-Command -Name $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $command) {
        continue
    }
    $launcherArguments = @()
    if ($name -eq 'py.exe') {
        $launcherArguments = @('-3.11')
    }
    if (Test-SetupCommand $command.Source ($launcherArguments + @('-c', $python311Check))) {
        $python = $command.Source
        $pythonArguments = $launcherArguments
        break
    }
}
if (-not $python) {
    throw '找不到 Windows x86-64 版的 Python 3.11。請先安裝並確認 PowerShell 可以執行。'
}

$node = Get-Command node.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
$nodeCheck = "const [major, minor] = process.versions.node.split('.').map(Number); process.exit(major > 22 || (major === 22 && minor >= 12) ? 0 : 1);"
if (-not $node -or -not (Test-SetupCommand $node.Source @('-e', $nodeCheck))) {
    throw '需要 Node.js 22.12 以上。'
}

$npm = Get-Command npm.cmd -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $npm -or -not (Test-SetupCommand $npm.Source @('--version'))) {
    throw '找不到可用的 npm.cmd。請確認 Node.js 安裝時包含 npm。'
}

Push-Location -LiteralPath $PSScriptRoot
try {
    $textEnv = 'text_bot/.venv'
    $speechEnv = 'voice_bot/voice_stt/.venv'
    Test-ExistingVenv $textEnv $textPythonCheck
    Test-ExistingVenv $speechEnv $python311Check

    Write-Host ''
    Write-Host '[1/3] 安裝文字 Bot 的 Python 套件'
    Install-PythonEnvironment $textEnv 'text_bot/requirements.txt' $python $pythonArguments
    Write-Host ''
    Write-Host '[2/3] 安裝語音轉寫和摘要的 Python 套件'
    Install-PythonEnvironment $speechEnv 'voice_bot/voice_stt/requirements.txt' $python $pythonArguments
    Write-Host ''
    Write-Host '[3/3] 安裝語音 Bot 的 Node.js 套件'
    Invoke-SetupCommand $npm.Source @('--prefix', 'voice_bot', 'ci') '安裝 Node.js 套件'

    $envFile = Join-Path -Path $PSScriptRoot -ChildPath '.env'
    if (-not (Test-Path -LiteralPath $envFile)) {
        [IO.File]::Copy((Join-Path -Path $PSScriptRoot -ChildPath '.env.example'), $envFile, $false)
    }
    Write-Host ''
    Write-Host '安裝完成。請在根目錄 .env 填寫 Discord Bot Token 和伺服器 ID。'
    Write-Host '若要啟用 OpenAI 摘要，請設定 MEETING_SUMMARIZER=openai 並填寫 OPENAI_API_KEY。'
    Write-Host '啟動指令請見 README.md。'
} finally {
    Pop-Location
}

