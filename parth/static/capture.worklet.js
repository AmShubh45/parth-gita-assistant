// Microphone capture: mono, resampled to 16 kHz, sent in ~32 ms chunks of 16-bit PCM.
// The AudioContext runs at the device rate (Firefox refuses to connect a mic to a 16 kHz context),
// so we resample here by averaging. The browser's own gain control is off (it puts phones in call mode,
// which makes all sound quiet), so Live turns on a gentle automatic gain here with {agc: true}.
class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.acc = 0; this.sum = 0; this.n = 0;
    this.out = new Int16Array(512); this.i = 0;
    this.agc = false; this.gain = 1; this.env = 0.05;
    this.port.onmessage = (e) => { if (e.data && typeof e.data.agc === "boolean") this.agc = e.data.agc; };
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    let level = 0;
    for (let k = 0; k < ch.length; k++) {
      let s = ch[k];
      if (this.agc) {
        const a = s < 0 ? -s : s;
        this.env = a > this.env ? a : this.env * 0.99997;            // peak envelope, ~1 s release
        const want = Math.min(6, 0.3 / Math.max(this.env, 0.01));    // aim speech peaks at about 0.3
        this.gain += (want - this.gain) * 0.0002;
        s = Math.max(-1, Math.min(1, s * this.gain));
      }
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
