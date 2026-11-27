// /ai tasks | ask | tracked —【測試】在 Discord 裡試 AI 單元（ai_demo）和追蹤進度。
// The bot first checks that the person can read the meeting's channel (View Channel +
// Read Message History, spec R15), then ai_demo reads the meeting and asks the AI. Answers are
// published only when the current channel audience can read the source. For a text meeting the bot reads the original
// messages from Discord right now (spec: read on demand) instead of keeping a copy.
//
// Tracking (test): /ai tasks shows a "追蹤進度" button for formal tasks. The leader's press is
// the confirmation of exactly what was shown (spec ConfirmationPolicy); each owner who can read
// the source channel gets a DM asking for progress; their answer is passed on to the leader.
import { randomUUID } from 'node:crypto';

import {
  ActionRowBuilder,
  AttachmentBuilder,
  ButtonBuilder,
  ButtonStyle,
  ChannelType,
  MessageFlags,
  PermissionFlagsBits,
  SlashCommandBuilder,
} from 'discord.js';

import { isLeader } from './commands.js';
import { runAiDemo } from './ingest.js';
import { readMeetingMessages } from './meetings.js';
import { deliverResult, readSourceAccess } from './replies.js';

const meetingOption = (option) =>
  option.setName('meeting').setDescription('哪一場會議（打字可以搜尋）').setRequired(true).setAutocomplete(true);

export const aiCommand = new SlashCommandBuilder()
  .setName('ai')
  .setDescription('【測試】用 AI 整理會議、詢問內容或查看追蹤')
  .addSubcommand((sub) =>
    sub
      .setName('tasks')
      .setDescription('【測試】從一場會議整理正式任務和待確認提案，可以接著追蹤進度')
      .addStringOption(meetingOption)
      .addUserOption((option) => option.setName('leader').setDescription('組長（沒填：開會或開始錄音的人）')),
  )
  .addSubcommand((sub) =>
    sub
      .setName('ask')
      .setDescription('【測試】問一場會議的問題')
      .addStringOption(meetingOption)
      .addStringOption((option) =>
        option.setName('question').setDescription('想問什麼').setRequired(true).setMaxLength(300),
      ),
  )
  .addSubcommand((sub) => sub.setName('tracked').setDescription('【測試】看追蹤中的任務和最新進度'));

const ephemeral = { flags: MessageFlags.Ephemeral };
const noPings = { allowedMentions: { parse: [] } };
const DISCORD_LIMIT = 2000;
const LIST_TTL_MS = 20000; // the meeting list is cached briefly so search-as-you-type stays fast
const CONFIRM_TTL_MS = 30 * 60 * 1000;
// spec.md: programs decide by ErrorCode, people read the message.
const REFUSED = {
  ACCESS_DENIED_USER: '你沒有權限取得所要求的資訊。',
  PERMISSION_UNVERIFIED: '暫時無法確認你的權限，請稍後再試。',
  NOT_FOUND: '沒有找到符合條件的資料。',
  SOURCE_UNAVAILABLE_BOT: 'Bot 沒有權限讀取所要求的來源。',
  UPSTREAM_UNAVAILABLE: '暫時無法向 Discord 讀取資料，請稍後再試。',
};
// Discord said no to the bot itself (Missing Access / Missing Permissions), not a passing failure.
const BOT_BLOCKED = new Set([50001, 50013]);
const MISSING = {
  explicit_assignment: '不是組長明確指派',
  owner_user_id: '看不出負責人',
  due_at: '沒有明確期限',
  reliable_evidence: '依據都是可能聽錯的句子',
};
export const STATUS = { not_started: '還沒開始', in_progress: '進行中', blocked: '卡住了', completed: '完成了', cancelled: '已取消' };

/**
 * spec AccessDecision: 'allow' | 'deny' | 'unknown' (unknown is never treated as allow).
 * A private thread also needs membership or Manage Threads (spec AC26): the parent's permissions
 * are not enough. `threadMember` is what Discord just said (true / false); without it only the
 * cache is used, and a miss there is 'unknown', not 'deny'.
 */
