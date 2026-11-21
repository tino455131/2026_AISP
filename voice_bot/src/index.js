// Entry point: node src/index.js (or npm start) inside voice_bot/.
import path from 'node:path';

import { ApplicationFlagsBitField, Client, Events, GatewayIntentBits, SlashCommandBuilder } from 'discord.js';
import dotenv from 'dotenv';

import { RecordController, recordCommand } from './commands.js';
import { MeetingController, meetingCommand } from './meetings.js';
import { AiController, aiCommand } from './ai.js';
import { BOT_ROOT, USAGE, argsToEnv, loadConfig } from './config.js';

dotenv.config({ path: path.join(BOT_ROOT, '.env'), quiet: true });
try {
  const { env, help } = argsToEnv(process.argv.slice(2));
  if (help) {
    console.log(USAGE);
    process.exit(0);
  }
  Object.assign(process.env, env); // the Python steps (STT, summary) inherit the choice too
} catch (error) {
  console.error(`${error.message}\n${USAGE}`);
  process.exit(1);
}

let config;
try {
  config = loadConfig();
} catch (error) {
  console.error(error.message);
  process.exit(1);
}

// Guilds + GuildVoiceStates are not privileged intents: no extra switches in the Developer Portal.
const client = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildVoiceStates] });
const controller = new RecordController(client, config);
const meetings = new MeetingController(client, config);
const ai = new AiController(client, config);
// Same command as the text bot's /ping, so the merged bot (team_bot) keeps it.
const pingCommand = new SlashCommandBuilder().setName('ping').setDescription('確認 bot 在線上');

client.once(Events.ClientReady, async (ready) => {
  const guild = await ready.guilds.fetch(config.guildId);
  // This process is the only one that registers commands (the merged text logger registers none).
  await guild.commands.set([recordCommand.toJSON(), meetingCommand.toJSON(), aiCommand.toJSON(), pingCommand.toJSON()]);
  await meetings.load();
  console.log(`語音錄音 bot 已上線：${ready.user.tag}，服務伺服器 ${guild.name}（/record、/meeting、/ai、/ping 指令已註冊）`);
  const app = await ready.application.fetch();
  const content = ApplicationFlagsBitField.Flags;
  if (!app.flags.any(content.GatewayMessageContent | content.GatewayMessageContentLimited)) {
    console.warn('提醒：Developer Portal 還沒開 Message Content Intent，/meeting 讀不到訊息內容（見 team_bot/README.md）');
  }
  console.log(`摘要器：${config.summarizer}；語音辨識：${config.sttEngine}`);
  if (config.autoRecord) {
    const where = config.autoRecordChannels ? `${config.autoRecordChannels.length} 個指定的語音頻道` : '所有語音頻道';
    const who = config.consentMode === 'direct' ? '頻道裡的人都會錄，可以按「不要錄我」' : '只錄按了同意的人';
    console.log(`自動錄音：開啟（${where}，有人進來就開始，${who}）`);
    controller.scan(client.guilds.cache.get(config.guildId)); // people may already be in a channel
  }
});

client.on(Events.InteractionCreate, (interaction) => {
  // Progress buttons arrive in DMs (no server); everything else only from this server.
  const dmProgress = !interaction.guildId && interaction.isButton() && interaction.customId.startsWith('progress:');
  if (interaction.guildId !== config.guildId && !dmProgress) return;
  if (interaction.isAutocomplete() && interaction.commandName === 'ai') {
    ai.autocomplete(interaction).catch((error) => console.error('[AI] 自動完成失敗：', error.message));
    return;
  }
  const command = interaction.isChatInputCommand() ? interaction.commandName : null;
  const handlers = {
    meeting: () => meetings.handle(interaction),
    ai: () => ai.handle(interaction),
    ping: () => interaction.reply('Pong! 🏓'),
  };
  const aiButton = interaction.isButton() && /^(track|progress):/.test(interaction.customId);
  const work = aiButton
    ? ai.button(interaction)
    : (handlers[command] ?? (() => controller.handle(interaction)))(); // /record and its buttons
  work.catch(async (error) => {
    console.error('[指令] 失敗：', error);
    const reply = { content: `出錯了：${error.message}`, flags: 64 };
    if (interaction.isRepliable()) {
      await (interaction.deferred || interaction.replied ? interaction.editReply(reply) : interaction.reply(reply)).catch(
        () => {},
      );
    }
  });
});

client.on(Events.VoiceStateUpdate, (oldState, newState) => {
  if (newState.guild.id !== config.guildId) return;
  controller.onVoiceState(oldState, newState).catch((error) => console.error('[語音狀態] 失敗：', error));
});

async function shutdown(signal) {
  console.log(`收到 ${signal}，停止錄音並關閉…`);
  await controller.stopAll('bot 正在關閉');
  await client.destroy();
  process.exit(0);
}
process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));

client.login(config.token);
