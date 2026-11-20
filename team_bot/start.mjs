// 合併版啟動：同一個 bot 帳號，同時跑
//   1. voice_bot（Node）：語音錄音、/record、/meeting、/ping，所有指令都由它註冊
//   2. 文字記錄（Python，沿用 discord_bot 的程式）：把文字訊息存進同一個資料庫
//
//   node team_bot/start.mjs
//
// 按 Ctrl+C 會一起停。文字記錄如果起不來（例如 Developer Portal 沒開權限），語音和指令照常運作。
import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const python =
  process.platform === 'win32'
    ? path.join(ROOT, 'discord_bot', '.venv', 'Scripts', 'python.exe')
    : path.join(ROOT, 'discord_bot', '.venv', 'bin', 'python');
let stopping = false;

/** Start one part; every line it prints gets a [name] prefix. */
function start(name, command, args, cwd) {
  const child = spawn(command, args, {
    cwd,
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    stdio: ['ignore', 'pipe', 'pipe'], // shares this console, so Ctrl+C reaches it too
  });
  for (const [stream, out] of [
    [child.stdout, process.stdout],
    [child.stderr, process.stderr],
  ]) {
    let buffer = '';
    stream.setEncoding('utf8');
    stream.on('data', (data) => {
      const lines = (buffer + data).split(/\r?\n/);
      buffer = lines.pop();
      for (const line of lines) out.write(`[${name}] ${line}\n`);
    });
  }
  return child;
}

// Startup options (--summarizer, --stt, …) go to voice_bot; see: node team_bot/start.mjs --help
if (process.argv.includes('--help') || process.argv.includes('-h')) {
  spawnSync(process.execPath, ['src/index.js', '--help'], { cwd: path.join(ROOT, 'voice_bot'), stdio: 'inherit' });
  process.exit(0);
}
const voice = start('語音', process.execPath, ['src/index.js', ...process.argv.slice(2)], path.join(ROOT, 'voice_bot'));
const text = existsSync(python)
  ? start('文字', python, [path.join(ROOT, 'team_bot', 'text_logger.py')], ROOT)
  : null;
if (!text) console.warn('[文字] 找不到 discord_bot/.venv，只啟動語音（見 discord_bot/README.md 建立環境）');

text?.on('exit', (code) => {
  if (!stopping) console.warn(`[文字] 文字記錄停了（結束碼 ${code}），語音和指令照常運作。`);
});
voice.on('exit', (code) => {
  stopping = true;
  if (text && text.exitCode === null) text.kill();
  console.log(`[語音] 已結束（結束碼 ${code}）`);
  process.exit(code ?? 0);
});

// Ctrl+C goes to both children by itself; the voice bot then finishes its recording before exiting.
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    stopping = true;
    setTimeout(() => {
      voice.kill();
      text?.kill();
      process.exit(1);
    }, 20000).unref(); // give up after 20 seconds
  });
}
