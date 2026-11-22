// Who agreed to be recorded in one session. Nobody is recorded by default.

export class ConsentBook {
  /** @type {Map<string, {status: 'agreed' | 'included' | 'declined' | 'withdrawn', at: string}>} */
  #entries = new Map();

  /** Mark a person as agreeing; from now on their voice is recorded. */
  agree(userId, at = new Date()) {
    this.#entries.set(userId, { status: 'agreed', at: at.toISOString() });
  }

  /**
   * CONSENT_MODE=direct: someone in the channel is recorded without pressing anything ('included').
   * Only people who have not said anything yet are included, so "不要錄我" sticks even if they rejoin.
   * Returns true when they were just included.
   */
  include(userId, at = new Date()) {
    if (this.status(userId) !== 'pending') return false;
    this.#entries.set(userId, { status: 'included', at: at.toISOString() });
    return true;
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
    const status = this.#entries.get(userId)?.status;
    return status === 'agreed' || status === 'included';
  }

  /** 'pending' = has not answered and was not included (and is therefore not recorded). */
  status(userId) {
    return this.#entries.get(userId)?.status ?? 'pending';
  }

  agreedUsers() {
    return [...this.#entries].filter(([, entry]) => entry.status === 'agreed').map(([id]) => id);
  }

  /** Everyone whose voice is being recorded, whether they pressed agree or were included. */
  recordedUsers() {
    return [...this.#entries].filter(([id]) => this.isRecording(id)).map(([id]) => id);
  }

  toJSON() {
    return Object.fromEntries(this.#entries);
  }
}
