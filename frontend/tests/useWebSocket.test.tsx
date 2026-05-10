import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useWebSocket, type UseWebSocketOptions } from '../src/hooks/useWebSocket';
import type { MeetingSummary } from '../src/types';

class FakeWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  readyState = FakeWebSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  send = vi.fn();

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  emitMessage(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
  }

  close(code = 1000, reason = 'test close') {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ code, reason } as CloseEvent);
  }
}

const summary: MeetingSummary = {
  title: 'Live review',
  overview: 'The team reviewed live progress.',
  key_topics: ['Progress'],
  decisions: [],
  risks: [],
  action_items: [],
};

const buildOptions = (overrides: Partial<UseWebSocketOptions> = {}): UseWebSocketOptions => ({
  onSessionStarted: vi.fn(),
  onTranscript: vi.fn(),
  onTranscriptUpdate: vi.fn(),
  onSpeakerUpdate: vi.fn(),
  onTranslation: vi.fn(),
  onAnalysis: vi.fn(),
  onRollingSummary: vi.fn(),
  onSummary: vi.fn(),
  ...overrides,
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  FakeWebSocket.instances = [];
});

describe('useWebSocket', () => {
  it('dispatches rolling_summary separately from final summary', async () => {
    vi.stubGlobal('WebSocket', FakeWebSocket);
    const onRollingSummary = vi.fn();
    const onSummary = vi.fn();
    const { result } = renderHook(() => useWebSocket(buildOptions({ onRollingSummary, onSummary })));

    let connectPromise: Promise<void>;
    act(() => {
      connectPromise = result.current.connect('ws://localhost/ws/meeting');
    });
    const socket = FakeWebSocket.instances[0];
    act(() => {
      socket.open();
    });
    await connectPromise!;

    act(() => {
      socket.emitMessage({ type: 'rolling_summary', data: summary });
      socket.emitMessage({ type: 'summary', data: { ...summary, overview: 'Final summary.' } });
    });

    expect(onRollingSummary).toHaveBeenCalledWith(summary);
    expect(onSummary).toHaveBeenCalledWith({ ...summary, overview: 'Final summary.' });
  });
});
