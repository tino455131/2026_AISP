// /meeting start | end | status: a text meeting led by the team leader (spec R05).
// The bot remembers the message where the meeting started. At the end it reads that channel's
// messages between the two boundaries straight from Discord, has meeting_ai summarize them,
// and posts the record in the same channel. Bot messages are not part of the meeting.
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

import { AttachmentBuilder, MessageFlags, PermissionFlagsBits, SlashCommandBuilder } from 'discord.js';

import { isLeader } from './commands.js';
import { runTextMeeting } from './ingest.js';

export const meetingCommand = new SlashCommandBuilder()
  .setName('meeting')
  .setDescription('文字會議：組長開始、結束，結束後在這個頻道貼出會議紀錄')
  .addSubcommand((sub) => sub.setName('start').setDescription('在這個頻道開始文字會議（組長）'))
  .addSubcommand((sub) => sub.setName('end').setDescription('結束這個頻道的文字會議，整理成會議紀錄（組長）'))
  .addSubcommand((sub) => sub.setName('status').setDescription('看這個頻道有沒有進行中的會議'));

const ephemeral = { flags: MessageFlags.Ephemeral };
const silent = { flags: MessageFlags.SuppressNotifications };
const noPings = { allowedMentions: { parse: [] } }; // mentions show as names but notify nobody
const DISCORD_LIMIT = 2000;
const MAX_MESSAGES = 2000; // a meeting longer than this is cut, and the record says so
const NEEDED = [
  [PermissionFlagsBits.ViewChannel, '檢視頻道'],
  [PermissionFlagsBits.SendMessages, '傳送訊息'],
  [PermissionFlagsBits.ReadMessageHistory, '讀取訊息歷史'],
];

const unix = (iso) => Math.floor(new Date(iso).getTime() / 1000);

/** A discord.js Message as the plain object meeting_ai expects (plus bot/system flags for filtering). */
export function toMeetingMessage(message) {
  return {
    message_id: message.id,
    author_id: message.author.id,
    name: message.member?.displayName ?? message.author.globalName ?? message.author.username,
    created_at: message.createdAt.toISOString(),
    text: message.content ?? '',
    // People @mentioned in the message, so meeting_ai can label them even if they never wrote.
    mentions: [...(message.mentions?.users?.values() ?? [])].map((user) => ({
      id: user.id,
      name: message.mentions.members?.get(user.id)?.displayName ?? user.globalName ?? user.username,
    })),
    bot: Boolean(message.author.bot || message.webhookId),
    system: Boolean(message.system),
  };
}

/**
 * The meeting's own messages: strictly between the start and end messages, written by people,
 * with text, oldest first. Ids are compared as numbers (Discord ids grow with time).
 */
export function pickMeetingMessages(messages, { afterId, beforeId }) {
  const after = BigInt(afterId);
  const before = BigInt(beforeId);
  return messages
    .filter((m) => BigInt(m.message_id) > after && BigInt(m.message_id) < before)
    .filter((m) => !m.bot && !m.system && m.text.trim())
    .sort((a, b) => (BigInt(a.message_id) < BigInt(b.message_id) ? -1 : 1))
    .map(({ bot, system, ...rest }) => rest); // eslint-disable-line no-unused-vars
}

/**
 * Every message between the two boundaries, read from Discord 100 at a time (spec: read the
 * readable history on demand). Used at /meeting end, and again by /ai so the original text
 * does not have to be stored.
 */
export async function readMeetingMessages(channel, startId, endId) {
  const collected = [];
  let after = startId;
  for (;;) {
    const batch = [...(await channel.messages.fetch({ after, limit: 100 })).values()].map(toMeetingMessage);
    if (batch.length === 0) break;
    collected.push(...batch);
    const newest = batch.reduce((max, m) => (BigInt(m.message_id) > BigInt(max) ? m.message_id : max), after);
    if (BigInt(newest) >= BigInt(endId) || batch.length < 100) break;
    after = newest;
  }
  const messages = pickMeetingMessages(collected, { afterId: startId, beforeId: endId });
  return { messages: messages.slice(0, MAX_MESSAGES), truncated: messages.length > MAX_MESSAGES };
}

/** The text of the record posted when the meeting ends. */
export function recordText({ meeting, endedAt, count, markdown, truncated = false }) {
  return [
    `📋 **會議紀錄**：<@${meeting.startedBy}> 主持，<t:${unix(meeting.startedAt)}:t>–<t:${unix(endedAt)}:t>，${count} 則發言`,
    ...(truncated ? [`-# 會議太長，只整理了前 ${MAX_MESSAGES} 則。`] : []),
    markdown,
    '-# 待辦是從討論整理出的候選，正式任務仍要組長確認。',
  ].join('\n');
}

export class MeetingController {
  constructor(client, config) {
    this.client = client;
    this.config = config;
    /** @type {Map<string, object>} channel id -> active meeting */
    this.active = new Map();
    // Kept on disk so a restart in the middle of a meeting does not lose its start.
    this.file = path.join(config.recordingsDir, 'active-meetings.json');
  }

  async load() {
    try {
      for (const meeting of JSON.parse(await readFile(this.file, 'utf8'))) this.active.set(meeting.channelId, meeting);
    } catch {
      // no file yet: no meeting in progress
    }
  }

