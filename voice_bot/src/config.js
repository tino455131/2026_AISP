// Reads and checks the settings in voice_bot/.env.
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const BOT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const REPO_ROOT = path.resolve(BOT_ROOT, '..');

const venvPython = (dir) => (process.platform === 'win32' ? `${dir}/.venv/Scripts/python.exe` : `${dir}/.venv/bin/python`);
const DEFAULT_PYTHON = venvPython('voice_stt');
const DEFAULT_READER_PYTHON = venvPython('discord_bot'); // has discord.py, for the "查看" buttons

const isSnowflake = (text) => /^\d{5,25}$/.test(text);

// The bot asks for these permissions when invited (View Channels, Send Messages, Connect, Change Nickname).
// View Channel, Send Messages, Attach Files, Read Message History, Connect, Change Nickname.
// Read Message History and Attach Files are for /meeting (reading the meeting, long records as a file).
export const INVITE_PERMISSIONS = String((1n << 10n) | (1n << 11n) | (1n << 15n) | (1n << 16n) | (1n << 20n) | (1n << 26n));

/** A bot token's first part is the bot's user id in base64. The id is public, so it is safe to show. */
export function botIdFromToken(token) {
  const parts = token.split('.');
  if (parts.length !== 3) return null;
  const id = Buffer.from(parts[0], 'base64').toString('utf8');
  return /^\d{15,25}$/.test(id) ? id : null;
}

/** Common paste mistakes, described without repeating the token. */
export function tokenProblems(token) {
  const problems = [];
  if (/^bot\s/i.test(token)) problems.push('開頭多了「Bot 」，只要貼後面那串');
  else if (/\s/.test(token)) problems.push('中間有空白或換行');
  if (/^["']|["']$/.test(token)) problems.push('前後多了引號');
  if (problems.length === 0 && !botIdFromToken(token)) {
    problems.push('格式不像 Discord bot token（應該是用兩個「.」隔開的三段）');
  }
  return problems;
}

export function inviteUrl(botId, guildId) {
  const query = new URLSearchParams({
    client_id: botId,
    permissions: INVITE_PERMISSIONS,
    scope: 'bot applications.commands',
    guild_id: guildId,
    disable_guild_select: 'true',
  });
  return `https://discord.com/oauth2/authorize?${query}`;
}

/**
 * Who receives the transcript text when it is summarized, named in the recording notice;
 * null = it stays on this computer. MEETING_SUMMARY_SENDS_TO overrides it for other sources
 * ("none" for a model that runs locally).
 */
export function summaryRecipient(summarizer, override = '') {
  const named = override.trim();
  if (named) return /^(none|no|0|local)$/i.test(named) ? null : named;
  if (summarizer === 'simple') return null;
  if (summarizer === 'claude' || summarizer === 'claude-code') return 'Claude（Anthropic 的 AI）';
  if (summarizer === 'openai') return 'ChatGPT（OpenAI 的 AI）';
  return '外部的 AI 服務';
}

/** Who receives the recorded audio for speech-to-text; null = it is transcribed on this computer. */
export function sttRecipient(engine, override = '') {
  const named = override.trim();
  if (named) return /^(none|no|0|local)$/i.test(named) ? null : named;
  if (engine === 'local') return null;
  if (engine === 'openai') return 'OpenAI';
  return '外部的語音辨識服務';
}

// Startup arguments: a quick way to switch for one run; they override voice_bot/.env.
const ARGS = {
  summarizer: 'MEETING_SUMMARIZER',
  stt: 'STT_ENGINE',
  consent: 'CONSENT_MODE',
  'auto-record': 'AUTO_RECORD',
};
export const USAGE = [
  '用法：npm start -- [選項]　或　node team_bot/start.mjs [選項]',
  '  --summarizer <名稱>   摘要器：simple、claude-code、claude、openai，或 模組路徑:類別名稱',
  '  --stt <名稱>          語音辨識：local（本機 Breeze）、openai，或 模組路徑:類別名稱',
  '  --consent <方式>      錄音同意：direct（進來就錄）或 ask（按了同意才錄）',
  '  --auto-record <on|off> 有人進語音頻道就自動錄音',
  '沒給的選項用 voice_bot/.env 的設定。API key 只能放在 .env，不能當參數。',
].join('\n');

/** ["--stt", "openai", "--summarizer=claude"] -> { env: {STT_ENGINE: "openai", ...}, help }. */
export function argsToEnv(argv) {
  const env = {};
  let help = false;
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--help' || arg === '-h') {
      help = true;
      continue;
    }
    const match = /^--([a-z-]+)(?:=(.*))?$/.exec(arg);
    const key = match && ARGS[match[1]];
    if (!key) throw new Error(`不認得的選項 ${arg}`);
    const value = match[2] ?? argv[(i += 1)];
    if (value === undefined || value.startsWith('--')) throw new Error(`${arg} 後面要接一個值`);
    env[key] = key === 'AUTO_RECORD' ? (/^(on|1|yes|true)$/i.test(value) ? '1' : '0') : value;
  }
  return { env, help };
}

