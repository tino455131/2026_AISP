// Reads and checks the settings in the project root .env.
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import dotenv from 'dotenv';

export const BOT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const REPO_ROOT = path.resolve(BOT_ROOT, '..');
export const ENV_FILE = path.join(REPO_ROOT, '.env');

export function loadRootEnv() {
  return dotenv.config({ path: ENV_FILE, quiet: true, override: false });
}

const venvPython = (dir) => (process.platform === 'win32' ? `${dir}/.venv/Scripts/python.exe` : `${dir}/.venv/bin/python`);
const STT_ROOT = path.join(BOT_ROOT, 'voice_stt');
const DEFAULT_PYTHON = venvPython(STT_ROOT);
const DEFAULT_READER_PYTHON = venvPython('text_bot'); // has discord.py, for the "查看" buttons

const isSnowflake = (text) => /^\d{5,25}$/.test(text);

// The bot asks for these permissions when invited (View Channels, Send Messages, Connect, Change Nickname).
export const INVITE_PERMISSIONS = String((1n << 10n) | (1n << 11n) | (1n << 20n) | (1n << 26n));

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

export function loadConfig(env = process.env) {
  const token = (env.VOICE_BOT_TOKEN ?? '').trim();
  if (!token || token === 'your-voice-bot-token-here') {
    throw new Error(
      '請在專案根目錄 .env 設定 VOICE_BOT_TOKEN（可先複製根目錄 .env.example）。',
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

  const silenceMs = Number(env.SILENCE_MS ?? 800);
  if (!Number.isInteger(silenceMs) || silenceMs < 200 || silenceMs > 5000) {
    throw new Error('SILENCE_MS 要是 200 到 5000 之間的整數（毫秒）。');
  }

  const fromRepo = (value, fallback) => path.resolve(REPO_ROOT, (value ?? '').trim() || fallback);
  return {
    token,
    guildId,
    leaderRoleId,
    silenceMs,
    // Testing only: keep the consenting people's clips after transcribing so they can be listened to.
    keepAudio: /^(1|true|yes)$/i.test((env.KEEP_AUDIO ?? '').trim()),
    python: fromRepo(env.STT_PYTHON, DEFAULT_PYTHON),
    readerPython: fromRepo(env.READER_PYTHON, DEFAULT_READER_PYTHON),
    repoRoot: REPO_ROOT,
    sttDir: STT_ROOT,
    botDb: fromRepo(env.BOT_DB, 'data/messages.sqlite3'),
    recordingsDir: fromRepo(env.RECORDINGS_DIR, 'voice_bot/recordings'),
  };
}
