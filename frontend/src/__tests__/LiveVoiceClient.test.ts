import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  LiveVoiceConnection,
  floatTo16kPcm,
  isLiveVoiceSupported,
  type AudioContextLike,
  type MediaStreamLike,
} from '../api/liveVoiceClient';

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 3;
  url: string;
  binaryType = '';
  readyState = 0;
  sent: Array<string | ArrayBuffer> = [];
  onopen: ((e: unknown) => void) | null = null;
  onmessage: ((e: { data: unknown }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }
  send(data: string | ArrayBuffer): void {
    this.sent.push(data);
  }
  close(): void {
    this.readyState = 3;
    this.onclose?.({ code: 1000 });
  }
  // test helpers
  open(): void {
    this.readyState = 1;
    this.onopen?.({});
  }
  message(data: unknown): void {
    this.onmessage?.({ data });
  }
  serverClose(code: number): void {
    this.readyState = 3;
    this.onclose?.({ code });
  }
}

function fakeAudioContext(): AudioContextLike {
  return {
    sampleRate: 48000,
    destination: {},
    createMediaStreamSource: () => ({ connect: () => {}, disconnect: () => {} }),
    close: async () => {},
    state: 'running',
  };
}

function fakeStream(): { stream: MediaStreamLike; stopped: { count: number } } {
  const stopped = { count: 0 };
  const stream: MediaStreamLike = {
    getTracks: () => [{ stop: () => (stopped.count += 1) }],
  };
  return { stream, stopped };
}

function makeConnection(
  getUserMedia: (c: MediaStreamConstraints) => Promise<MediaStreamLike>,
  callbacks = {}
) {
  return new LiveVoiceConnection(
    {
      callId: 'call-1',
      token: 'operator-token',
      baseUrl: 'http://127.0.0.1:8000',
      webSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
      audioContextFactory: fakeAudioContext,
      getUserMedia,
    },
    callbacks
  );
}

describe('liveVoiceClient', () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('floatTo16kPcm', () => {
    it('downsamples 48k to 16k (1/3 length) and encodes Int16', () => {
      const input = new Float32Array(300).fill(0.5);
      const buffer = floatTo16kPcm(input, 48000, 16000);
      const view = new Int16Array(buffer);
      expect(view.length).toBe(100);
      expect(view[0]).toBe(Math.trunc(0.5 * 0x7fff));
    });

    it('clamps out-of-range samples', () => {
      const input = new Float32Array([2, -2]);
      const view = new Int16Array(floatTo16kPcm(input, 16000, 16000));
      expect(view[0]).toBe(0x7fff);
      expect(view[1]).toBe(-0x8000);
    });
  });

  describe('isLiveVoiceSupported', () => {
    it('is false when media devices are unavailable (jsdom default)', () => {
      expect(isLiveVoiceSupported()).toBe(false);
    });
  });

  describe('connection lifecycle', () => {
    it('reaches live status and routes transcript/analysis/interrupt events', async () => {
      const { stream } = fakeStream();
      const events: Record<string, unknown[]> = {
        status: [],
        transcript: [],
        analysis: [],
        interrupted: [],
      };
      const conn = makeConnection(async () => stream, {
        onStatus: (s: string) => events.status.push(s),
        onTranscript: (t: unknown) => events.transcript.push(t),
        onAnalysis: (a: unknown) => events.analysis.push(a),
        onInterrupted: () => events.interrupted.push(true),
      });

      await conn.start();
      const ws = FakeWebSocket.instances[0];
      expect(ws).toBeDefined();
      expect(ws.url).toContain('/api/v1/calls/call-1/live');
      expect(ws.url).toContain('token=operator-token');
      // URL should target ws:// not http://
      expect(ws.url.startsWith('ws://')).toBe(true);

      ws.open();
      ws.message(JSON.stringify({ type: 'session_started' }));
      expect(conn.getStatus()).toBe('live');

      ws.message(JSON.stringify({ type: 'transcript_final', speaker: 'customer', text: 'hi', seq: 0 }));
      expect(events.transcript).toHaveLength(1);
      expect((events.transcript[0] as { final: boolean }).final).toBe(true);

      ws.message(JSON.stringify({ type: 'analysis_update', status: 'completed' }));
      expect(events.analysis).toHaveLength(1);

      // Binary audio chunks are buffered; interruption (barge-in) flushes them.
      ws.message(new ArrayBuffer(8));
      expect(conn.receivedAudioChunks).toBe(1);
      ws.message(JSON.stringify({ type: 'interrupted' }));
      expect(events.interrupted).toHaveLength(1);
      expect(conn.receivedAudioChunks).toBe(0);
    });

    it('falls back (does not claim live) when the microphone is denied', async () => {
      const errors: string[] = [];
      const statuses: string[] = [];
      const conn = makeConnection(
        async () => {
          throw new Error('NotAllowedError');
        },
        { onError: (m: string) => errors.push(m), onStatus: (s: string) => statuses.push(s) }
      );
      await conn.start();
      expect(conn.getStatus()).toBe('unavailable');
      expect(errors[0]).toMatch(/text chat/i);
      expect(FakeWebSocket.instances).toHaveLength(0); // never opened a socket
    });

    it('marks unavailable when the backend closes with a policy code', async () => {
      const { stream } = fakeStream();
      const errors: string[] = [];
      const closed: string[] = [];
      const conn = makeConnection(async () => stream, {
        onError: (m: string) => errors.push(m),
        onClosed: (r: string) => closed.push(r),
      });
      await conn.start();
      const ws = FakeWebSocket.instances[0];
      ws.serverClose(4404); // live disabled on backend
      expect(conn.getStatus()).toBe('unavailable');
      expect(errors.length).toBeGreaterThan(0);
      expect(closed[0]).toContain('4404');
    });

    it('end() signals the backend and tears down the stream', async () => {
      const { stream, stopped } = fakeStream();
      const conn = makeConnection(async () => stream);
      await conn.start();
      const ws = FakeWebSocket.instances[0];
      ws.open();
      ws.message(JSON.stringify({ type: 'session_started' }));

      await conn.end();
      expect(conn.getStatus()).toBe('ended');
      const endFrame = ws.sent.find((d) => typeof d === 'string' && d.includes('"end"'));
      expect(endFrame).toBeDefined();
      expect(stopped.count).toBe(1); // mic track stopped on cleanup
    });
  });
});
