import { ApplicationCommandOptionType, AttachmentBuilder, MessageFlags, SlashCommandBuilder } from 'discord.js';

export const helpCommand = new SlashCommandBuilder()
  .setName('help')
  .setDescription('查看 Team Bot 的斜線指令與用途');

function descriptions(parent, command) {
  const name = `${parent} ${command.name}`.trimStart();
  const children = (command.options ?? []).filter(({ type }) =>
    type === ApplicationCommandOptionType.Subcommand || type === ApplicationCommandOptionType.SubcommandGroup,
  );
  return [`**\`/${name}\`**　${command.description}`, ...children.flatMap((child) => descriptions(name, child))];
}

export function showHelp(interaction, commands) {
  const content = [
    '**Team Bot 指令**',
    ...commands.flatMap((command) => descriptions('', command)),
    '使用 `/ask` 時可選 `private:True`，讓回覆只顯示給自己。',
  ].join('\n');
  if (content.length <= 2000) return interaction.reply({ content, flags: MessageFlags.Ephemeral });
  const file = new AttachmentBuilder(Buffer.from(content, 'utf-8'), { name: 'team-bot-help.md' });
  return interaction.reply({ content: '完整指令清單請見附件。', files: [file], flags: MessageFlags.Ephemeral });
}
