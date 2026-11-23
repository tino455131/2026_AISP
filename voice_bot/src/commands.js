// /record start | stop | status, automatic recording when people join, the consent buttons,
// what happens after stop, and the "查看" buttons.
import { rm } from 'node:fs/promises';

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

import { runIngest, runShow, runSummary } from './ingest.js';
import { RecordingSession } from './recorder.js';

import { deliverResult, readSourceAccess, replyFlags } from './replies.js';

export const recordCommand = new SlashCommandBuilder()
  .setName('record')
  .setDescription('會議錄音：只錄有按「同意」的人，結束後轉成逐字稿')
  .addSubcommand((sub) => sub.setName('start').setDescription('在你所在的語音頻道開始錄音（組長）'))
  .addSubcommand((sub) => sub.setName('stop').setDescription('停止錄音並轉成逐字稿（組長）'))
  .addSubcommand((sub) => sub.setName('status').setDescription('查看目前的錄音狀態'));

const REC_PREFIX = '[REC] ';
const ephemeral = { flags: MessageFlags.Ephemeral };
// Everything the bot posts in the channel is silent: an unread dot, but no sound or pop-up.
const silent = { flags: MessageFlags.SuppressNotifications };
const DISCORD_LIMIT = 2000;

/** Who may start or stop a recording: the leader role, or server managers if none is set. */
export function isLeader(member, leaderRoleId) {
  if (leaderRoleId) return member.roles.cache.has(leaderRoleId);
  return member.permissions.has(PermissionFlagsBits.ManageGuild);
}

// Wait this long after someone joins before starting, so a quick join-and-leave starts nothing.
const AUTO_START_DELAY_MS = 3000;

/**
 * Which voice channel to record automatically: the one with the most people that is allowed,
 * not the AFK channel, not stopped by hand, and joinable. Plain objects keep it testable:
 * [{id, humans, joinable}] -> one of them or null.
 */
export function pickAutoChannel(channels, { allowed = null, afkChannelId = null, suppressed = new Set() } = {}) {
  const ok = channels.filter(
    (ch) =>
      ch.humans > 0 &&
      ch.joinable &&
      ch.id !== afkChannelId &&
      !suppressed.has(ch.id) &&
      (!allowed || allowed.includes(ch.id)),
  );
  return ok.sort((a, b) => b.humans - a.humans)[0] ?? null;
}

/** custom id of a consent button: consent:<agree|refuse>:<session id> */
export function parseConsentId(customId) {
  const match = /^consent:(agree|refuse):(.+)$/.exec(customId);
  return match ? { action: match[1], sessionId: match[2] } : null;
}

/** custom id of a "查看" button: view:<summary|transcript>:<session id> */
export function parseViewId(customId) {
  const match = /^view:(summary|transcript):(.+)$/.exec(customId);
  return match ? { what: match[1], sessionId: match[2] } : null;
}

export function viewButtons(sessionId, { summary = true } = {}) {
  const row = new ActionRowBuilder();
  if (summary) {
    row.addComponents(
      new ButtonBuilder().setCustomId(`view:summary:${sessionId}`).setLabel('查看摘要').setStyle(ButtonStyle.Primary),
    );
  }
  return row.addComponents(
    new ButtonBuilder().setCustomId(`view:transcript:${sessionId}`).setLabel('查看逐字稿').setStyle(ButtonStyle.Secondary),
  );
}

/** direct: "不要錄我" first (everyone is already recorded); ask: agree / refuse. Same custom ids. */
export function consentButtons(sessionId, mode = 'ask') {
  if (mode === 'direct') {
    return new ActionRowBuilder().addComponents(
      new ButtonBuilder().setCustomId(`consent:refuse:${sessionId}`).setLabel('不要錄我').setStyle(ButtonStyle.Danger),
      new ButtonBuilder().setCustomId(`consent:agree:${sessionId}`).setLabel('繼續錄我').setStyle(ButtonStyle.Secondary),
    );
  }
  return new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId(`consent:agree:${sessionId}`).setLabel('同意錄音').setStyle(ButtonStyle.Success),
    new ButtonBuilder()
      .setCustomId(`consent:refuse:${sessionId}`)
      .setLabel('不同意／撤回同意')
      .setStyle(ButtonStyle.Danger),
  );
}