export function loadConfig(env = process.env) {
  const token = (env.DISCORD_TOKEN ?? '').trim();
  if (!token || token === 'your-voice-bot-token-here') {
    throw new Error(
      'DISCORD_TOKEN 還沒填：打開 voice_bot/.env（沒有的話先把 .env.example 複製成 .env），把「語音 bot」自己的 token 貼在 DISCORD_TOKEN= 後面。',
    );
  }

  // Discord ids are bigger than JavaScript numbers can hold exactly: keep them as strings.
  const guildId = (env.DISCORD_GUILD_ID ?? '').trim();
  if (!isSnowflake(guildId)) {
    throw new Error('DISCORD_GUILD_ID 要填伺服器 ID（一串數字）。');
  }

  const leaderRoleId = (env.LEADER_ROLE_ID ?? '').trim() || null;
  if (leaderRoleId && !isSnowflake(leaderRoleId)) {
    throw new Error('LEADER_ROLE_ID 要填身分組 ID（一串數字），或留空。');
  }

  // Automatic recording: on unless AUTO_RECORD=0. AUTO_RECORD_CHANNELS limits it to some voice channels.
  const autoRecord = !/^(0|false|no|off)$/i.test((env.AUTO_RECORD ?? '').trim());
  const channelList = (env.AUTO_RECORD_CHANNELS ?? '').split(',').map((id) => id.trim()).filter(Boolean);
  if (channelList.some((id) => !isSnowflake(id))) {
    throw new Error('AUTO_RECORD_CHANNELS 要填語音頻道 ID（一串數字），多個用逗號分開，或留空代表全部。');
  }

  // direct: everyone in the voice channel is recorded and can press "不要錄我"; ask: only people who press agree.
  const consentMode = (env.CONSENT_MODE ?? '').trim().toLowerCase() || 'direct';
  if (!['direct', 'ask'].includes(consentMode)) {
    throw new Error('CONSENT_MODE 要填 direct（進來就錄，可以按「不要錄我」）或 ask（按了同意才錄）。');
  }

  const silenceMs = Number(env.SILENCE_MS ?? 800);
  if (!Number.isInteger(silenceMs) || silenceMs < 200 || silenceMs > 5000) {
    throw new Error('SILENCE_MS 要是 200 到 5000 之間的整數（毫秒）。');
  }

  const summarizer = (env.MEETING_SUMMARIZER ?? '').trim().toLowerCase() || 'simple';
  const sttEngine = (env.STT_ENGINE ?? '').trim().toLowerCase() || 'local';

  const fromRepo = (value, fallback) => path.resolve(REPO_ROOT, (value ?? '').trim() || fallback);
  return {
    token,
    guildId,
    leaderRoleId,
    consentMode,
    silenceMs,
    // Testing only: keep the consenting people's clips after transcribing so they can be listened to.
    keepAudio: /^(1|true|yes)$/i.test((env.KEEP_AUDIO ?? '').trim()),
    autoRecord,
    autoRecordChannels: channelList.length > 0 ? channelList : null, // null = every voice channel
    // Which meeting_ai summarizer runs after a recording (simple, claude, claude-code or module:Class).
    summarizer,
    summaryRecipient: summaryRecipient(summarizer, env.MEETING_SUMMARY_SENDS_TO ?? ''),
    // Which voice_stt engine transcribes recordings (local, openai or module:Class).
    sttEngine,
    sttRecipient: sttRecipient(sttEngine, env.STT_SENDS_TO ?? ''),
    python: fromRepo(env.STT_PYTHON, DEFAULT_PYTHON),
    readerPython: fromRepo(env.READER_PYTHON, DEFAULT_READER_PYTHON),
    repoRoot: REPO_ROOT,
    sttDir: path.join(REPO_ROOT, 'voice_stt'),
    botDb: fromRepo(env.BOT_DB, 'discord_bot/data/messages.sqlite3'),
    recordingsDir: fromRepo(env.RECORDINGS_DIR, 'voice_bot/recordings'),
  };
}
