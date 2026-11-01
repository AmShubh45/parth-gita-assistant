// Microphone capture for Gemini Live: mono, resampled to 16 kHz, sent in ~32 ms chunks of 16-bit PCM.
// The AudioContext runs at the device rate (Firefox refuses to connect a mic to a 16 kHz context),
// so we resample here by averaging.
class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.acc = 0; this.sum = 0; this.n = 0;
    this.out = new Int16Array(512); this.i = 0;
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    let level = 0;
    for (let k = 0; k < ch.length; k++) {
      const s = ch[k];
      level += s * s;
      this.sum += s; this.n++; this.acc++;
      if (this.acc >= this.ratio) {
        const v = Math.max(-1, Math.min(1, this.sum / this.n));
        this.out[this.i++] = v < 0 ? v * 0x8000 : v * 0x7fff;
        this.acc -= this.ratio; this.sum = 0; this.n = 0;
        if (this.i === this.out.length) {
          this.port.postMessage({ pcm: this.out.buffer.slice(0), level: Math.sqrt(level / ch.length) });
          this.i = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor("parth-capture", CaptureProcessor);
