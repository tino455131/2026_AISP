import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, stat, writeFile, mkdir } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';

import { ChannelType, PermissionFlagsBits, PermissionsBitField } from 'discord.js';

import {
  consentButtons,
  isLeader,
  parseConsentId,
  parseViewId,
  pickAutoChannel,
  recordCommand,
  viewButtons,
} from '../src/commands.js';
import {
  INVITE_PERMISSIONS,
  argsToEnv,
  botIdFromToken,
  inviteUrl,
  loadConfig,
  sttRecipient,
  summaryRecipient,
  tokenProblems,
} from '../src/config.js';
import { ConsentBook } from '../src/consent.js';
import { pickMeetingMessages, recordText, toMeetingMessage } from '../src/meetings.js';
import {
  accessTo,
  formatAnswer,
  formatTasks,
  inquiryMessage,
  meetingLabel,
  parseProgressId,
  parseTrackId,
} from '../src/ai.js';
import { parseResultLine, runIngest, runShow } from '../src/ingest.js';
import { SessionManifest, makeSessionId } from '../src/manifest.js';
import prism from 'prism-media';

import { ClipTimeline, PacketCounter, isStillEncrypted } from '../src/recorder.js';
import { monoSeconds, monoToWav, stereoToMono } from '../src/wav.js';

const LEADER = '123456789012345678';
const MEMBER = '223456789012345678';

test('nobody is recorded until they agree; withdrawing reports it', () => {
  const book = new ConsentBook();
  assert.equal(book.isRecording(MEMBER), false);
  assert.equal(book.status(MEMBER), 'pending');
  book.agree(MEMBER);
  assert.equal(book.isRecording(MEMBER), true);
  assert.equal(book.refuse(MEMBER), true); // had agreed -> caller deletes audio
  assert.equal(book.status(MEMBER), 'withdrawn');
  assert.equal(book.refuse(LEADER), false); // never agreed
  assert.equal(book.status(LEADER), 'declined');
  assert.deepEqual(book.agreedUsers(), []);
});

test('CONSENT_MODE=direct: people are included, "不要錄我" sticks even after rejoining', () => {
  const book = new ConsentBook();
  assert.equal(book.include(MEMBER), true);
  assert.equal(book.isRecording(MEMBER), true);
  assert.equal(book.status(MEMBER), 'included');
  assert.equal(book.refuse(MEMBER), true); // was recorded -> caller deletes audio
  assert.equal(book.include(MEMBER), false); // rejoining does not start recording them again
  assert.equal(book.isRecording(MEMBER), false);
  book.agree(MEMBER); // "繼續錄我"
  assert.equal(book.isRecording(MEMBER), true);
  book.include(LEADER);
  assert.deepEqual(book.recordedUsers().sort(), [LEADER, MEMBER].sort());
  assert.deepEqual(book.agreedUsers(), [MEMBER]);
});

test('CONSENT_MODE defaults to direct; only direct or ask', () => {
  const base = { VOICE_BOT_TOKEN: 'x', DISCORD_GUILD_ID: '123456789012345678' };
  assert.equal(loadConfig(base).consentMode, 'direct');
  assert.equal(loadConfig({ ...base, CONSENT_MODE: ' ASK ' }).consentMode, 'ask');
  assert.throws(() => loadConfig({ ...base, CONSENT_MODE: 'yes' }), /CONSENT_MODE/);
  const labels = (mode) => consentButtons('s', mode).components.map((b) => b.data.label);
  assert.deepEqual(labels('direct'), ['不要錄我', '繼續錄我']);
  assert.deepEqual(labels('ask'), ['同意錄音', '不同意／撤回同意']);
});

