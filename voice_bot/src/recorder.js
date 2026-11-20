// One recording in one voice channel: joins, records only consenting people
// (one clip per thing they say), and writes the folder voice_stt reads.
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { Transform } from 'node:stream';

import { EndBehaviorType, VoiceConnectionStatus, entersState, joinVoiceChannel } from '@discordjs/voice';
import prism from 'prism-media';

import { ConsentBook } from './consent.js';
import { SessionManifest, makeSessionId } from './manifest.js';
import { monoSeconds, monoToWav, stereoToMono } from './wav.js';

const MIN_CLIP_SECONDS = 0.3; // shorter than this is a cough or a click
const MAX_CLIP_BYTES = 48000 * 4 * 600; // 10 minutes of stereo PCM; longer talk is cut
const FRAME_MS = 20; // Discord sends one Opus packet per 20 ms of sound
const PAUSE_MS = 200; // a longer gap between packets is the speaker pausing, not loss
const WARN_LOSS = 0.1;

/**
 * Estimates how much of a clip's sound never arrived. The stream carries no sequence
 * numbers, so it counts packets against the time they kept coming. Short gaps add up
 * to the expected count (arrival jitter cancels out); long gaps are pauses.
 */
export class PacketCounter {
  received = 0;
  expected = 0;
  #lastMs = null;

  add(nowMs) {
    this.received += 1;
    if (this.#lastMs === null) {
      this.expected = 1;
    } else {
      const gap = nowMs - this.#lastMs;
      this.expected += gap < PAUSE_MS ? gap / FRAME_MS : 1;
    }
    this.#lastMs = nowMs;
  }

  get lost() {
    return this.expected > 0 ? Math.max(0, 1 - this.received / this.expected) : 0;
  }
}

const SILENCE_FRAME = Buffer.from([0xf8, 0xff, 0xfe]); // one Opus packet = 20 ms of silence
const ALIGN_SLACK_MS = 60; // ignore smaller delays: that is network jitter

/**
 * Keeps a clip in step with the clock. Discord sends nothing during short pauses, and lost
 * packets leave holes; without filling them the clip gets shorter than the real talk, and
 * later sentences get times that are too early (so two people's lines come out in the
 * wrong order).
 */
export class ClipTimeline {
  #startMs = null;
  #frames = 0;

  /** How many 20 ms silence frames to put before the packet that arrived at `nowMs`. */
  silenceBefore(nowMs) {
    if (this.#startMs === null) {
      this.#startMs = nowMs;
      this.#frames = 1;
      return 0;
    }
    const behindMs = nowMs - (this.#startMs + this.#frames * FRAME_MS);
    const fill = behindMs > ALIGN_SLACK_MS ? Math.round(behindMs / FRAME_MS) : 0;
    this.#frames += fill + 1;
    return fill;
  }
}

/**
 * True if a packet is still end-to-end (DAVE) encrypted: such frames end with the marker
 * bytes FA FA. @discordjs/voice passes packets through untouched while its DAVE session
 * is not ready; decoding one as sound gives noise, which the speech model turns into
 * made-up sentences.
 */
export function isStillEncrypted(packet) {
  const n = packet.length;
  return n > 2 && packet[n - 1] === 0xfa && packet[n - 2] === 0xfa;
}

export class RecordingSession {
  /**
   * @param {object} options
   * @param {import('discord.js').VoiceBasedChannel} options.channel
   * @param {string} options.startedBy user id of the leader who started it
   * @param {{recordingsDir: string, silenceMs: number}} options.config
   * @param {(reason: string) => void} [options.onLost] called if Discord drops the connection
   */
  constructor({ channel, startedBy, config, onLost }) {
    this.channel = channel;
    this.config = config;
    this.onLost = onLost;
    this.startedAt = new Date();
    this.sessionId = makeSessionId(channel.id, this.startedAt);
    this.dir = path.join(config.recordingsDir, this.sessionId);
    this.consent = new ConsentBook();
    this.manifest = new SessionManifest({
      sessionId: this.sessionId,
      guildId: channel.guild.id,
      channelId: channel.id,
      startedBy,
      startedAt: this.startedAt,
      dir: this.dir,
    });
    this.connection = null;
    this.stopping = false;
    /** @type {Map<string, {stream: import('stream').Readable}>} user id -> clip being recorded */
    this.active = new Map();
    /** @type {Set<Promise<void>>} clips still being written to disk */
    this.pending = new Set();
  }

