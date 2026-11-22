import { AttachmentBuilder, MessageFlags, SlashCommandBuilder } from 'discord.js';

import { getReadableChannel } from './channel_summary.js';
import { runChannelAsk } from './ingest.js';

export const channelAskCommand = new SlashCommandBuilder()
  .setName('ask')
  .setDescription('私人 AI 問答，可詢問一般問題或目前頻道的討論')
  .addStringOption((option) => option
    .setName('question').setDescription('想問什麼？').setRequired(true).setMaxLength(1000));

const messages = {
  ACCESS_DENIED_USER: '你沒有讀取目前頻道歷史訊息的權限。',
  SOURCE_UNAVAILABLE_BOT: 'Bot 沒有讀取目前頻道歷史訊息的權限。',
  PERMISSION_UNVERIFIED: '暫時無法確認你和 Bot 都有來源頻道權限，請稍後再試。',
  OUTSIDE_CHANNEL: '目前只能查詢執行 /ask 的頻道紀錄。',
  NO_HISTORY: '目前頻道還沒有可用的文字紀錄。',
  CONFIGURATION: '問答尚未設定 OpenAI，請聯絡管理員。',
  UPSTREAM_UNAVAILABLE: '暫時無法取得 AI 回覆，請稍後再試。',
  TIMED_OUT: 'AI 回覆逾時，請稍後再試或縮短問題。',
};

export async function askCurrentChannel(
  interaction, config, ask = runChannelAsk, { timeoutMs = 60_000, access = getReadableChannel } = {},
) {
  const question = interaction.options.getString('question', true).trim();
  if (!question) return interaction.reply({ content: '請輸入想詢問的問題。', flags: MessageFlags.Ephemeral });
  await interaction.deferReply({ flags: MessageFlags.Ephemeral });

  const signal = AbortSignal.timeout(timeoutMs);
  let onTimeout;
  const timedOut = new Promise((_, reject) => {
    onTimeout = () => reject(signal.reason);
    signal.addEventListener('abort', onTimeout, { once: true });
  });
  try {
    const result = await Promise.race([ask({
      python: config.readerPython,
      repoRoot: config.repoRoot,
      botDb: config.botDb,
      request: {
        question,
        guild_id: interaction.guildId,
        channel_id: interaction.channelId,
        member_id: interaction.user.id,
      },
      signal,
    }), timedOut]);
    if (!result?.ok) {
      const code = result?.error_code;
      return interaction.editReply(Object.hasOwn(messages, code) ? messages[code] : messages.UPSTREAM_UNAVAILABLE);
    }
    if (result.used_channel_history && !(await Promise.race([access(interaction).catch(() => null), timedOut]))) {
      return interaction.editReply(messages.PERMISSION_UNVERIFIED);
    }

    const allowedMentions = { parse: [] };
    if (result.text.length <= 2000) return interaction.editReply({ content: result.text, allowedMentions });
    const file = new AttachmentBuilder(Buffer.from(result.text, 'utf-8'), { name: 'ai-answer.md' });
    return interaction.editReply({ content: '完整回答請見附件。', files: [file], allowedMentions });
  } catch (error) {
    if (signal.aborted) return interaction.editReply(messages.TIMED_OUT);
    console.error('[問答] 執行失敗：', error.name);
    return interaction.editReply(messages.UPSTREAM_UNAVAILABLE);
  } finally {
    signal.removeEventListener('abort', onTimeout);
  }
}