export class RecordController {
  constructor(client, config) {
    this.client = client;
    this.config = config;
    /** @type {Map<string, RecordingSession>} guild id -> the recording there */
    this.sessions = new Map();
    /** @type {Map<string, Set<string>>} session id -> users already reminded */
    this.reminded = new Map();
    this.originalNick = new Map();
    /** @type {Set<string>} channels where a leader stopped by hand: no auto start until they empty */
    this.suppressed = new Set();
    /** @type {Set<string>} guilds where a recording is being started right now */
    this.starting = new Set();
    /** @type {Map<string, NodeJS.Timeout>} guild id -> pending automatic check */
    this.scanTimers = new Map();
    this.closing = false;
  }

  async handle(interaction, { options = interaction.options, privateReply = false } = {}) {
    if (interaction.isChatInputCommand() && (interaction.commandName === 'record' || privateReply)) {
      const sub = options.getSubcommand();
      if (sub === 'start') return this.#start(interaction, privateReply);
      if (sub === 'stop') return this.#stop(interaction, privateReply);
      if (sub === 'status') return this.#status(interaction, privateReply);
    }
    if (interaction.isButton()) {
      const consent = parseConsentId(interaction.customId);
      if (consent) return this.#consent(interaction, consent);
      const view = parseViewId(interaction.customId);
      if (view) return this.#view(interaction, view);
    }
  }

  async #start(interaction, privateReply) {
    const member = interaction.member;
    const channel = member?.voice?.channel;
    if (!channel) return interaction.reply({ content: '請先進入要錄音的語音頻道，再下這個指令。', ...ephemeral });
    if (!isLeader(member, this.config.leaderRoleId)) {
      return interaction.reply({ content: '只有組長可以開始錄音。', ...ephemeral });
    }
    if (this.sessions.has(interaction.guildId) || this.starting.has(interaction.guildId)) {
      return interaction.reply({ content: '這個伺服器已經在錄音了，請先 /record stop。', ...ephemeral });
    }

