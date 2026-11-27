// Entry point: node src/index.js (or npm start) inside voice_bot/. Settings come from the root .env.
import { ApplicationFlagsBitField, Client, Events, GatewayIntentBits } from 'discord.js';

import { RecordController } from './commands.js';
import { AiController } from './ai.js';
import { commands, dispatchSlash } from './slash_commands.js';
import { handleMentionMessage } from './mention_chat.js';
import { USAGE, argsToEnv, loadConfig, loadRootEnv } from './config.js';

loadRootEnv();
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

// MessageContent is privileged and must be enabled in the Developer Portal.
const client = new Client({ intents: [
  GatewayIntentBits.Guilds,
  GatewayIntentBits.GuildVoiceStates,
  GatewayIntentBits.GuildMessages,
  GatewayIntentBits.MessageContent,
] });
const controller = new RecordController(client, config);
const ai = new AiController(client, config);

client.once(Events.ClientReady, async (ready) => {
  const guild = await ready.guilds.fetch(config.guildId);
  // This process is the only one that registers commands (the merged text logger registers none).
  await guild.commands.set(commands);
  console.log(`語音錄音 bot 已上線：${ready.user.tag}，服務伺服器 ${guild.name}（${commands.map(({ name }) => `/${name}`).join('、')} 指令已註冊）`);
  const app = await ready.application.fetch();
  const content = ApplicationFlagsBitField.Flags;
  if (!app.flags.any(content.GatewayMessageContent | content.GatewayMessageContentLimited)) {
    console.warn('提醒：Developer Portal 還沒開 Message Content Intent，文字記錄與 @Bot 問答會受影響（見 team_bot/README.md）');
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
  if (interaction.isAutocomplete()) {
    interaction.respond([]).catch((error) => console.error('[指令] 自動完成失敗：', error.message));
    return;
  }
  const aiButton = interaction.isButton() && /^(track|progress):/.test(interaction.customId);
  const work = aiButton
    ? ai.button(interaction)
    : interaction.isChatInputCommand()
      ? dispatchSlash(interaction, config)
      : controller.handle(interaction); // recording and viewer buttons
  work.catch(async (error) => {
    console.error('[指令] 失敗：', error);
    const reply = { content: '指令執行失敗，請稍後再試。' };
    if (interaction.isRepliable()) {
      await (interaction.deferred || interaction.replied ? interaction.editReply(reply) : interaction.reply({ ...reply, flags: 64 })).catch(
        () => {},
      );
    }
  });
});

client.on(Events.MessageCreate, (message) => {
  handleMentionMessage(message, config).catch((error) => {
    // Never log the question, model answer, or upstream error body here.
    console.error('[提及問答] 無法處理訊息：', error.name);
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