  async start() {
    await mkdir(this.dir, { recursive: true });
    await this.manifest.save(this.consent);

    this.connection = joinVoiceChannel({
      channelId: this.channel.id,
      guildId: this.channel.guild.id,
      adapterCreator: this.channel.guild.voiceAdapterCreator,
      selfDeaf: false, // must hear to record
      selfMute: true, // the bot never talks
      debug: true, // needed to see DAVE decryption failures (handled in #onDebug)
    });
    this.connection.on('debug', (message) => this.#onDebug(message));
    try {
      await entersState(this.connection, VoiceConnectionStatus.Ready, 20_000);
    } catch (error) {
      this.connection.destroy();
      throw new Error(`連不上語音頻道（20 秒逾時）：${error.message}`);
    }

    this.connection.receiver.speaking.on('start', (userId) => this.#onSpeakingStart(userId));
    this.connection.on(VoiceConnectionStatus.Disconnected, async () => {
      try {
        // Moving between channels or a short network blip: Discord reconnects by itself.
        await Promise.race([
          entersState(this.connection, VoiceConnectionStatus.Signalling, 5_000),
          entersState(this.connection, VoiceConnectionStatus.Connecting, 5_000),
        ]);
      } catch {
        if (!this.stopping) this.onLost?.('和 Discord 的語音連線中斷');
      }
    });
  }

  /** Only end-to-end encryption messages matter here; the rest is connection chatter. */
  #onDebug(message) {
    if (!message.includes('[DAVE]')) return;
    if (message.includes('Failed to decrypt')) {
      // The library drops these packets silently; count them instead of printing each one.
      this.manifest.diagnostics.decrypt_failures += 1;
      return;
    }
    console.log(`[加密] ${message}`);
  }

  /** A consenting person started talking: record until they are silent for a moment. */
  #onSpeakingStart(userId) {
    if (this.stopping || !this.consent.isRecording(userId) || this.active.has(userId)) return;

    const startedAtMs = Date.now();
    const stream = this.connection.receiver.subscribe(userId, {
      end: { behavior: EndBehaviorType.AfterSilence, duration: this.config.silenceMs },
    });
    const decoder = new prism.opus.Decoder({ rate: 48000, channels: 2, frameSize: 960 });
    const chunks = [];
    let bytes = 0;
    const counter = new PacketCounter();
    const timeline = new ClipTimeline();
    let undecrypted = 0;
    const diagnostics = this.manifest.diagnostics;
    // Between the receiver and the decoder: count packets, drop ones that are still
    // encrypted, and fill pauses and holes with silence so the clip keeps real time.
    const filter = new Transform({
      transform(packet, _encoding, done) {
        const now = Date.now();
        counter.add(now);
        if (isStillEncrypted(packet)) {
          undecrypted += 1;
          diagnostics.undecrypted_packets += 1;
          done();
          return;
        }
        for (let i = timeline.silenceBefore(now); i > 0; i--) this.push(SILENCE_FRAME);
        done(null, packet);
      },
    });

    this.active.set(userId, { stream });
    const finished = new Promise((resolve) => {
      decoder.on('data', (chunk) => {
        if (bytes < MAX_CLIP_BYTES) {
          chunks.push(chunk);
          bytes += chunk.length;
        }
      });
      decoder.once('end', resolve);
      decoder.once('error', (error) => {
        console.warn(`[錄音] 解碼 ${userId} 的聲音失敗：${error.message}`);
        resolve();
      });
      stream.once('error', (error) => {
        console.warn(`[錄音] 接收 ${userId} 的聲音失敗：${error.message}`);
        filter.end();
      });
    });
    stream.pipe(filter).pipe(decoder);

    const write = finished
      .then(() => {
        this.active.delete(userId);
        return this.#saveClip(userId, startedAtMs, Buffer.concat(chunks), counter.lost, undecrypted);
      })
      .catch((error) => console.error(`[錄音] 存檔失敗（${userId}）：`, error))
      .finally(() => this.pending.delete(write));
    this.pending.add(write);
  }

  async #saveClip(userId, startedAtMs, stereo, lost, undecrypted) {
    if (!this.consent.isRecording(userId)) return; // withdrew while talking: keep nothing
    const mono = stereoToMono(stereo);
    const seconds = monoSeconds(mono);
    if (seconds < MIN_CLIP_SECONDS) return;

    const offsetMs = startedAtMs - this.startedAt.getTime();
    const who = this.manifest.names[userId] ?? userId;
    if (lost > WARN_LOSS) {
      console.warn(`[錄音] ${who} 的一段話（${seconds.toFixed(1)} 秒）大約掉了 ${Math.round(lost * 100)}% 的聲音`);
    }
    if (undecrypted > 0) {
      console.warn(`[錄音] ${who} 的一段話有 ${undecrypted} 個封包沒解密就送來，已丟掉（不然會變雜音）`);
    }
    const file = this.manifest.addClip({ userId, offsetMs, duration: seconds, lost, undecrypted });
    await mkdir(path.join(this.dir, userId), { recursive: true });
    await writeFile(path.join(this.dir, file), monoToWav(mono));
    await this.manifest.save(this.consent);
  }

  agree(userId, displayName) {
    this.consent.agree(userId);
    if (displayName) this.manifest.names[userId] = displayName;
    return this.manifest.save(this.consent);
  }

  /** CONSENT_MODE=direct: record this person from now on unless they already said no. */
  async include(userId, displayName) {
    if (!this.consent.include(userId)) return false;
    if (displayName) this.manifest.names[userId] = displayName;
    await this.manifest.save(this.consent);
    return true;
  }

  /** Decline or withdraw. If they had agreed, delete everything recorded of them. */
  async refuse(userId) {
    const hadAgreed = this.consent.refuse(userId);
    if (hadAgreed) {
      this.active.get(userId)?.stream.push(null); // end the clip in progress
      await Promise.allSettled([...this.pending]);
      await this.manifest.removeUser(userId);
    }
    delete this.manifest.names[userId];
    await this.manifest.save(this.consent);
    return hadAgreed;
  }

  /** Stop recording, finish writing clips, leave the channel. Returns the clip count. */
  async stop() {
    if (this.stopping) return this.manifest.clips.length;
    this.stopping = true;
    for (const { stream } of this.active.values()) stream.push(null);
    await Promise.allSettled([...this.pending]);
    this.connection?.destroy();
    const { decrypt_failures: failures, undecrypted_packets: undecrypted } = this.manifest.diagnostics;
    if (failures > 0 || undecrypted > 0) {
      console.warn(`[錄音] 這次有 ${failures} 個封包解密失敗（被丟掉）、${undecrypted} 個封包沒解密（已丟掉）`);
    }
    this.manifest.endedAt = new Date();
    await this.manifest.save(this.consent);
    return this.manifest.clips.length;
  }

  humansInChannel() {
    return [...this.channel.members.values()].filter((member) => !member.user.bot);
  }
}
