// Entry point: node src/index.js (or npm start) inside voice_bot/.
import path from 'node:path';

import { Client, Events, GatewayIntentBits } from 'discord.js';
import dotenv from 'dotenv';

import { RecordController, recordCommand } from './commands.js';
import { BOT_ROOT, loadConfig } from './config.js';

dotenv.config({ path: path.join(BOT_ROOT, '.env'), quiet: true });

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

client.once(Events.ClientReady, async (ready) => {
  const guild = await ready.guilds.fetch(config.guildId);
  await guild.commands.set([recordCommand.toJSON()]);
  console.log(`語音錄音 bot 已上線：${ready.user.tag}，服務伺服器 ${guild.name}（/record 指令已註冊）`);
});

client.on(Events.InteractionCreate, (interaction) => {
  if (interaction.guildId !== config.guildId) return;
  controller.handle(interaction).catch(async (error) => {
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
