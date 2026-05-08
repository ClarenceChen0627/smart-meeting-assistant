import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useAudioRecording } from '../src/hooks/useAudioRecording';

class FakeAudioContext {
  static instances: FakeAudioContext[] = [];

  state: AudioContextState | 'interrupted' = 'running';
  sampleRate = 48000;
  destination = {};
  onstatechange: (() => void) | null = null;
  resume = vi.fn(async () => {
    this.state = 'running';
  });
  close = vi.fn(async () => {
    this.state = 'closed';
  });
  createMediaStreamSource = vi.fn(() => ({
    connect: vi.fn(),
    disconnect: vi.fn(),
  }));
  createScriptProcessor = vi.fn(() => ({
    connect: vi.fn(),
    disconnect: vi.fn(),
    onaudioprocess: null,
  }));
  createGain = vi.fn(() => ({
    connect: vi.fn(),
    disconnect: vi.fn(),
    gain: { value: 1 },
  }));

  constructor() {
    FakeAudioContext.instances.push(this);
  }
}

const createTrack = () => {
  const target = new EventTarget();
  return Object.assign(target, {
    stop: vi.fn(),
  }) as EventTarget & { stop: ReturnType<typeof vi.fn> };
};

const createStream = (track = createTrack()) => ({
  getTracks: () => [track],
  getAudioTracks: () => [track],
});

const setMediaDevices = (mediaDevices?: Partial<MediaDevices>) => {
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: mediaDevices,
  });
};

beforeEach(() => {
  FakeAudioContext.instances = [];
  vi.stubGlobal('AudioContext', FakeAudioContext);
  Object.defineProperty(window, 'AudioContext', {
    configurable: true,
    value: FakeAudioContext,
  });
  setMediaDevices({
    getUserMedia: vi.fn(async () => createStream() as unknown as MediaStream),
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('useAudioRecording', () => {
  it('reports unsupported microphone capture before requesting audio', async () => {
    setMediaDevices(undefined);
    const onError = vi.fn();
    const onStatusChange = vi.fn();

    const { result } = renderHook(() =>
      useAudioRecording({
        onAudioData: vi.fn(),
        onStatusChange,
        onError,
      })
    );

    await expect(result.current.startRecording()).rejects.toThrow(
      'Microphone recording is not supported in this browser.'
    );
    expect(onError).toHaveBeenCalledWith('Microphone recording is not supported in this browser.');
    expect(onStatusChange).not.toHaveBeenCalledWith('Requesting microphone access...');
  });

  it('reports and stops when the microphone track ends unexpectedly', async () => {
    const track = createTrack();
    setMediaDevices({
      getUserMedia: vi.fn(async () => createStream(track) as unknown as MediaStream),
    });
    const onError = vi.fn();
    const onInterrupted = vi.fn();
    const onStatusChange = vi.fn();

    const { result } = renderHook(() =>
      useAudioRecording({
        onAudioData: vi.fn(),
        onStatusChange,
        onError,
        onInterrupted,
      })
    );

    await act(async () => {
      await result.current.startRecording();
    });
    await act(async () => {
      track.dispatchEvent(new Event('ended'));
      await Promise.resolve();
    });

    const message = 'Microphone input ended. Recording was interrupted by the browser or operating system.';
    expect(onStatusChange).toHaveBeenCalledWith(message);
    expect(onError).toHaveBeenCalledWith(message);
    expect(onInterrupted).toHaveBeenCalledWith(message);
    expect(track.stop).toHaveBeenCalled();
  });

  it('surfaces suspended audio engine state', async () => {
    const onStatusChange = vi.fn();
    const { result } = renderHook(() =>
      useAudioRecording({
        onAudioData: vi.fn(),
        onStatusChange,
      })
    );

    await act(async () => {
      await result.current.startRecording();
    });

    const audioContext = FakeAudioContext.instances[0];
    audioContext.state = 'suspended';
    act(() => {
      audioContext.onstatechange?.();
    });

    expect(onStatusChange).toHaveBeenCalledWith(
      'Audio engine is suspended. Keep this tab active and the screen awake.'
    );
  });

  it('warns when the page goes into the background', async () => {
    const onStatusChange = vi.fn();
    const { result } = renderHook(() =>
      useAudioRecording({
        onAudioData: vi.fn(),
        onStatusChange,
      })
    );

    await act(async () => {
      await result.current.startRecording();
    });

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    });
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(onStatusChange).toHaveBeenCalledWith(
      'Page is in the background. Mobile browsers may pause microphone capture.'
    );
  });
});
