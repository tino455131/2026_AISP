import { askCurrentChannel, channelAskCommand } from './channel_ask.js';
import { helpCommand, showHelp } from './help.js';
import { replyFlags } from './replies.js';

// Re-enable the other slash commands here when they are ready for use.
const active = [
  [helpCommand, (interaction) => showHelp(interaction, commands)],
  [channelAskCommand, askCurrentChannel],
];
export const commands = active.map(([definition]) => definition.toJSON());

export async function dispatchSlash(interaction, config) {
  const match = active.find(([definition]) => definition.name === interaction.commandName);
  if (!match) {
    return interaction.reply({ content: '這個指令目前已暫停，請用 /help 查看可用指令。', ...replyFlags(true) });
  }
  return match[1](interaction, config);
}