test('/meeting keeps only messages from people between the start and end, oldest first', () => {
  const msg = (id, extra = {}) => ({
    id,
    author: { id: MEMBER, bot: false, username: 'c', globalName: null },
    member: { displayName: 'C' },
    content: 'hi ' + id,
    createdAt: new Date('2026-11-21T06:00:00Z'),
    system: false,
    ...extra,
  });
  const raw = [
    msg('105'),
    msg('103'),
    msg('100'), // the start notice itself
    msg('104', { author: { id: '9', bot: true, username: 'bot' } }), // bot message
    msg('106', { content: '   ' }), // no text (e.g. only a picture)
    msg('107', { system: true }), // "pinned a message"
    msg('120'), // after the end notice
  ].map(toMeetingMessage);
  const picked = pickMeetingMessages(raw, { afterId: '100', beforeId: '110' });
  assert.deepEqual(picked.map((m) => m.message_id), ['103', '105']);
  assert.equal(picked[0].name, 'C');
  assert.equal('bot' in picked[0], false);
  // ids longer than JavaScript numbers can hold still sort correctly
  const big = pickMeetingMessages(
    [msg('900000000000000020'), msg('900000000000000010')].map(toMeetingMessage),
    { afterId: '900000000000000001', beforeId: '900000000000000099' },
  );
  assert.deepEqual(big.map((m) => m.message_id), ['900000000000000010', '900000000000000020']);
  const text = recordText({
    meeting: { startedBy: LEADER, startedAt: '2026-11-21T06:00:00Z' },
    endedAt: '2026-11-21T06:30:00Z',
    count: 2,
    markdown: '**📝 會議摘要**',
  });
  assert.match(text, /2 則發言/);
  assert.match(text, /正式任務仍要組長確認/);
});

test('startup options pick the summarizer and STT engine for one run', () => {
  assert.deepEqual(argsToEnv(['--summarizer', 'openai', '--stt=openai', '--auto-record', 'off']), {
    env: { MEETING_SUMMARIZER: 'openai', STT_ENGINE: 'openai', AUTO_RECORD: '0' },
    help: false,
  });
  assert.equal(argsToEnv(['--help']).help, true);
  assert.throws(() => argsToEnv(['--token', 'abc']), /不認得/); // secrets stay in .env
  assert.throws(() => argsToEnv(['--stt']), /後面要接一個值/);

  assert.equal(summaryRecipient('openai'), 'ChatGPT（OpenAI 的 AI）');
  assert.equal(sttRecipient('local'), null); // transcribed on this computer
  assert.equal(sttRecipient('openai'), 'OpenAI');
  assert.equal(sttRecipient('my.engine:x', 'none'), null);
  const config = loadConfig({ VOICE_BOT_TOKEN: 'x', DISCORD_GUILD_ID: '123456789012345678', STT_ENGINE: 'OpenAI' });
  assert.equal(config.sttEngine, 'openai');
  assert.equal(config.sttRecipient, 'OpenAI');
});

test('/ai checks channel access first and shows results only with real fields', () => {
  const channel = (canRead) => ({ permissionsFor: () => ({ has: () => canRead }) });
  assert.equal(accessTo({ id: MEMBER }, channel(true)), 'allow');
  assert.equal(accessTo({ id: MEMBER }, channel(false)), 'deny');
  assert.equal(accessTo(null, channel(true)), 'unknown'); // never treated as allow
  assert.equal(accessTo({ id: MEMBER }, { permissionsFor: () => null }), 'unknown');

  // A private thread: the parent's permissions are not enough (spec AC26).
  const thread = (members, flags = [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.ReadMessageHistory]) => ({
    type: ChannelType.PrivateThread,
    permissionsFor: () => new PermissionsBitField(flags),
    members: { cache: new Set(members) },
  });
  assert.equal(accessTo({ id: MEMBER }, thread([MEMBER])), 'allow');
  assert.equal(accessTo({ id: MEMBER }, thread([])), 'unknown'); // not in the cache: ask Discord, never allow
  assert.equal(accessTo({ id: MEMBER }, thread([]), false), 'deny'); // Discord said: not in the thread
  assert.equal(accessTo({ id: MEMBER }, thread([]), true), 'allow');
  const moderator = [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.ReadMessageHistory, PermissionFlagsBits.ManageThreads];
  assert.equal(accessTo({ id: MEMBER }, thread([], moderator)), 'allow'); // Manage Threads sees every thread

  const label = meetingLabel({ kind: 'voice', started_at: '2026-11-20T08:54:00Z', line_count: 25 }, '一般');
  assert.equal(label, '語音 11/20 16:54 · #一般 · 25 句'); // shown in Taiwan time
  const tasks = formatTasks(
    {
      leader_user_id: null,
      tasks: [{ title: '出小考', owner_user_id: MEMBER, due_at: '2026-11-27T15:59:00Z' }],
      proposals: [{ payload: { title: '批改', owner_user_id: null }, missing: ['owner_user_id', 'due_at'], question: '誰來改？' }],
      rejected: 1,
    },
    label,
  );
  assert.match(tasks, /沒有指定組長/);
  assert.ok(tasks.includes(`出小考 — <@${MEMBER}>，期限 <t:1795795140:f>`)); // due_at as a Discord timestamp
  assert.match(tasks, /批改 — （未指定）：看不出負責人、沒有明確期限/);
  assert.match(tasks, /要問組長：誰來改？/);
  assert.equal(formatAnswer({ ok: false, error_code: 'NOT_FOUND', message: '沒有找到符合條件的資料。' }, label), '沒有找到符合條件的資料。');
  assert.match(formatAnswer({ ok: true, answer: 'C', source_line_ids: [1, 2] }, label), /依據：第 1、2 句/);
});

