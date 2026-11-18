// /record start | stop | status, the consent buttons, and what happens after stop.
import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  MessageFlags,
  PermissionFlagsBits,
  SlashCommandBuilder,
} from 'discord.js';

import { fitDiscord, runIngest, runSummary } from './ingest.js';
import { RecordingSession } from './recorder.js';

export const recordCommand = new SlashCommandBuilder()
  .setName('record')
  .setDescription('會議錄音：只錄有按「同意」的人，結束後轉成逐字稿')
  .addSubcommand((sub) => sub.setName('start').setDescription('在你所在的語音頻道開始錄音（組長）'))
  .addSubcommand((sub) => sub.setName('stop').setDescription('停止錄音並轉成逐字稿（組長）'))
  .addSubcommand((sub) => sub.setName('status').setDescription('查看目前的錄音狀態'));

const REC_PREFIX = '[REC] ';
const ephemeral = { flags: MessageFlags.Ephemeral };

/** Who may start or stop a recording: the leader role, or server managers if none is set. */
export function isLeader(member, leaderRoleId) {
  if (leaderRoleId) return member.roles.cache.has(leaderRoleId);
  return member.permissions.has(PermissionFlagsBits.ManageGuild);
}

/** custom id of a consent button: consent:<agree|refuse>:<session id> */
export function parseConsentId(customId) {
  const match = /^consent:(agree|refuse):(.+)$/.exec(customId);
  return match ? { action: match[1], sessionId: match[2] } : null;
}