export function accessTo(member, channel, threadMember) {
  if (!member || !channel) return 'unknown';
  const perms = channel.permissionsFor(member);
  if (!perms) return 'unknown';
  if (!perms.has([PermissionFlagsBits.ViewChannel, PermissionFlagsBits.ReadMessageHistory])) return 'deny';
  if (channel.type !== ChannelType.PrivateThread || perms.has(PermissionFlagsBits.ManageThreads)) return 'allow';
  if (threadMember !== undefined) return threadMember ? 'allow' : 'deny';
  return channel.members?.cache?.has(member.id) ? 'allow' : 'unknown';
}

/** For a private thread, ask Discord whether this person is in it: true / false, or undefined when unsure. */
export async function threadMembership(channel, member) {
  if (channel?.type !== ChannelType.PrivateThread || !member) return undefined;
  return channel.members.fetch({ member: member.id, force: true, cache: false }).then(
    () => true,
    (error) => (error.code === 10007 ? false : undefined), // 10007 Unknown Member: not in the thread
  );
}

export function meetingLabel(meeting, channelName) {
  // Built from parts: the locale's own format puts odd spaces in, which vary between machines.
  const part = Object.fromEntries(
    new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Taipei',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
      .formatToParts(new Date(meeting.started_at))
      .map(({ type, value }) => [type, value]),
  );
  const when = `${part.month}/${part.day} ${part.hour}:${part.minute}`;
  const kind = meeting.kind === 'voice' ? '語音' : '文字';
  return `${kind} ${when} · #${channelName ?? '?'} · ${meeting.line_count} 句`;
}

const who = (id) => (id ? `<@${id}>` : '（未指定）');
const when = (iso) => `<t:${Math.floor(Date.parse(iso) / 1000)}:f>`;

export function formatTasks(result, label) {
  const out = [`🧪 **【測試】AI 整理任務**：${label}`];
  if (!result.leader_user_id) out.push('-# 沒有指定組長：照 spec 全部只會是待確認提案，可以用 leader 選項指定。');
  out.push(`**正式任務（${result.tasks.length}）**`);
  for (const task of result.tasks) out.push(`- ${task.title} — ${who(task.owner_user_id)}，期限 ${when(task.due_at)}`);
  out.push(`**待確認提案（${result.proposals.length}）**`);
  for (const proposal of result.proposals) {
    const reasons = proposal.missing.map((m) => MISSING[m] ?? m).join('、');
    out.push(`- ${proposal.payload.title} — ${who(proposal.payload.owner_user_id)}：${reasons}`);
    out.push(`  ↳ 要問組長：${proposal.question}`);
  }
  if (result.rejected) out.push(`-# 另外有 ${result.rejected} 項找不到依據，已丟掉。`);
  out.push('-# 測試版：AI 只能提案；照 spec，組長明確指派、有負責人、有期限、有依據才算正式任務。只有你看得到。');
  return out.join('\n');
}

export function formatAnswer(result, label) {
  if (!result.ok) return result.message ?? REFUSED.NOT_FOUND;
  return [
    `🧪 **【測試】${label}**`,
    result.answer,
    `-# 依據：第 ${result.source_line_ids.join('、')} 句。只有你看得到。`,
  ].join('\n');
}

/** The DM an owner gets: the spec's sharing notice, and one button per status they may report. */
export function inquiryMessage(task, leaderId, channelName) {
  return {
    content: [
      `📋 **【測試】進度詢問**：組長 <@${leaderId}> 想追蹤這項任務`,
      `**${task.title}**（期限 ${when(task.due_at)}，來自 #${channelName} 的會議）`,
      '本次提交的任務進度將分享給有來源權限的組長。目前進度是？',
    ].join('\n'),
    components: [
      new ActionRowBuilder().addComponents(
        ['not_started', 'in_progress', 'blocked', 'completed'].map((status) =>
          new ButtonBuilder()
            .setCustomId(`progress:${task.task_id}:${status}`)
            .setLabel(STATUS[status])
            .setStyle(status === 'completed' ? ButtonStyle.Success : status === 'blocked' ? ButtonStyle.Danger : ButtonStyle.Secondary),
        ),
      ),
    ],
    ...noPings,
  };
}

export function parseTrackId(customId) {
  const match = /^track:([0-9a-f]{8})$/.exec(customId);
  return match ? match[1] : null;
}

export function parseProgressId(customId) {
  const match = /^progress:(task-[\w-]+):(not_started|in_progress|blocked|completed)$/.exec(customId);
  return match ? { taskId: match[1], status: match[2] } : null;
}

