// npm run check: checks the project root .env without ever printing the token.
// It asks Discord (and only Discord) whether the token works and whether the bot is in the server.
// npm run check -- --offline skips that and only checks the file.
import fs from 'node:fs';

import { ENV_FILE, botIdFromToken, inviteUrl, loadConfig, loadRootEnv, tokenProblems } from './config.js';

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

function checkFile() {
  if (fs.existsSync(ENV_FILE)) loadRootEnv();

  let config;
  try {
    config = loadConfig();
  } catch (error) {
    fail(error.message);
  }

  const problems = tokenProblems(config.token);
  if (problems.length > 0) fail(`VOICE_BOT_TOKEN 看起來貼錯了：${problems.join('、')}。`);
  ok(`VOICE_BOT_TOKEN 已填（屬於 bot ID ${botIdFromToken(config.token)}，內容不顯示）`);
  ok(`DISCORD_GUILD_ID = ${config.guildId}`);
  if (config.leaderRoleId) ok(`LEADER_ROLE_ID = ${config.leaderRoleId}`);
  else ok('LEADER_ROLE_ID 留空：有「管理伺服器」權限的人才能用 /record');

  if (config.keepAudio) warn('KEEP_AUDIO 開著（測試模式）：錄音轉完不會刪除。測完請關掉，並刪掉 voice_bot/recordings 裡的檔案');

  if (fs.existsSync(config.python)) ok('找到語音辨識的 Python 環境');
  else warn(`找不到 ${config.python}：錄完音會無法轉文字（見 voice_stt 的 README）`);
  if (fs.existsSync(config.readerPython)) ok('找到 text_bot 的 Python 環境（「查看摘要／逐字稿」按鈕用）');
  else warn(`找不到 ${config.readerPython}：「查看」按鈕會無法使用（見 text_bot 的 README）`);

  const summarizer = (process.env.MEETING_SUMMARIZER ?? '').trim().toLowerCase() || 'simple';
  if (summarizer === 'openai') {
    if ((process.env.OPENAI_API_KEY ?? '').trim()) ok('摘要器：openai，OPENAI_API_KEY 已填（內容不顯示，每次摘要都會花錢）');
    else warn('MEETING_SUMMARIZER=openai，但沒有 OPENAI_API_KEY：摘要會失敗');
  } else if (summarizer === 'claude') {
    warn('MEETING_SUMMARIZER=claude 已移除：請改用 openai 並設定 OPENAI_API_KEY');
  } else if (summarizer !== 'simple') {
    warn(`不認得的摘要器 ${summarizer}：請用 simple 或 openai`);
  } else {
    ok(`摘要器：${summarizer}`);
  }
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