  async #save() {
    await mkdir(path.dirname(this.file), { recursive: true });
    await writeFile(this.file, JSON.stringify([...this.active.values()], null, 2));
  }

  async handle(interaction) {
    const sub = interaction.options.getSubcommand();
    if (sub === 'start') return this.#start(interaction);
    if (sub === 'end') return this.#end(interaction);
    return this.#status(interaction);
  }

  async #channel(interaction) {
    return interaction.channel ?? (await this.client.channels.fetch(interaction.channelId));
  }

  async #start(interaction) {
    if (!isLeader(interaction.member, this.config.leaderRoleId)) {
      return interaction.reply({ content: '只有組長可以開始會議。', ...ephemeral });
    }
    const channel = await this.#channel(interaction);
    if (!channel?.isTextBased()) return interaction.reply({ content: '請在文字頻道裡開始會議。', ...ephemeral });
    const running = this.active.get(channel.id);
    if (running) {
      return interaction.reply({
        content: `這個頻道已經在開會了（<t:${unix(running.startedAt)}:t> 開始），結束請用 /meeting end。`,
        ...ephemeral,
      });
    }
    const mine = channel.permissionsFor(interaction.guild.members.me);
    const missing = NEEDED.filter(([flag]) => !mine?.has(flag)).map(([, name]) => name);
    if (missing.length) {
      return interaction.reply({ content: `bot 在這個頻道少了權限：${missing.join('、')}，請管理員幫它加上。`, ...ephemeral });
    }

    await interaction.deferReply(ephemeral);
    const recipient = this.config.summaryRecipient;
    const notice = await channel.send({
      content: [
        `📝 **會議開始**：<@${interaction.user.id}> 開始了文字會議。`,
        '- 從現在起到組長下 `/meeting end`，這個頻道的發言會整理成會議紀錄；bot 的訊息不算。',
        ...(recipient ? [`- 結束時，這段訊息會交給 ${recipient} 整理。`] : []),
      ].join('\n'),
      ...silent,
      ...noPings,
    });
    this.active.set(channel.id, {
      guildId: interaction.guildId,
      channelId: channel.id,
      startedBy: interaction.user.id,
      startedAt: notice.createdAt.toISOString(),
      startMessageId: notice.id,
    });
    await this.#save();
    console.log(`[會議] 開始：#${channel.name ?? channel.id}`);
    return interaction.editReply('已開始會議。結束時請在這個頻道用 /meeting end。');
  }

  async #end(interaction) {
    if (!isLeader(interaction.member, this.config.leaderRoleId)) {
      return interaction.reply({ content: '只有組長可以結束會議。', ...ephemeral });
    }
    const channel = await this.#channel(interaction);
    const meeting = channel && this.active.get(channel.id);
    if (!meeting) return interaction.reply({ content: '這個頻道沒有進行中的會議。', ...ephemeral });

    await interaction.deferReply(ephemeral);
    const status = await channel.send({ content: '⏹ **會議結束**，正在整理紀錄…', ...silent, ...noPings });
    this.active.delete(channel.id);
    await this.#save();
    const endedAt = status.createdAt.toISOString();

    try {
      const { messages, truncated } = await this.#readMeeting(channel, meeting.startMessageId, status.id);
      if (messages.length === 0) {
        await status.edit({ content: '⏹ **會議結束**：這段時間沒有成員發言，不產生紀錄。', ...noPings });
        return interaction.editReply('已結束會議；這段時間沒有發言。');
      }
      const result = await runTextMeeting({
        python: this.config.python,
        repoRoot: this.config.repoRoot,
        botDb: this.config.botDb,
        meeting: {
          guild_id: meeting.guildId,
          channel_id: meeting.channelId,
          started_by: meeting.startedBy,
          started_at: meeting.startedAt,
          ended_at: endedAt,
          start_message_id: meeting.startMessageId,
          end_message_id: status.id,
          messages,
        },
      });
      const text = recordText({ meeting, endedAt, count: messages.length, markdown: result.markdown, truncated });
      if (text.length <= DISCORD_LIMIT) {
        await status.edit({ content: text, ...noPings });
      } else {
        const head = recordText({ meeting, endedAt, count: messages.length, markdown: '內容比較長，完整紀錄在附件。', truncated });
        const file = new AttachmentBuilder(Buffer.from(text, 'utf-8'), { name: `${result.meeting_id}.md` });
        await status.edit({ content: head, files: [file], ...noPings });
      }
      console.log(`[會議] 結束：${messages.length} 則發言，${result.decisions} 項決定、${result.action_items} 項待辦`);
      return interaction.editReply('已結束會議，紀錄貼在這個頻道了。');
    } catch (error) {
      console.error('[會議] 整理失敗：', error);
      await status.edit({ content: `⏹ **會議結束**，但整理紀錄失敗：${error.message}`, ...noPings }).catch(() => {});
      return interaction.editReply(`整理紀錄失敗：${error.message}`);
    }
  }

  async #readMeeting(channel, startId, endId) {
    return readMeetingMessages(channel, startId, endId);
  }

  async #status(interaction) {
    const meeting = this.active.get(interaction.channelId);
    if (!meeting) return interaction.reply({ content: '這個頻道沒有進行中的會議。', ...ephemeral });
    return interaction.reply({
      content: `📝 會議進行中：<@${meeting.startedBy}> 在 <t:${unix(meeting.startedAt)}:t> 開始。結束請用 /meeting end。`,
      ...ephemeral,
      ...noPings,
    });
  }
}
