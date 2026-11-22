// Turn the decoded Discord audio (48 kHz, 16-bit, stereo PCM) into WAV files.

export const SAMPLE_RATE = 48000;
const BYTES_PER_MONO_SECOND = SAMPLE_RATE * 2;

/** Average the left and right channels: speech does not need stereo, and the file halves. */
export function stereoToMono(stereo) {
  const frames = Math.floor(stereo.length / 4);
  const mono = Buffer.alloc(frames * 2);
  for (let i = 0; i < frames; i++) {
    const left = stereo.readInt16LE(i * 4);
    const right = stereo.readInt16LE(i * 4 + 2);
    mono.writeInt16LE((left + right) >> 1, i * 2);
  }
  return mono;
}

/** The 44-byte header that makes raw 16-bit mono PCM a .wav file. */
export function wavHeader(dataBytes, sampleRate = SAMPLE_RATE) {
  const header = Buffer.alloc(44);
  header.write('RIFF', 0, 'ascii');
  header.writeUInt32LE(36 + dataBytes, 4);
  header.write('WAVE', 8, 'ascii');
  header.write('fmt ', 12, 'ascii');
  header.writeUInt32LE(16, 16); // size of the fmt section
  header.writeUInt16LE(1, 20); // PCM
  header.writeUInt16LE(1, 22); // mono
  header.writeUInt32LE(sampleRate, 24);
  header.writeUInt32LE(sampleRate * 2, 28); // bytes per second
  header.writeUInt16LE(2, 32); // bytes per sample frame
  header.writeUInt16LE(16, 34); // bits per sample
  header.write('data', 36, 'ascii');
  header.writeUInt32LE(dataBytes, 40);
  return header;
}

export function monoToWav(mono, sampleRate = SAMPLE_RATE) {
  return Buffer.concat([wavHeader(mono.length, sampleRate), mono]);
}

export function monoSeconds(mono) {
  return mono.length / BYTES_PER_MONO_SECOND;
}
