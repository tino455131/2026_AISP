// After /record stop, two Python steps run (in voice_stt's virtual environment):
//   1. voice_stt:  recording folder -> transcript in the bot database
//   2. meeting_ai: transcript -> summary (stored too), returned as Discord-ready text
import { spawn } from 'node:child_process';
import path from 'node:path';

/** Both Python steps print one line "RESULT {json}" when they succeed. */
export function parseResultLine(stdout) {
  const line = stdout.split(/\r?\n/).find((text) => text.startsWith('RESULT '));
  return line ? JSON.parse(line.slice('RESULT '.length)) : null;
}

function runPython(python, args, cwd) {
  return new Promise((resolve, reject) => {
    const child = spawn(python, args, {
      cwd,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
      windowsHide: true,
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (data) => (stdout += data));
    child.stderr.on('data', (data) => (stderr += data));
    child.once('error', (error) => reject(new Error(`無法啟動 Python（${python}）：${error.message}`)));
    child.once('close', (code) => {
      const result = parseResultLine(stdout);
      if (code === 0 && result) return resolve(result);
      const tail = (stderr || stdout).trim().split(/\r?\n/).slice(-3).join(' / ');
      reject(new Error(`${args[1]} 失敗（結束碼 ${code}）：${tail}`));
    });
  });
}

export function runIngest({ python, sttDir, sessionDir, botDb, keepAudio = false }) {
  const args = ['-m', 'stt.ingest_recording', sessionDir, '--db', botDb];
  if (keepAudio) args.push('--keep-audio');
  return runPython(python, args, sttDir);
}

export function runSummary({ python, repoRoot, sessionId, sessionDir, botDb }) {
  const args = ['-m', 'meeting_ai.summarize_session', sessionId, '--db', botDb];
  args.push('--names', path.join(sessionDir, 'manifest.json'));
  return runPython(python, args, repoRoot);
}

/** Discord messages are limited to 2000 characters. */
export function fitDiscord(text, limit = 1900) {
  return text.length <= limit ? text : `${text.slice(0, limit)}…\n（摘要太長，完整內容已存進資料庫）`;
}