function consentButtons(sessionId) {
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
  }

  async handle(interaction) {
    if (interaction.isChatInputCommand() && interaction.commandName === 'record') {
      const sub = interaction.options.getSubcommand();
      if (sub === 'start') return this.#start(interaction);
      if (sub === 'stop') return this.#stop(interaction);
      if (sub === 'status') return this.#status(interaction);
    }
    if (interaction.isButton()) {
      const parsed = parseConsentId(interaction.customId);
      if (parsed) return this.#consent(interaction, parsed);
    }
  }

  async #start(interaction) {
    const member = interaction.member;
    const channel = member?.voice?.channel;
    if (!channel) return interaction.reply({ content: '請先進入要錄音的語音頻道，再下這個指令。', ...ephemeral });
    if (!isLeader(member, this.config.leaderRoleId)) {
      return interaction.reply({ content: '只有組長可以開始錄音。', ...ephemeral });
    }
    if (this.sessions.has(interaction.guildId)) {
      return interaction.reply({ content: '這個伺服器已經在錄音了，請先 /record stop。', ...ephemeral });
    }

    await interaction.deferReply(ephemeral); // joining can take longer than Discord's 3 seconds
    const session = new RecordingSession({
      channel,
      startedBy: member.id,
      config: this.config,
      onLost: (reason) => this.#finish(interaction.guildId, `⚠️ ${reason}，錄音已自動停止。`),
    });
    try {
      await session.start();
    } catch (error) {
      return interaction.editReply(`開始錄音失敗：${error.message}`);
    }
    this.sessions.set(interaction.guildId, session);
    this.reminded.set(session.sessionId, new Set());
    await this.#markRecording(channel.guild, true);

    const people = session.humansInChannel().map((m) => `<@${m.id}>`).join(' ');
    await channel.send({
      content: [
        `🔴 **錄音中**：<@${member.id}> 開始了會議錄音。${people}`,
        '- **只會錄有按「同意錄音」的人**；沒按或按不同意的人，聲音不會被保存。',
        '- 錄音結束後會轉成文字存進 bot 的資料庫，之後只有看得到這個語音頻道的人能透過 bot 讀到。',
        '- 隨時可以按「不同意／撤回同意」，你這次已錄的部分會被刪除。',
      ].join('\n'),
      components: [consentButtons(session.sessionId)],
    });
    return interaction.editReply(`已開始錄音（${session.sessionId}）。結束時請用 /record stop。`);
  }

  async #consent(interaction, { action, sessionId }) {
    const session = this.sessions.get(interaction.guildId);
    if (!session || session.sessionId !== sessionId || session.stopping) {
      return interaction.reply({ content: '這次錄音已經結束了。', ...ephemeral });
    }
    if (interaction.user.bot) return;
    await interaction.deferReply(ephemeral);
    if (action === 'agree') {
      await session.agree(interaction.user.id, interaction.member?.displayName ?? interaction.user.username);
      return interaction.editReply('✅ 已同意。接下來你在這個語音頻道的發言會被錄下；隨時可以撤回。');
    }
    const hadAgreed = await session.refuse(interaction.user.id);
    return interaction.editReply(
      hadAgreed ? '已撤回同意，並刪除你這次已錄下的聲音。之後不會再錄你。' : '好的，這次不會錄你的聲音。',
    );
  }

  async #stop(interaction) {
    if (!isLeader(interaction.member, this.config.leaderRoleId)) {
      return interaction.reply({ content: '只有組長可以停止錄音。', ...ephemeral });
    }
    if (!this.sessions.has(interaction.guildId)) {
      return interaction.reply({ content: '目前沒有在錄音。', ...ephemeral });
    }
    await interaction.deferReply(ephemeral);
    await this.#finish(interaction.guildId, `⏹ <@${interaction.user.id}> 停止了錄音。`);
    return interaction.editReply('已停止錄音，正在轉成文字，完成後會在語音頻道的聊天室通知。');
  }

  async #status(interaction) {
    const session = this.sessions.get(interaction.guildId);
    if (!session) return interaction.reply({ content: '目前沒有在錄音。', ...ephemeral });
    const minutes = Math.floor((Date.now() - session.startedAt.getTime()) / 60000);
    const agreed = session.consent.agreedUsers().map((id) => `<@${id}>`).join('、') || '（還沒有人同意）';
    return interaction.reply({
      content: `🔴 錄音中：<#${session.channel.id}>，已 ${minutes} 分鐘，${session.manifest.clips.length} 段發言。\n同意錄音的人：${agreed}`,
      ...ephemeral,
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

    const say = (text) => session.channel.send(text).catch((e) => console.warn('[錄音] 無法發訊息：', e.message));
    if (clips === 0) {
      await say(`${notice}\n沒有錄到任何同意者的發言，不會產生逐字稿。`);
      return;
    }
    await say(`${notice}\n共 ${clips} 段發言，正在轉成文字…`);
    const { python, sttDir, repoRoot, botDb, keepAudio } = this.config;
    let ingested;
    try {
      ingested = await runIngest({ python, sttDir, sessionDir: session.dir, botDb, keepAudio });
      const audioNote = keepAudio ? '錄音檔保留在主機上（測試模式 KEEP_AUDIO）。' : '錄音檔已刪除。';
      await say(`✅ 逐字稿已存入（${ingested.saved_lines} 句，編號 \`${ingested.session_id}\`）。${audioNote}`);
    } catch (error) {
      console.error('[錄音] 轉文字失敗：', error);
      await say(`⚠️ 轉文字失敗：${error.message}\n錄音檔保留在主機上（${session.sessionId}），可以修好後再處理。`);
      return;
    }
    if (ingested.saved_lines === 0) return;

    // Step 2: summary through the swappable meeting_ai interface. The channel it is
    // posted in is the voice channel itself, so readers are the same as the transcript's.
    try {
      const summary = await runSummary({ python, repoRoot, sessionId: ingested.session_id, sessionDir: session.dir, botDb });
      await session.channel.send({
        content: fitDiscord(`${summary.markdown}\n-# 摘要器：${summary.summarizer}`),
        allowedMentions: { parse: [] }, // show names without pinging everyone
      });
    } catch (error) {
      console.error('[錄音] 摘要失敗：', error);
      await say(`⚠️ 逐字稿已存好，但摘要失敗：${error.message}`);
    }
  }

  /** Remind people who join during a recording; stop when everyone has left. */
  async onVoiceState(oldState, newState) {
    const session = this.sessions.get(newState.guild.id);
    if (!session || session.stopping) return;
    const channelId = session.channel.id;
    const user = newState.member?.user;

    if (newState.channelId === channelId && oldState.channelId !== channelId && user && !user.bot) {
      const reminded = this.reminded.get(session.sessionId);
      if (session.consent.status(user.id) === 'pending' && !reminded.has(user.id)) {
        reminded.add(user.id);
        await session.channel
          .send(`<@${user.id}> 這裡正在錄音，請在上方訊息按「同意錄音」或「不同意」；沒按就不會錄你。`)
          .catch(() => {});
      }
    }
    if (oldState.channelId === channelId && session.humansInChannel().length === 0) {
      await this.#finish(newState.guild.id, '⏹ 大家都離開了，錄音自動停止。');
    }
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
    await Promise.allSettled([...this.sessions.keys()].map((id) => this.#finish(id, `⏹ ${reason}，錄音停止。`)));
  }
}