test('progress tracking asks the owner with the sharing notice and four status buttons', () => {
  const dm = inquiryMessage({ task_id: 'task-ab12cd34-1', title: '寫報告', due_at: '2026-11-25T10:00:00Z' }, LEADER, '一般');
  assert.match(dm.content, /本次提交的任務進度將分享給有來源權限的組長/); // spec wording
  const ids = dm.components[0].components.map((b) => b.data.custom_id);
  assert.deepEqual(ids.map((id) => parseProgressId(id).status), ['not_started', 'in_progress', 'blocked', 'completed']);
  assert.equal(parseProgressId('progress:task-ab12cd34-1:cancelled'), null); // only the leader may cancel
  assert.equal(parseTrackId('track:ab12cd34'), 'ab12cd34');
  assert.equal(parseTrackId('track:../../x'), null);

  const mentioned = toMeetingMessage({
    id: '10',
    author: { id: LEADER, bot: false, username: 'a' },
    member: { displayName: 'A' },
    content: '<@' + MEMBER + '> 負責寫報告',
    createdAt: new Date('2026-11-21T06:00:00Z'),
    mentions: { users: new Map([[MEMBER, { id: MEMBER, username: 'c' }]]), members: new Map([[MEMBER, { displayName: 'C' }]]) },
  });
  assert.deepEqual(mentioned.mentions, [{ id: MEMBER, name: 'C' }]);
});

test('stereo PCM becomes a valid mono WAV', () => {
  const stereo = Buffer.alloc(8);
  stereo.writeInt16LE(1000, 0);
  stereo.writeInt16LE(3000, 2);
  stereo.writeInt16LE(-2000, 4);
  stereo.writeInt16LE(-4000, 6);
  const mono = stereoToMono(stereo);
  assert.deepEqual([mono.readInt16LE(0), mono.readInt16LE(2)], [2000, -3000]);

  const wav = monoToWav(mono);
  assert.equal(wav.toString('ascii', 0, 4), 'RIFF');
  assert.equal(wav.toString('ascii', 8, 12), 'WAVE');
  assert.equal(wav.readUInt32LE(24), 48000);
  assert.equal(wav.readUInt32LE(40), mono.length);
  assert.equal(monoSeconds(Buffer.alloc(96000)), 1);
});

test('session ids follow the voice_stt pattern', () => {
  assert.equal(makeSessionId('301', new Date(2026, 10, 18, 14, 5, 9)), 'rec-301-20261118-140509');
});

