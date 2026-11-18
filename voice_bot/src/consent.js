// Who agreed to be recorded in one session. Nobody is recorded by default.

export class ConsentBook {
  /** @type {Map<string, {status: 'agreed' | 'declined' | 'withdrawn', at: string}>} */
  #entries = new Map();

  /** Mark a person as agreeing; from now on their voice is recorded. */
  agree(userId, at = new Date()) {
    this.#entries.set(userId, { status: 'agreed', at: at.toISOString() });
  }

  /**
   * Mark a person as not agreeing (declined before, or withdrawing now).
   * Returns true when they had agreed, so the caller deletes what was recorded.
   */
  refuse(userId, at = new Date()) {
    const hadAgreed = this.isRecording(userId);
    this.#entries.set(userId, { status: hadAgreed ? 'withdrawn' : 'declined', at: at.toISOString() });
    return hadAgreed;
  }

  isRecording(userId) {
    return this.#entries.get(userId)?.status === 'agreed';
  }

  /** 'pending' = has not answered yet (and is therefore not recorded). */
  status(userId) {
    return this.#entries.get(userId)?.status ?? 'pending';
  }

  agreedUsers() {
    return [...this.#entries].filter(([, entry]) => entry.status === 'agreed').map(([id]) => id);
  }

  toJSON() {
    return Object.fromEntries(this.#entries);
  }
}
