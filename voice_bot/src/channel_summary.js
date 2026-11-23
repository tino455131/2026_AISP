import { AttachmentBuilder, ChannelType, MessageFlags, SlashCommandBuilder } from 'discord.js';

import { accessTo, threadMembership } from './ai.js';
import { runChannelSummary } from './ingest.js';
import { deliverResult } from './replies.js';

export const channelSummaryCommand = new SlashCommandBuilder()
  .setName('summary_this_channel')
  .setDescription('摘要目前頻道最近 100 則已記錄的文字訊息');

const noPings = { allowedMentions: { parse: [] } };

async function canRead(member, channel) {
  if (accessTo(member, channel, false) === 'allow') return true;
  if (!member || channel.type !== ChannelType.PrivateThread) return false;
  const joined = await threadMembership(channel, member);
  return accessTo(member, channel, joined === true) === 'allow';
}

export async function getReadableChannel(interaction) {
  const { guild, channelId, user, client } = interaction;
  if (!guild) return null;
  const [channel, member, bot] = await Promise.all([
    guild.channels.fetch(channelId, { force: true }),
    guild.members.fetch({ user: user.id, force: true }),
    guild.members.fetch({ user: client.user.id, force: true }),
  ]);
  if (!channel?.isTextBased() || !channel.messages) return null;
  // Permissions on threads come from their parent channel.
  if (channel.isThread() && !(await guild.channels.fetch(channel.parentId, { force: true }))) return null;
  const [userCanRead, botCanRead] = await Promise.all([canRead(member, channel), canRead(bot, channel)]);
  return userCanRead && botCanRead ? channel : null;
}

export async function summarizeCurrentChannel(interaction, config, summarize = runChannelSummary, { privateReply = false } = {}) {
  await interaction.deferReply({ flags: MessageFlags.Ephemeral });
  const unavailable = '無法確認你和 Bot 都有目前頻道的檢視與歷史訊息讀取權限。請在可讀取歷史訊息的頻道重試。';

  try {
    const channel = await getReadableChannel(interaction).catch(() => null);
    if (!channel) return interaction.editReply(unavailable);

    const result = await summarize({
      python: config.python,
      repoRoot: config.repoRoot,
      botDb: config.botDb,
      guildId: interaction.guildId,
      channelId: channel.id,
    });
    if (!result.count) return interaction.editReply('目前頻道還沒有可摘要的文字紀錄。');
    const heading = `**頻道摘要**（最近 ${result.count} 則已記錄文字）`;
    const content = `${heading}\n${result.summary}`;
    let payload = { content, ...noPings };
    if (content.length > 2000) {
      const file = new AttachmentBuilder(Buffer.from(content, 'utf-8'), { name: 'channel-summary.md' });
      payload = { ...payload, content: `${heading}\n完整摘要請見附件。`, files: [file] };
    }
    return await deliverResult(interaction, payload, {
      privateReply, sourceChannelId: interaction.channelId,
      verifyAccess: async () => Boolean(await getReadableChannel(interaction).catch(() => null)),
    });
  } catch (error) {
    console.error('[頻道摘要] 執行失敗：', error.name);
    return interaction.editReply('無法產生頻道摘要，請稍後再試或請管理員確認摘要器設定。');
  }
}
