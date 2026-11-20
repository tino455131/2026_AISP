// npm run check: checks voice_bot/.env without ever printing the token.
// It asks Discord (and only Discord) whether the token works and whether the bot is in the server.
// npm run check -- --offline skips that and only checks the file.
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

import dotenv from 'dotenv';

import { BOT_ROOT, argsToEnv, botIdFromToken, inviteUrl, loadConfig, tokenProblems } from './config.js';

const ENV_FILE = path.join(BOT_ROOT, '.env');
const API = 'https://discord.com/api/v10';

let warnings = 0;
const ok = (text) => console.log(`✅ ${text}`);
const warn = (text) => {
  warnings += 1;
  console.log(`⚠️ ${text}`);
};
const fail = (text) => {
  console.log(`❌ ${text}`);
  process.exit(1);
};

/** An OpenAI-based part needs the key in .env and the openai package in voice_stt's Python. */
function checkOpenAI(config, label) {
  if (!(process.env.OPENAI_API_KEY ?? '').trim()) return warn(`${label}，但 .env 沒有 OPENAI_API_KEY：會失敗`);
  const probe = spawnSync(config.python, ['-c', 'import openai'], { encoding: 'utf8' });
  if (probe.status !== 0) return warn(`${label}，但 voice_stt/.venv 沒有 openai 套件：執行 pip install openai`);
  return ok(`${label}，OPENAI_API_KEY 已填（內容不顯示）`);
}

function checkFile() {
  if (!fs.existsSync(ENV_FILE)) fail('找不到 voice_bot/.env：先把 .env.example 複製成 .env。');
  dotenv.config({ path: ENV_FILE, quiet: true });
  // npm run check -- --summarizer openai: check the same choices the bot would start with.
  Object.assign(process.env, argsToEnv(process.argv.slice(2).filter((a) => a !== '--offline')).env);

  let config;
  try {
    config = loadConfig();
  } catch (error) {
    fail(error.message);
  }

  const problems = tokenProblems(config.token);
  if (problems.length > 0) fail(`DISCORD_TOKEN 看起來貼錯了：${problems.join('、')}。`);
  ok(`DISCORD_TOKEN 已填（屬於 bot ID ${botIdFromToken(config.token)}，內容不顯示）`);
  ok(`DISCORD_GUILD_ID = ${config.guildId}`);
  if (config.leaderRoleId) ok(`LEADER_ROLE_ID = ${config.leaderRoleId}`);
  else ok('LEADER_ROLE_ID 留空：有「管理伺服器」權限的人才能用 /record');

  if (config.autoRecord) {
    const where = config.autoRecordChannels ? `只在 ${config.autoRecordChannels.join('、')}` : '所有語音頻道';
    ok(`自動錄音：開啟（${where}）；有人進語音頻道就開始。AUTO_RECORD=0 可以關掉`);
  } else ok('自動錄音：關閉，要用 /record start 開始');
  ok(
    config.consentMode === 'direct'
      ? '錄音同意：direct，頻道裡的人都會錄，可以按「不要錄我」退出（CONSENT_MODE=ask 改回按同意才錄）'
      : '錄音同意：ask，只錄按了「同意錄音」的人',
  );
  if (config.keepAudio) warn('KEEP_AUDIO 開著（測試模式）：錄音轉完不會刪除。測完請關掉，並刪掉 voice_bot/recordings 裡的檔案');

  if (fs.existsSync(config.python)) ok('找到語音辨識的 Python 環境');
  else warn(`找不到 ${config.python}：錄完音會無法轉文字（見 voice_stt 的 README）`);
  if (fs.existsSync(config.readerPython)) ok('找到 discord_bot 的 Python 環境（「查看摘要／逐字稿」按鈕用）');
  else warn(`找不到 ${config.readerPython}：「查看」按鈕會無法使用（見 discord_bot 的 README）`);

  const summarizer = (process.env.MEETING_SUMMARIZER ?? '').trim() || 'simple';
  if (summarizer === 'claude') {
    if ((process.env.ANTHROPIC_API_KEY ?? '').trim()) ok('摘要器：claude，ANTHROPIC_API_KEY 已填（內容不顯示，每次摘要都會花錢）');
    else warn('MEETING_SUMMARIZER=claude，但沒有 ANTHROPIC_API_KEY：摘要會失敗');
  } else if (summarizer === 'openai') {
    checkOpenAI(config, '摘要器：openai（ChatGPT API，每次呼叫都會花錢）');
  } else if (summarizer === 'claude-code') {
    const version = spawnSync('claude', ['--version'], { encoding: 'utf8', shell: process.platform === 'win32' });
    if (version.status === 0) ok(`摘要器：claude-code，用這台電腦已登入的 Claude Code（${version.stdout.trim()}），算在該帳號的訂閱額度`);
    else warn('MEETING_SUMMARIZER=claude-code，但找不到 claude 指令：請先安裝並登入 Claude Code');
  } else {
    ok(`摘要器：${summarizer}`);
  }
  if (config.sttEngine === 'openai') checkOpenAI(config, '語音辨識：openai（錄音會傳到 OpenAI，每次都會花錢）');
  else ok(`語音辨識：${config.sttEngine}`);
  return config;
}

async function discordGet(token, route) {
  return fetch(API + route, {
    headers: { Authorization: `Bot ${token}` },
    signal: AbortSignal.timeout(10_000),
  });
}

async function checkWithDiscord(config) {
  let me;
  try {
    const response = await discordGet(config.token, '/users/@me');
    if (response.status === 401) {
      fail('Discord 說這個 token 無效：到 Developer Portal → Bot → Reset Token 重新產生，再貼一次。');
    }
    if (!response.ok) {
      warn(`Discord 回應 ${response.status}，無法確認 token，稍後再試。`);
      return;
    }
    me = await response.json();
  } catch (error) {
    warn(`連不上 Discord（${error.message}），無法確認 token 是否有效。`);
    return;
  }
  ok(`token 有效：bot 名稱 ${me.username}`);

  const guild = await discordGet(config.token, `/guilds/${config.guildId}`).catch(() => null);
  if (guild?.ok) {
    ok(`bot 已經在伺服器「${(await guild.json()).name}」裡`);
  } else {
    warn('bot 還不在這個伺服器裡（或 DISCORD_GUILD_ID 填錯）。用這個網址邀請它：');
    console.log(`   ${inviteUrl(me.id, config.guildId)}`);
  }
}

const config = checkFile();
if (process.argv.includes('--offline')) {
  console.log('（--offline：沒有連 Discord 確認 token）');
} else {
  await checkWithDiscord(config);
}
console.log(warnings === 0 ? '\n設定都沒問題，可以 npm start。' : `\n有 ${warnings} 個提醒，看上面的 ⚠️。`);
