import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, stat, writeFile, mkdir } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';

import { PermissionFlagsBits } from 'discord.js';

import { isLeader, parseConsentId, parseViewId, recordCommand, viewButtons } from '../src/commands.js';
import { INVITE_PERMISSIONS, botIdFromToken, inviteUrl, loadConfig, tokenProblems } from '../src/config.js';
import { ConsentBook } from '../src/consent.js';
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