    await interaction.deferReply(replyFlags(privateReply)); // joining can take longer than Discord's 3 seconds
    let session;
    try {
      session = await this.#begin(channel, member.id);
    } catch (error) {
      return interaction.editReply('開始錄音失敗，請稍後再試。');
    }
    return interaction.editReply('已開始錄音。結束時請用 /record stop。');
  }

  /** Join `channel` and start recording. `startedBy` is null when it started automatically. */
  async #begin(channel, startedBy) {
    const guildId = channel.guild.id;
    this.starting.add(guildId);
    const session = new RecordingSession({
      channel,
      startedBy,
      config: this.config,
      onLost: (reason) => this.#finish(guildId, `⚠️ ${reason}，錄音已自動停止。`),
    });
    session.auto = startedBy === null;
    session.botMessages = []; // taken back if an automatic recording ends with nothing recorded
    try {
      await session.start();
    } catch (error) {
      await rm(session.dir, { recursive: true, force: true }).catch(() => {});
      throw error;
    } finally {
      this.starting.delete(guildId);
    }
    this.sessions.set(guildId, session);
    this.reminded.set(session.sessionId, new Set());
    await this.#markRecording(channel.guild, true);
    const direct = this.config.consentMode === 'direct';
    if (direct) {
      for (const member of session.humansInChannel()) await session.include(member.id, member.displayName);
    }

    const people = session.humansInChannel().map((m) => `<@${m.id}>`).join(' ');
    const who = startedBy ? `<@${startedBy}> 開始了會議錄音。` : '有人進入語音頻道，bot 自動開始會議錄音。';
    const message = await channel
      .send({
        content: [
          `🔴 **錄音中**：${who}${people}`,
          direct
            ? '- 這個語音頻道裡的人**都會被錄音**，之後進來的人也一樣。'
            : '- **只會錄有按「同意錄音」的人**；沒按或按不同意的人，聲音不會被保存。',
          '- 錄音結束後會轉成文字存進 bot 的資料庫，之後只有看得到這個語音頻道的人能透過 bot 讀到。',
          ...(this.config.sttRecipient ? [`- 錄音會交給 ${this.config.sttRecipient} 轉成文字。`] : []),
          ...(this.config.summaryRecipient
            ? [
                `- 逐字稿會交給 ${this.config.summaryRecipient} 整理成摘要${this.config.sttRecipient ? '' : '；錄音檔本身不會送出去'}。`,
              ]
            : []),
          direct
            ? '- 不想被錄可以隨時按「不要錄我」，你這次已錄的部分會被刪除。'
            : '- 隨時可以按「不同意／撤回同意」，你這次已錄的部分會被刪除。',
        ].join('\n'),
        components: [consentButtons(session.sessionId, this.config.consentMode)],
        ...silent,
      })
      .catch((e) => console.warn('[錄音] 無法發同意訊息：', e.message));
    if (message) session.botMessages.push(message);
    if (session.auto) console.log(`[自動錄音] 開始：${channel.name}（${session.sessionId}）`);
    return session;
  }

  async #consent(interaction, { action, sessionId }) {
    const session = this.sessions.get(interaction.guildId);
    if (!session || session.sessionId !== sessionId || session.stopping) {
      return interaction.reply({ content: '這次錄音已經結束了。', ...ephemeral });
    }
    if (interaction.user.bot) return;
    await interaction.deferReply(ephemeral);
    const direct = this.config.consentMode === 'direct';
    if (action === 'agree') {
      await session.agree(interaction.user.id, interaction.member?.displayName ?? interaction.user.username);
      return interaction.editReply(
        direct ? '✅ 好，會繼續錄你。' : '✅ 已同意。接下來你在這個語音頻道的發言會被錄下；隨時可以撤回。',
      );
    }
    const hadAgreed = await session.refuse(interaction.user.id);
    if (!hadAgreed) return interaction.editReply('好的，這次不會錄你的聲音。');
    return interaction.editReply(
      direct
        ? '已停止錄你，並刪除你這次已錄下的聲音。想恢復可以按「繼續錄我」。'
        : '已撤回同意，並刪除你這次已錄下的聲音。之後不會再錄你。',
    );
  }

  async #stop(interaction, privateReply) {
    if (!isLeader(interaction.member, this.config.leaderRoleId)) {
      return interaction.reply({ content: '只有組長可以停止錄音。', ...ephemeral });
    }
    if (!this.sessions.has(interaction.guildId)) {
      return interaction.reply({ content: '目前沒有在錄音。', ...ephemeral });
    }
    await interaction.deferReply(replyFlags(privateReply));
    // Stopped by hand: don't start again in this channel until everyone has left it.
    this.suppressed.add(this.sessions.get(interaction.guildId).channel.id);
    await this.#finish(interaction.guildId, `⏹ <@${interaction.user.id}> 停止了錄音。`);
    return interaction.editReply('已停止錄音，正在轉成文字。語音頻道聊天室裡那則訊息會隨進度更新（靜音，不會吵到大家）。');
  }

  async #status(interaction, privateReply) {
    const session = this.sessions.get(interaction.guildId);
    if (!session) return interaction.reply({ content: '目前沒有在錄音。', ...replyFlags(privateReply) });
    await interaction.deferReply(ephemeral);
    const minutes = Math.floor((Date.now() - session.startedAt.getTime()) / 60000);
    const recorded = session.consent.recordedUsers().map((id) => `<@${id}>`).join('、') || '（目前沒有）';
    return deliverResult(interaction, {
      content: `🔴 錄音中：<#${session.channel.id}>，已 ${minutes} 分鐘，${session.manifest.clips.length} 段發言。\n正在錄的人：${recorded}`,
      allowedMentions: { parse: [] },
    }, {
      privateReply, sourceChannelId: session.channel.id,
      verifyAccess: async () => (await readSourceAccess(interaction.guild, session.channel.id, interaction.user.id)).decision === 'allow',
    });
  }

  /** Stop a recording (command, channel empty, connection lost), then transcribe it. */
  async #finish(guildId, notice) {
    const session = this.sessions.get(guildId);
    if (!session || session.stopping) return;
    const clips = await session.stop();
    this.sessions.delete(guildId);
    this.reminded.delete(session.sessionId);
    await this.#markRecording(session.channel.guild, false);
    this.scan(session.channel.guild); // people may be waiting in another channel

    const post = (content, components = []) =>
      session.channel.send({ content, components, ...silent }).catch((e) => {
        console.warn('[錄音] 無法發訊息：', e.message);
        return null;
      });
    if (clips === 0) {
      // Nothing recorded: no folder is kept. An automatic start also takes its messages back,
      // so someone dropping into a channel for a moment leaves no trace in the chat.
      await rm(session.dir, { recursive: true, force: true }).catch(() => {});
      if (session.auto) {
        await Promise.allSettled(session.botMessages.map((m) => m.delete()));
        return;
      }
      await post(`${notice}\n沒有錄到任何同意者的發言，不會產生逐字稿。`);
      return;
    }
    // One message, edited as the work goes on (edits notify nobody).
    const status = await post(`${notice}\n共 ${clips} 段發言，正在轉成文字…`);
    const update = (content, components = []) =>
      status
        ? status.edit({ content, components }).catch((e) => console.warn('[錄音] 無法更新訊息：', e.message))
        : post(content, components);

    const { python, sttDir, repoRoot, botDb, keepAudio } = this.config;
    let ingested;
    try {
      ingested = await runIngest({ python, sttDir, sessionDir: session.dir, botDb, keepAudio });
    } catch (error) {
      console.error('[錄音] 轉文字失敗：', error);
      await update(`${notice}\n⚠️ 轉文字失敗：${error.message}\n錄音檔保留在主機上（${session.sessionId}），可以修好後再處理。`);
      return;
    }
    const audioNote = keepAudio ? '錄音檔保留在主機上（測試模式 KEEP_AUDIO）。' : '錄音檔已刪除。';
    if (ingested.saved_lines === 0) {
      await update(`${notice}\n沒有辨識出任何句子。${audioNote}`);
      return;
    }
    await update(`${notice}\n已轉成 ${ingested.saved_lines} 句，正在整理摘要…`);

    // The summary goes through the swappable meeting_ai interface and is only stored;
    // nobody gets it pushed to them. People open it with the buttons, one at a time.
    let summaryNote = '摘要已存。';
    let hasSummary = true;
    try {
      await runSummary({ python, repoRoot, sessionId: ingested.session_id, sessionDir: session.dir, botDb });
    } catch (error) {
      console.error('[錄音] 摘要失敗：', error);
      summaryNote = `⚠️ 摘要失敗：${error.message}`;
      hasSummary = false;
    }
    await update(
      [
        notice,
        `✅ 會議紀錄完成：逐字稿 ${ingested.saved_lines} 句。${summaryNote}${audioNote}`,
        '-# 看得到這個頻道的人都可以按下面的按鈕，內容只有按的人自己看得到。',
      ].join('\n'),
      [viewButtons(ingested.session_id, { summary: hasSummary })],
    );
  }

  /** "查看摘要／逐字稿": read for the person who pressed, shown only to them. */
  async #view(interaction, { what, sessionId }) {
    await interaction.deferReply(ephemeral); // the permission check takes a few seconds
    const { readerPython, repoRoot, botDb, token } = this.config;
    let result;
    try {
      result = await runShow({
        python: readerPython,
        repoRoot,
        botDb,
        token,
        sessionId,
        memberId: interaction.user.id,
        guildId: interaction.guildId,
        what,
      });
    } catch (error) {
      console.error('[查看] 讀取失敗：', error);
      return interaction.editReply(`讀取失敗：${error.message}`);
    }
    // Refusals carry spec.md's ErrorCode plus the message to show (written by show_session).
    if (!result.ok) return interaction.editReply(result.message ?? `讀不到（${result.error_code}）`);
    if (result.text.length <= DISCORD_LIMIT) {
      return interaction.editReply({ content: result.text, allowedMentions: { parse: [] } });
    }
    return interaction.editReply({
      content: '內容比較長，放在附件裡（一樣只有你看得到）。',
      files: [new AttachmentBuilder(Buffer.from(result.text, 'utf-8'), { name: `${what}-${sessionId}.md` })],
    });
  }

  /** Remind people who join during a recording; stop when everyone has left; start when someone joins. */
  async onVoiceState(oldState, newState) {
    const guild = newState.guild;
    const user = newState.member?.user;
    const left = oldState.channel;
    if (left && this.suppressed.has(left.id) && ![...left.members.values()].some((m) => !m.user.bot)) {
      this.suppressed.delete(left.id); // that channel is empty now: automatic recording may start there again
    }

    const session = this.sessions.get(guild.id);
    if (session && !session.stopping) {
      const channelId = session.channel.id;
      if (newState.channelId === channelId && oldState.channelId !== channelId && user && !user.bot) {
        const reminded = this.reminded.get(session.sessionId);
        const direct = this.config.consentMode === 'direct';
        if (session.consent.status(user.id) === 'pending' && !reminded.has(user.id)) {
          reminded.add(user.id);
          if (direct) await session.include(user.id, newState.member.displayName); // recorded from now on
          const reminder = await session.channel
            .send({
              content: direct
                ? `<@${user.id}> 這裡正在錄音，你的聲音會被錄下；不想被錄請按上方訊息的「不要錄我」。`
                : `<@${user.id}> 這裡正在錄音，請在上方訊息按「同意錄音」或「不同意」；沒按就不會錄你。`,
              ...silent,
            })
            .catch(() => null);
          if (reminder) session.botMessages.push(reminder);
        }
      }
      if (oldState.channelId === channelId && session.humansInChannel().length === 0) {
        await this.#finish(guild.id, '⏹ 大家都離開了，錄音自動停止。');
      }
    }
    if (user && !user.bot && newState.channelId && newState.channelId !== oldState.channelId) this.scan(guild);
  }

  /** Start recording automatically (AUTO_RECORD) once someone has been in a voice channel for a moment. */
  scan(guild) {
    if (!this.config.autoRecord || this.closing) return;
    clearTimeout(this.scanTimers.get(guild.id));
    this.scanTimers.set(
      guild.id,
      setTimeout(() => {
        this.scanTimers.delete(guild.id);
        this.#autoStart(guild).catch((error) => console.warn('[自動錄音] 無法開始：', error.message));
      }, AUTO_START_DELAY_MS),
    );
  }

  async #autoStart(guild) {
    if (this.closing || this.sessions.has(guild.id) || this.starting.has(guild.id)) return;
    const voiceChannels = [...guild.channels.cache.values()].filter((ch) => ch.type === ChannelType.GuildVoice);
    const picked = pickAutoChannel(
      voiceChannels.map((ch) => ({
        id: ch.id,
        humans: [...ch.members.values()].filter((m) => !m.user.bot).length,
        joinable: ch.joinable,
        channel: ch,
      })),
      { allowed: this.config.autoRecordChannels, afkChannelId: guild.afkChannelId, suppressed: this.suppressed },
    );
    if (picked) await this.#begin(picked.channel, null);
  }

  /** Show "[REC]" in the bot's nickname while recording, so nobody misses it. */
  async #markRecording(guild, isRecording) {
    const me = guild.members.me;
    if (!me) return;
    try {
      if (isRecording) {
        const current = me.nickname ?? me.user.username;
        this.originalNick.set(guild.id, me.nickname);
        if (!current.startsWith(REC_PREFIX)) await me.setNickname(`${REC_PREFIX}${current}`.slice(0, 32));
      } else {
        await me.setNickname(this.originalNick.get(guild.id) ?? null);
      }
    } catch (error) {
      console.warn('[錄音] 無法修改暱稱（需要「更改暱稱」權限）：', error.message);
    }
  }

  async stopAll(reason) {
    this.closing = true;
    for (const timer of this.scanTimers.values()) clearTimeout(timer);
    await Promise.allSettled([...this.sessions.keys()].map((id) => this.#finish(id, `⏹ ${reason}，錄音停止。`)));
  }
}
