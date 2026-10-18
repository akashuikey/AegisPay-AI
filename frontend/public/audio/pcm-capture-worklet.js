// PCM capture AudioWorklet for live voice (P2-A11).
// Forwards mono Float32 frames to the main thread, which resamples to 16 kHz PCM16
// and streams them over the WebSocket. Keeping resampling on the main thread keeps
// this processor tiny and portable.
class PcmCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (input && input[0] && input[0].length > 0) {
      // Copy the channel-0 frame; the underlying buffer is reused by the engine.
      this.port.postMessage(new Float32Array(input[0]));
    }
    return true;
  }
}

registerProcessor('pcm-capture', PcmCaptureProcessor);
