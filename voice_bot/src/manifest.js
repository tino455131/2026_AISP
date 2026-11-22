// manifest.json: what voice_stt needs to turn one recording folder into a transcript.
//
// recordings/<session_id>/
//   manifest.json
//   <user id>/<ms after start>.wav   one file per thing a person said
import { mkdir, rename, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';

/** rec-<channel>-<local time>, the same pattern voice_stt uses. */
export function makeSessionId(channelId, date = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  const stamp =
    `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-` +
    `${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
  return `rec-${channelId}-${stamp}`;
}

export class SessionManifest {
  constructor({ sessionId, guildId, channelId, startedBy, startedAt, dir }) {
    this.sessionId = sessionId;
    this.guildId = guildId;
    this.channelId = channelId;
    this.startedBy = startedBy;
    this.startedAt = startedAt; // Date
    this.endedAt = null;
    this.dir = dir;
    /** @type {{user_id: string, file: string, offset: number, duration: number}[]} */
    this.clips = [];
    /** @type {Record<string, string>} user id -> display name, for the summary only */
    this.names = {};
    /** Audio-quality counters for diagnosing bad transcripts (see recorder.js). */
    this.diagnostics = { decrypt_failures: 0, undecrypted_packets: 0 };
    this.#saving = Promise.resolve();
  }

  #saving;

  get path() {
    return path.join(this.dir, 'manifest.json');
  }

  /** `lost` is the estimated share of this clip's sound that never arrived (0-1), for diagnosing audio quality. */
  addClip({ userId, offsetMs, duration, lost = 0, undecrypted = 0 }) {
    const file = `${userId}/${offsetMs}.wav`;
    this.clips.push({
      user_id: userId,
      file,
      offset: offsetMs / 1000,
      duration: Math.round(duration * 1000) / 1000,
      lost: Math.round(lost * 100) / 100,
      undecrypted,
    });
    return file;
  }

  /** Forget one person's clips (consent withdrawn) and delete their audio files. */
  async removeUser(userId) {
    const removed = this.clips.filter((clip) => clip.user_id === userId);
    this.clips = this.clips.filter((clip) => clip.user_id !== userId);
    delete this.names[userId];
    await rm(path.join(this.dir, userId), { recursive: true, force: true });
    return removed.length;
  }

  toJSON(consent) {
    return {
      session_id: this.sessionId,
      guild_id: this.guildId,
      channel_id: this.channelId,
      started_by: this.startedBy,
      started_at: this.startedAt.toISOString(),
      ended_at: this.endedAt ? this.endedAt.toISOString() : null,
      consent: consent.toJSON(),
      names: this.names,
      clips: [...this.clips].sort((a, b) => a.offset - b.offset),
      diagnostics: this.diagnostics,
    };
  }

  /** Write manifest.json; saves run one at a time and replace the file atomically. */
  save(consent) {
    const text = JSON.stringify(this.toJSON(consent), null, 2);
    this.#saving = this.#saving.then(async () => {
      await mkdir(this.dir, { recursive: true });
      const temp = `${this.path}.tmp`;
      await writeFile(temp, text, 'utf8');
      await rename(temp, this.path);
    });
    return this.#saving;
  }
}
