import { AttachmentBuilder, MessageReferenceType, MessageType } from 'discord.js';

import { getReadableChannel } from './channel_summary.js';
import { runChannelAsk } from './ingest.js';

const MAX_QUESTION_LENGTH = 1000;
const noPings = { parse: [], repliedUser: false };
const messages = {
  ACCESS_DENIED_USER: '你沒有讀取目前頻道歷史訊息的權限。',
  SOURCE_UNAVAILABLE_BOT: 'Bot 沒有讀取目前頻道歷史訊息的權限。',
  PERMISSION_UNVERIFIED: '暫時無法確認你和 Bot 都有來源頻道權限，請稍後再試。',
  OUTSIDE_CHANNEL: '只能查詢你目前所在頻道的紀錄。',
  NO_HISTORY: '目前頻道還沒有可用的文字紀錄。',
  CONFIGURATION: '問答尚未設定 OpenAI，請聯絡管理員。',
  UPSTREAM_UNAVAILABLE: '暫時無法取得 AI 回覆，請稍後再試。',
  TIMED_OUT: 'AI 回覆逾時，請稍後再試或縮短問題。',
};

/** null means no explicit mention; an empty string means a mention without a question. */
export function extractMentionQuestion(message, botId) {
  if (!/^\d+$/.test(botId) || typeof message.content !== 'string' || !message.mentions?.users?.has(botId)) {
    return null;
  }
  const mention = new RegExp(`<@!?${botId}>`, 'g');
  // Reply notifications can populate mentions without a literal @Bot in the message.
  if (!mention.test(message.content)) return null;
  return message.content.replace(mention, '').trim();
}

/** Verify the referenced author without relying on whether reply notifications are enabled. */
export async function isReplyToBot(message, botId, { timeoutMs = 5_000 } = {}) {
  const reference = message.reference;
  if (!/^\d+$/.test(botId) || !message.guildId || message.type !== MessageType.Reply || !reference?.messageId
    || reference.type === MessageReferenceType.Forward || reference.channelId !== message.channelId
    || (reference.guildId && reference.guildId !== message.guildId)) {
    return false;
  }

  let timer;
  try {
    const original = await Promise.race([
      message.fetchReference(),
      new Promise((resolve) => {
        timer = setTimeout(() => resolve(null), timeoutMs);
        timer.unref();
      }),
    ]);
    return Boolean(original && original.id === reference.messageId && original.guildId === message.guildId
      && original.channelId === message.channelId && original.author?.id === botId);
  } catch {
    // Deleted messages, missing access and failed lookups do not authorize a conversation.
    return false;
  } finally {
    clearTimeout(timer);
  }
}

/** One public, same-channel mention or reply. Slash interactions keep their private adapter. */
export async function handleMentionMessage(
  message, config, ask = runChannelAsk, { timeoutMs = 60_000, access = getReadableChannel } = {},
) {
  if (!message.guildId || message.guildId !== config.guildId || message.author?.bot || message.webhookId) {
    return false;
  }
  const botId = message.client.user?.id;
  let question = extractMentionQuestion(message, botId);
  if (question === null) {
    if (typeof message.content !== 'string' || !(await isReplyToBot(message, botId))) return false;
    question = message.content.trim();
  }

  if (!question || question.length > MAX_QUESTION_LENGTH) {
    await message.reply({
      content: question ? `問題請控制在 ${MAX_QUESTION_LENGTH} 字元以內，再傳送問題。` : '我可以幫你什麼? 請在訊息裡 @Bot，或回覆我的訊息並附上問題。',
      allowedMentions: noPings,
    });
    return true;
  }

  const signal = AbortSignal.timeout(timeoutMs);
  let onTimeout;
  const timedOut = new Promise((_, reject) => {
    onTimeout = () => reject(signal.reason);
    signal.addEventListener('abort', onTimeout, { once: true });
  });
  let reply;
  try {
    const result = await Promise.race([ask({
      python: config.readerPython,
      repoRoot: config.repoRoot,
      botDb: config.botDb,
      request: {
        question,
        guild_id: message.guildId,
        channel_id: message.channelId,
        member_id: message.author.id,
      },
      signal,
    }), timedOut]);

    if (!result?.ok) {
      const code = result?.error_code;
      reply = { content: Object.hasOwn(messages, code) ? messages[code] : messages.UPSTREAM_UNAVAILABLE };
    } else if (typeof result.text !== 'string' || !result.text.trim() || typeof result.used_channel_history !== 'boolean') {
      reply = { content: messages.UPSTREAM_UNAVAILABLE };
    } else if (result.used_channel_history && !(await Promise.race([access({
      guild: message.guild,
      channelId: message.channelId,
      user: message.author,
      client: message.client,
    }).catch(() => null), timedOut]))) {
      reply = { content: messages.PERMISSION_UNVERIFIED };
    } else if (result.text.length <= 2000) {
      reply = { content: result.text };
    } else {
      reply = {
        content: '完整回答請見附件。',
        files: [new AttachmentBuilder(Buffer.from(result.text, 'utf-8'), { name: 'ai-answer.md' })],
      };
    }
  } catch (error) {
    if (!signal.aborted) console.error('[提及問答] 執行失敗：', error.name);
    reply = { content: signal.aborted ? messages.TIMED_OUT : messages.UPSTREAM_UNAVAILABLE };
  } finally {
    signal.removeEventListener('abort', onTimeout);
  }

  // A normal message reply is public. Do not reuse interaction-only ephemeral flags.
  await message.reply({ ...reply, allowedMentions: noPings });
  return true;
}