export class AiController {
  constructor(client, config) {
    this.client = client;
    this.config = config;
    this.cache = { at: 0, meetings: [] };
    /** @type {Map<string, object>} confirmation id -> exactly the tasks the leader saw */
    this.pending = new Map();
  }

  #run(args, input = null) {
    const { python, repoRoot, botDb, recordingsDir } = this.config;
    return runAiDemo({ python, repoRoot, botDb, recordingsDir, args, input });
  }

  async #meetings() {
    if (Date.now() - this.cache.at > LIST_TTL_MS) {
      const result = await this.#run(['list']);
      this.cache = { at: Date.now(), meetings: result.ok ? result.meetings : [] };
    }
    return this.cache.meetings;
  }

  async #access(guild, userId, channelId) {
    return readSourceAccess(guild, channelId, userId);
  }

  /** Search-as-you-type: only meetings whose channel this person can read. */
  async autocomplete(interaction) {
    const typed = interaction.options.getFocused().trim().toLowerCase();
    const meetings = await this.#meetings().catch(() => []);
    const member = await interaction.guild.members.fetch(interaction.user.id).catch(() => null);
    const choices = [];
    for (const meeting of meetings) {
      const channel = interaction.guild.channels.cache.get(meeting.channel_id);
      if (accessTo(member, channel) !== 'allow') continue;
      const label = meetingLabel(meeting, channel.name);
      if (typed && !label.toLowerCase().includes(typed) && !meeting.meeting_id.includes(typed)) continue;
      choices.push({ name: label.slice(0, 100), value: meeting.meeting_id });
      if (choices.length === 25) break;
    }
    return interaction.respond(choices);
  }

  async handle(interaction, { options = interaction.options, privateReply = false } = {}) {
    const sub = options.getSubcommand();
    if (sub === 'tracked') return this.#tracked(interaction);
    const meetingId = options.getString('meeting', true);
    await interaction.deferReply(ephemeral);

    this.cache.at = 0; // a meeting that just ended should be found
    const meeting = (await this.#meetings()).find((m) => m.meeting_id === meetingId);
    if (!meeting) return interaction.editReply(REFUSED.NOT_FOUND);
    const { decision, channel } = await this.#access(interaction.guild, interaction.user.id, meeting.channel_id);
    if (decision === 'deny') return interaction.editReply(REFUSED.ACCESS_DENIED_USER);
    if (decision !== 'allow') return interaction.editReply(REFUSED.PERMISSION_UNVERIFIED);
    if (meeting.kind === 'text') {
      // spec: "the bot cannot read the source" is a different answer from "you cannot".
      const me = interaction.guild.members.me ?? (await interaction.guild.members.fetchMe().catch(() => null));
      const bot = accessTo(me, channel, await threadMembership(channel, me));
      if (bot === 'deny') return interaction.editReply(REFUSED.SOURCE_UNAVAILABLE_BOT);
      if (bot !== 'allow') return interaction.editReply(REFUSED.PERMISSION_UNVERIFIED);
    }

    const label = meetingLabel(meeting, channel.name);
    await interaction.editReply(`🧪 AI 正在讀「${label}」…（Claude Code 大約 20～40 秒）`);
    let input = null;
    if (meeting.kind === 'text') {
      const read = await readMeetingMessages(channel, meeting.start_message_id, meeting.end_message_id).catch((e) => e);
      if (read instanceof Error) {
        console.warn('[AI] 讀不到會議訊息：', read.code ?? read.message);
        return interaction.editReply(BOT_BLOCKED.has(read.code) ? REFUSED.SOURCE_UNAVAILABLE_BOT : REFUSED.UPSTREAM_UNAVAILABLE);
      }
      input = JSON.stringify({ messages: read.messages });
    }
    const leader = sub === 'tasks' ? options.getUser('leader') : null;
    const args =
      sub === 'tasks'
        ? ['tasks', meetingId, ...(leader ? ['--leader', leader.id] : [])]
        : ['ask', meetingId, options.getString('question', true)];
    const result = await this.#run(input ? ['--stdin', ...args] : args, input);
    if (!result.ok && sub === 'tasks') return interaction.editReply(REFUSED.NOT_FOUND);
    if (sub === 'tasks') {
      console.log(`[AI] 整理任務：${result.tasks.length} 項正式、${result.proposals.length} 項提案`);
    }

    const text = sub === 'tasks' ? formatTasks(result, label) : formatAnswer(result, label);
    const components = sub === 'tasks' && result.tasks.length ? [this.#trackButton(interaction, meeting, result)] : [];
    let payload = { content: text, components, ...noPings };
    if (text.length > DISCORD_LIMIT) {
      const file = new AttachmentBuilder(Buffer.from(text, 'utf-8'), { name: `ai-${sub}-${meetingId}.md` });
      payload = { ...payload, content: `🧪 **【測試】${label}**：內容比較長，放在附件。`, files: [file] };
    }
    return deliverResult(interaction, payload, {
      privateReply, sourceChannelId: String(meeting.channel_id),
      verifyAccess: async () => (await this.#access(interaction.guild, interaction.user.id, meeting.channel_id)).decision === 'allow',
    });
  }

  /** Remember exactly what was shown; pressing the button confirms that version, nothing else. */
  #trackButton(interaction, meeting, result) {
    const id = randomUUID().slice(0, 8);
    this.pending.set(id, {
      at: Date.now(),
      createdBy: interaction.user.id,
      confirmation: {
        confirmation_id: id,
        meeting_id: meeting.meeting_id,
        guild_id: interaction.guildId,
        channel_id: meeting.channel_id,
        created_by: interaction.user.id,
        tasks: result.tasks,
      },
    });
    return new ActionRowBuilder().addComponents(
      new ButtonBuilder()
        .setCustomId(`track:${id}`)
        .setLabel(`追蹤這 ${result.tasks.length} 項正式任務的進度`)
        .setStyle(ButtonStyle.Primary),
    );
  }

  async button(interaction) {
    const trackId = parseTrackId(interaction.customId);
    if (trackId) return this.#confirmTracking(interaction, trackId);
    const progress = parseProgressId(interaction.customId);
    if (progress) return this.#reportProgress(interaction, progress);
  }

  async #confirmTracking(interaction, id) {
    const pending = this.pending.get(id);
    if (!pending || Date.now() - pending.at > CONFIRM_TTL_MS) {
      return interaction.reply({ content: '這個確認已經過期或用過了，請重新 /ai tasks。', ...ephemeral });
    }
    if (pending.createdBy !== interaction.user.id || !isLeader(interaction.member, this.config.leaderRoleId)) {
      return interaction.reply({ content: '只有下這個指令的組長可以確認追蹤（spec：正式派工是組長的權限）。', ...ephemeral });
    }
    await interaction.deferReply(ephemeral);
    const { confirmation } = pending;
    const guild = interaction.guild;
    const leaderAccess = await this.#access(guild, interaction.user.id, confirmation.channel_id);
    if (leaderAccess.decision !== 'allow' || !isLeader(leaderAccess.member, this.config.leaderRoleId)) {
      return interaction.editReply(REFUSED.PERMISSION_UNVERIFIED);
    }
    if (this.pending.get(id) !== pending) return interaction.editReply('這個確認已經用過了。');
    this.pending.delete(id);
    const channel = leaderAccess.channel;

    // spec R18: an owner who cannot read the source channel is not messaged; the leader decides.
    const access = {};
    for (const task of confirmation.tasks) {
      access[task.owner_user_id] ??= (await this.#access(guild, task.owner_user_id, confirmation.channel_id)).decision;
      task.activation_state = access[task.owner_user_id] === 'allow' ? 'active' : 'awaiting_leader_decision';
    }
    const saved = await this.#run(['--stdin', 'track'], JSON.stringify(confirmation));
    if (!saved.ok) return interaction.editReply({ content: saved.message, components: [] });

    const lines = [`📋 **【測試】開始追蹤 ${saved.tasks.length} 項任務**`];
    let sent = 0;
    for (const task of saved.tasks) {
      if (task.activation_state !== 'active') {
        const why = access[task.owner_user_id] === 'deny' ? '看不到來源頻道' : '暫時無法確認權限';
        lines.push(`- ${task.title} → ${who(task.owner_user_id)} ${why}，先不私訊，等你決定（spec R18）`);
        continue;
      }
      let delivery = 'sent';
      let messageId = null;
      try {
        const user = await this.client.users.fetch(task.owner_user_id);
        const dm = await user.send(inquiryMessage(task, confirmation.created_by, channel?.name ?? '?'));
        messageId = dm.id;
        sent += 1;
      } catch (error) {
        // Discord refused (e.g. 50007: DMs closed) → delivery_failed. No answer at all (network,
        // timeout, 5xx) → delivery_unknown: it may have arrived, so it is neither "sent" nor resent.
        // Either way it never moves to a public channel (R10).
        delivery = error.status >= 400 && error.status < 500 ? 'delivery_failed' : 'delivery_unknown';
        console.warn('[追蹤] 私訊失敗：', error.code ?? error.message);
      }
      await this.#run(['inquiry', '--task', task.task_id, '--owner', task.owner_user_id, '--delivery', delivery, ...(messageId ? ['--message', messageId] : [])]);
      lines.push(
        {
          sent: `- ${task.title} → 已私訊 ${who(task.owner_user_id)} 詢問進度`,
          delivery_failed: `- ${task.title} → 私訊 ${who(task.owner_user_id)} 失敗（對方可能關閉私訊），不會改貼到公開頻道`,
          delivery_unknown: `- ${task.title} → 不確定私訊 ${who(task.owner_user_id)} 有沒有送到（Discord 沒有回應），不會重送`,
        }[delivery],
      );
    }
    lines.push('-# 負責人按下進度後，bot 會私訊通知你。測試版只問這一次，沒有定期提醒。');
    console.log(`[追蹤] 建立 ${saved.tasks.length} 項，私訊成功 ${sent} 項`);
    return interaction.editReply({ content: lines.join('\n'), components: [], ...noPings });
  }

  /** An owner pressed a status button in the DM. */
  async #reportProgress(interaction, { taskId, status }) {
    const result = await this.#run(['progress', '--task', taskId, '--user', interaction.user.id, '--status', status]);
    if (!result.ok) return interaction.reply({ content: result.message, ...ephemeral });
    const task = result.task;
    const base = interaction.message.content.split('\n').filter((line) => !line.startsWith('✅ 已回報')).join('\n');
    const now = Math.floor(Date.now() / 1000);
    await interaction.update({
      content: `${base}\n✅ 已回報：**${STATUS[status]}**（<t:${now}:t>）。之後有變化可以再按。`,
      ...noPings,
    });
    console.log(`[追蹤] 負責人回報：${status}`);

    // spec R10: progress goes to the leader by DM, only if the leader can read the source channel.
    const guild = this.client.guilds.cache.get(String(task.guild_id));
    const { decision } = guild ? await this.#access(guild, String(task.created_by), String(task.channel_id)) : {};
    if (decision !== 'allow') return;
    const leader = await this.client.users.fetch(String(task.created_by)).catch(() => null);
    await leader
      ?.send({ content: `📈 **【測試】進度回報**：${who(task.owner_user_id)} 回報「${task.title}」：**${STATUS[status]}**`, ...noPings })
      .catch((error) => console.warn('[追蹤] 通知組長失敗：', error.code ?? error.message));
  }

  async #tracked(interaction) {
    await interaction.deferReply(ephemeral);
    const result = await this.#run(['tracked', '--guild', interaction.guildId]);
    const currentUser = interaction.user.id;
    const accessByChannel = new Map();
    const visible = [];
    for (const task of result.tasks ?? []) {
      const owner = String(task.owner_user_id) === currentUser;
      const leader = String(task.created_by) === currentUser && isLeader(interaction.member, this.config.leaderRoleId);
      if (!owner && !leader) continue;
      const channelId = String(task.channel_id);
      if (!accessByChannel.has(channelId)) {
        const { decision } = await this.#access(interaction.guild, currentUser, channelId);
        accessByChannel.set(channelId, decision === 'allow');
      }
      if (accessByChannel.get(channelId)) visible.push(task);
      if (visible.length === 30) break;
    }
    if (visible.length === 0) return interaction.editReply('目前沒有你看得到的追蹤中任務。');
    const lines = ['📋 **【測試】追蹤中的任務**'];
    for (const task of visible.slice(0, 30)) {
      const waiting = task.activation_state === 'awaiting_leader_decision' ? '（等組長決定）' : '';
      lines.push(`- ${task.title} — ${who(task.owner_user_id)}：**${STATUS[task.status] ?? task.status}**${waiting}，期限 ${when(task.due_at)}`);
    }
    return interaction.editReply({ content: lines.join('\n').slice(0, DISCORD_LIMIT), ...noPings });
  }
}