test('manifest keeps ids as strings and forgets a withdrawn person', async () => {
  const dir = await mkdtemp(path.join(os.tmpdir(), 'voicebot-'));
  try {
    const manifest = new SessionManifest({
      sessionId: 'rec-301-x',
      guildId: '10',
      channelId: '301',
      startedBy: LEADER,
      startedAt: new Date('2026-11-18T06:00:00Z'),
      dir,
    });
    const consent = new ConsentBook();
    consent.agree(LEADER);
    consent.agree(MEMBER);
    manifest.names[MEMBER] = '小明';
    manifest.addClip({ userId: MEMBER, offsetMs: 4500, duration: 1.2345 });
    manifest.addClip({ userId: LEADER, offsetMs: 1000, duration: 2 });
    await mkdir(path.join(dir, MEMBER), { recursive: true });
    await writeFile(path.join(dir, MEMBER, '4500.wav'), 'x');
    await manifest.save(consent);

    let saved = JSON.parse(await readFile(manifest.path, 'utf8'));
    assert.equal(saved.started_by, LEADER); // not rounded like a JS number would be
    assert.deepEqual(saved.clips.map((c) => c.offset), [1, 4.5]); // sorted by time
    assert.equal(saved.clips[1].file, `${MEMBER}/4500.wav`);
    assert.equal(saved.names[MEMBER], '小明');

    consent.refuse(MEMBER);
    assert.equal(await manifest.removeUser(MEMBER), 1);
    await manifest.save(consent);
    saved = JSON.parse(await readFile(manifest.path, 'utf8'));
    assert.deepEqual(saved.clips.map((c) => c.user_id), [LEADER]);
    assert.equal(saved.names[MEMBER], undefined);
    assert.equal(saved.consent[MEMBER].status, 'withdrawn');
    await assert.rejects(stat(path.join(dir, MEMBER))); // audio folder deleted
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('config needs a token and a numeric server id', () => {
  assert.throws(() => loadConfig({}), /VOICE_BOT_TOKEN/);
  assert.throws(() => loadConfig({ VOICE_BOT_TOKEN: 'abc', DISCORD_GUILD_ID: 'my server' }), /DISCORD_GUILD_ID/);
  const config = loadConfig({ VOICE_BOT_TOKEN: 'abc', DISCORD_GUILD_ID: '123456789012345678' });
  assert.equal(config.leaderRoleId, null);
  assert.equal(config.silenceMs, 800);
  assert.match(config.botDb, /[\\/]data[\\/]messages\.sqlite3$/);
  assert.equal(config.keepAudio, false);
  assert.equal(config.summarizer, 'simple');
  const base = { VOICE_BOT_TOKEN: 'abc', DISCORD_GUILD_ID: '123456789012345678' };
  assert.equal(loadConfig({ ...base, MEETING_SUMMARIZER: ' Claude-Code ' }).summarizer, 'claude-code');
  assert.equal(summaryRecipient('claude-code'), 'Claude（Anthropic 的 AI）');
  assert.equal(summaryRecipient('claude'), 'Claude（Anthropic 的 AI）');
  assert.equal(summaryRecipient('simple'), null);
  assert.equal(summaryRecipient('my_pkg.openai_one:mysummarizer'), '外部的 AI 服務');
  assert.equal(summaryRecipient('my_pkg.openai_one:mysummarizer', 'OpenAI 的 GPT'), 'OpenAI 的 GPT');
  assert.equal(summaryRecipient('my_pkg.local:llama', 'none'), null); // a model on this computer
  assert.equal(loadConfig({ ...base, MEETING_SUMMARIZER: 'claude' }).summaryRecipient, 'Claude（Anthropic 的 AI）');
  assert.throws(() => loadConfig({ TEXT_BOT_TOKEN: 'text-only', DISCORD_GUILD_ID: '123456789012345678' }), /VOICE_BOT_TOKEN/);
  const executable = process.platform === 'win32' ? ['Scripts', 'python.exe'] : ['bin', 'python'];
  assert.equal(config.sttDir, path.join(config.repoRoot, 'voice_bot', 'voice_stt'));
  assert.equal(config.python, path.join(config.sttDir, '.venv', ...executable));
  assert.equal(config.readerPython, path.join(config.repoRoot, 'text_bot', '.venv', ...executable));
  const overridden = loadConfig({
    VOICE_BOT_TOKEN: 'voice-token', TEXT_BOT_TOKEN: 'text-token',
    DISCORD_GUILD_ID: '123456789012345678', BOT_DB: 'archive/shared.sqlite3',
  });
  assert.equal(overridden.token, 'voice-token');
  assert.equal(overridden.botDb, path.join(overridden.repoRoot, 'archive', 'shared.sqlite3'));
  assert.equal(loadConfig({ VOICE_BOT_TOKEN: 'abc', DISCORD_GUILD_ID: '123456789012345678', KEEP_AUDIO: '1' }).keepAudio, true);
});

test('packet loss is estimated from arrival times; pauses are not loss', () => {
  const feed = (times) => {
    const counter = new PacketCounter();
    times.forEach((t) => counter.add(t));
    return counter.lost;
  };
  const steady = Array.from({ length: 50 }, (_, i) => i * 20);
  assert.equal(feed(steady), 0);
  // Late packets arriving in bursts are not loss: 0, 40, 40, 80, 80, ...
  const bursty = Array.from({ length: 50 }, (_, i) => Math.ceil(i / 2) * 40);
  assert.ok(feed(bursty) < 0.05);
  // Every other packet missing.
  const half = Array.from({ length: 50 }, (_, i) => i * 40);
  assert.ok(Math.abs(feed(half) - 0.5) < 0.02);
  // A one-second pause in the middle of a clip is the speaker pausing.
  const paused = [...steady, ...steady.map((t) => t + 2000)];
  assert.equal(feed(paused), 0);
});

test('pauses and holes are filled with silence so a clip keeps real time', async () => {
  const fills = (times) => {
    const timeline = new ClipTimeline();
    return times.map((t) => timeline.silenceBefore(t));
  };
  // Steady 20 ms packets: nothing to fill.
  assert.deepEqual(fills([0, 20, 40, 60]), [0, 0, 0, 0]);
  // A 300 ms pause in Discord's packets: 15 frames of silence put it back.
  assert.deepEqual(fills([0, 20, 340, 360]), [0, 0, 15, 0]);
  // A packet 40 ms late, then a burst: jitter, not a pause.
  assert.deepEqual(fills([0, 20, 40, 100, 100, 120]), [0, 0, 0, 0, 0, 0]);

  // The silence packet really decodes to 20 ms (960 samples, stereo, 16-bit).
  const decoder = new prism.opus.Decoder({ rate: 48000, channels: 2, frameSize: 960 });
  const pcm = await new Promise((resolve, reject) => {
    decoder.once('data', resolve);
    decoder.once('error', reject);
    decoder.write(Buffer.from([0xf8, 0xff, 0xfe]));
  });
  assert.equal(pcm.length, 960 * 2 * 2);
  assert.ok(pcm.every((byte) => byte === 0));
});

test('still-encrypted DAVE frames are recognized by their FA FA ending', () => {
  assert.equal(isStillEncrypted(Buffer.from([0x78, 0x01, 0x02, 0x08, 0xfa, 0xfa])), true);
  assert.equal(isStillEncrypted(Buffer.from([0x78, 0x01, 0x02, 0x03])), false);
  assert.equal(isStillEncrypted(Buffer.from([0xf8, 0xff, 0xfe])), false); // Discord's silence frame
  assert.equal(isStillEncrypted(Buffer.from([0xfa, 0xfa])), false); // too short to be a frame
});

test('the token check finds paste mistakes without needing the real token', () => {
  // Shaped like a bot token but made up: base64 of an id, then two dummy parts.
  const fake = `${Buffer.from(LEADER).toString('base64').replace(/=+$/, '')}.AAAAAA.${'x'.repeat(27)}`;
  assert.equal(botIdFromToken(fake), LEADER);
  assert.deepEqual(tokenProblems(fake), []);
  assert.match(tokenProblems(`Bot ${fake}`).join(), /Bot/);
  assert.match(tokenProblems(`${fake.slice(0, 10)} ${fake.slice(10)}`).join(), /空白/);
  assert.match(tokenProblems(`"${fake}"`).join(), /引號/);
  assert.match(tokenProblems('your-client-secret').join(), /格式/);

  const permissions =
    PermissionFlagsBits.ViewChannel |
    PermissionFlagsBits.SendMessages |
    PermissionFlagsBits.AttachFiles |
    PermissionFlagsBits.ReadMessageHistory |
    PermissionFlagsBits.Connect |
    PermissionFlagsBits.ChangeNickname;
  assert.equal(INVITE_PERMISSIONS, String(permissions));
  const url = new URL(inviteUrl(LEADER, MEMBER));
  assert.equal(url.searchParams.get('client_id'), LEADER);
  assert.equal(url.searchParams.get('scope'), 'bot applications.commands');
  assert.equal(url.searchParams.get('guild_id'), MEMBER);
});

test('only leaders may start or stop', () => {
  const member = (roles, canManage) => ({
    roles: { cache: new Set(roles) },
    permissions: { has: (flag) => canManage && flag === PermissionFlagsBits.ManageGuild },
  });
  assert.equal(isLeader(member(['999'], false), '999'), true);
  assert.equal(isLeader(member([], true), '999'), false); // role set: managers need the role too
  assert.equal(isLeader(member([], true), null), true);
  assert.equal(isLeader(member([], false), null), false);
});

test('consent button ids and the slash command shape', () => {
  assert.deepEqual(parseConsentId('consent:agree:rec-1'), { action: 'agree', sessionId: 'rec-1' });
  assert.equal(parseConsentId('other:thing'), null);
  const json = recordCommand.toJSON();
  assert.equal(json.name, 'record');
  assert.deepEqual(json.options.map((o) => o.name), ['start', 'stop', 'status']);
});

test('automatic recording picks the busiest allowed voice channel', () => {
  const channels = [
    { id: '1', humans: 0, joinable: true }, // empty
    { id: '2', humans: 1, joinable: true },
    { id: '3', humans: 3, joinable: true },
    { id: '4', humans: 5, joinable: false }, // bot may not join
    { id: '9', humans: 6, joinable: true }, // AFK channel
  ];
  const pick = (options) => pickAutoChannel(channels, { afkChannelId: '9', ...options })?.id ?? null;
  assert.equal(pick({}), '3');
  assert.equal(pick({ suppressed: new Set(['3']) }), '2'); // a leader stopped it by hand
  assert.equal(pick({ allowed: ['1', '2'] }), '2'); // AUTO_RECORD_CHANNELS
  assert.equal(pick({ allowed: ['1'] }), null); // allowed channel is empty: nothing to record
  assert.equal(pickAutoChannel([], {}), null);
});

test('AUTO_RECORD is on unless turned off; AUTO_RECORD_CHANNELS takes channel ids', () => {
  const base = { VOICE_BOT_TOKEN: 'abc', DISCORD_GUILD_ID: '123456789012345678' };
  assert.equal(loadConfig(base).autoRecord, true);
  assert.equal(loadConfig(base).autoRecordChannels, null);
  assert.equal(loadConfig({ ...base, AUTO_RECORD: '0' }).autoRecord, false);
  assert.deepEqual(loadConfig({ ...base, AUTO_RECORD_CHANNELS: ' 111111, 222222 ' }).autoRecordChannels, ['111111', '222222']);
  assert.throws(() => loadConfig({ ...base, AUTO_RECORD_CHANNELS: 'general' }), /AUTO_RECORD_CHANNELS/);
});

test('view buttons: summary and transcript, or transcript only when there is no summary', () => {
  assert.deepEqual(parseViewId('view:summary:rec-1'), { what: 'summary', sessionId: 'rec-1' });
  assert.deepEqual(parseViewId('view:transcript:rec-1'), { what: 'transcript', sessionId: 'rec-1' });
  assert.equal(parseViewId('view:audio:rec-1'), null);
  assert.equal(parseViewId('consent:agree:rec-1'), null);
  const ids = (row) => row.toJSON().components.map((b) => b.custom_id);
  assert.deepEqual(ids(viewButtons('rec-1')), ['view:summary:rec-1', 'view:transcript:rec-1']);
  assert.deepEqual(ids(viewButtons('rec-1', { summary: false })), ['view:transcript:rec-1']);
  // Discord limits a custom id to 100 characters; real session ids are about 40.
  assert.ok(`view:transcript:${makeSessionId('1234567890123456789', new Date())}`.length <= 100);
});

test('python results are read from the RESULT line', async () => {
  assert.deepEqual(parseResultLine('loading...\nRESULT {"saved_lines": 3}\n'), { saved_lines: 3 });
  assert.equal(parseResultLine('no result'), null);
  await assert.rejects(
    runIngest({ python: 'no-such-python-xyz', sttDir: '.', sessionDir: '.', botDb: 'x' }),
    /無法啟動 Python/,
  );
  await assert.rejects(
    runShow({ python: 'no-such-python-xyz', repoRoot: '.', botDb: 'x', token: 't', sessionId: 's', memberId: '1', guildId: '2', what: 'summary' }),
    /無法啟動 Python/,
  );
});
