// Gapless playback of Gemini's 24 kHz PCM. "interrupt" clears the queue when the person starts talking.
class PlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = []; this.offset = 0;
    this.port.onmessage = (e) => {
      if (e.data === "interrupt") { this.queue = []; this.offset = 0; }
      else this.queue.push(e.data);
    };
  }
  process(_, outputs) {
    const out = outputs[0][0];
    let i = 0;
    while (i < out.length && this.queue.length) {
      const buf = this.queue[0];
      const n = Math.min(out.length - i, buf.length - this.offset);
      out.set(buf.subarray(this.offset, this.offset + n), i);
      i += n; this.offset += n;
      if (this.offset >= buf.length) { this.queue.shift(); this.offset = 0; }
    }
    out.fill(0, i);
    return true;
  }
}
registerProcessor("parth-playback", PlaybackProcessor);
