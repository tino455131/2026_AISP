// After /record stop, two Python steps run (in voice_stt's virtual environment):
//   1. voice_stt:  recording folder -> transcript in the bot database
//   2. meeting_ai: transcript -> summary, stored in the database
// The "查看" buttons run a third one (in discord_bot's environment, it needs discord.py):
//   meeting_ai.show_session reads for one person through the AI team's reader interface.
import { spawn } from 'node:child_process';
import path from 'node:path';

/** Both Python steps print one line "RESULT {json}" when they succeed. */
export function parseResultLine(stdout) {
  const line = stdout.split(/\r?\n/).find((text) => text.startsWith('RESULT '));
  return line ? JSON.parse(line.slice('RESULT '.length)) : null;
}

function runPython(python, args, cwd, extraEnv = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(python, args, {
      cwd,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', ...extraEnv },
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

/**
 * Summary or transcript of one recording, for one person. Whether they may read it is
 * decided by AuthorizedTranscriptReader asking Discord, not here.
 * Resolves {ok: true, text} or {ok: false, reason: denied|unavailable|not_found|no_summary}.
 */
export function runShow({ python, repoRoot, botDb, token, sessionId, memberId, guildId, what }) {
  const args = ['-m', 'meeting_ai.show_session', sessionId, '--member', memberId, '--guild-id', guildId];
  args.push('--what', what, '--db', botDb);
  return runPython(python, args, repoRoot, { DISCORD_TOKEN: token });
}
