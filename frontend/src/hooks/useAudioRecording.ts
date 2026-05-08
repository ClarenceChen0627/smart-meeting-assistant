import { useRef, useCallback } from 'react';

const TARGET_SAMPLE_RATE = 16000;

type AudioContextConstructor = new () => AudioContext;

type WakeLockSentinelLike = EventTarget & {
  release: () => Promise<void>;
};

declare global {
  interface Window {
    webkitAudioContext?: AudioContextConstructor;
  }

  interface Navigator {
    wakeLock?: {
      request: (type: 'screen') => Promise<WakeLockSentinelLike>;
    };
  }
}

export function useAudioRecording({
  onAudioData,
  onStatusChange,
  onError,
  onInterrupted
}: {
  onAudioData: (data: ArrayBuffer) => void;
  onStatusChange?: (status: string) => void;
  onError?: (error: Error | string) => void;
  onInterrupted?: (message: string) => void;
}) {
  const audioContextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const processorNodeRef = useRef<ScriptProcessorNode | null>(null);
  const audioSourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const silentGainNodeRef = useRef<GainNode | null>(null);
  const trackCleanupRef = useRef<(() => void)[]>([]);
  const pageLifecycleCleanupRef = useRef<(() => void) | null>(null);
  const wakeLockRef = useRef<WakeLockSentinelLike | null>(null);
  const wakeLockCleanupRef = useRef<(() => void) | null>(null);
  const isStoppingRef = useRef(false);

  const getAudioContextConstructor = (): AudioContextConstructor | null => {
    if (typeof window === 'undefined') return null;
    return window.AudioContext ?? window.webkitAudioContext ?? null;
  };

  const validateRecordingSupport = () => {
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      throw new Error('Microphone recording is not supported in this browser.');
    }
    if (!getAudioContextConstructor()) {
      throw new Error('Browser audio processing is not supported in this browser.');
    }
  };

  const encodePcm16Chunk = (inputData: Float32Array): ArrayBuffer => {
    const buffer = new ArrayBuffer(inputData.length * 2);
    const view = new DataView(buffer);
    for (let index = 0; index < inputData.length; index += 1) {
      const sample = Math.max(-1, Math.min(1, inputData[index]));
      const normalized = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
      view.setInt16(index * 2, normalized, true);
    }
    return buffer;
  };

  const downsampleAudio = (
    inputData: Float32Array,
    sourceSampleRate: number,
    targetSampleRate: number
  ): Float32Array => {
    if (sourceSampleRate === targetSampleRate) return inputData;
    const sampleRateRatio = sourceSampleRate / targetSampleRate;
    const outputLength = Math.round(inputData.length / sampleRateRatio);
    const output = new Float32Array(outputLength);
    let outputIndex = 0;
    let inputIndex = 0;

    while (outputIndex < outputLength) {
      const nextInputIndex = Math.round((outputIndex + 1) * sampleRateRatio);
      let accumulator = 0;
      let count = 0;
      for (let index = inputIndex; index < nextInputIndex && index < inputData.length; index += 1) {
        accumulator += inputData[index];
        count += 1;
      }
      output[outputIndex] = count > 0 ? accumulator / count : 0;
      outputIndex += 1;
      inputIndex = nextInputIndex;
    }
    return output;
  };

  const clearTrackListeners = () => {
    trackCleanupRef.current.forEach((cleanup) => cleanup());
    trackCleanupRef.current = [];
  };

  const clearPageLifecycleListeners = () => {
    pageLifecycleCleanupRef.current?.();
    pageLifecycleCleanupRef.current = null;
  };

  const releaseWakeLock = useCallback(async () => {
    wakeLockCleanupRef.current?.();
    wakeLockCleanupRef.current = null;

    const wakeLock = wakeLockRef.current;
    wakeLockRef.current = null;
    if (wakeLock) {
      try {
        await wakeLock.release();
      } catch (error) {
        console.warn('Failed to release wake lock:', error);
      }
    }
  }, []);

  const requestWakeLock = useCallback(async () => {
    if (!navigator.wakeLock?.request) return;

    try {
      const wakeLock = await navigator.wakeLock.request('screen');
      wakeLockRef.current = wakeLock;

      const handleRelease = () => {
        wakeLockRef.current = null;
        onStatusChange?.('Screen wake lock was released. Keep the device awake while recording.');
      };

      wakeLock.addEventListener('release', handleRelease);
      wakeLockCleanupRef.current = () => {
        wakeLock.removeEventListener('release', handleRelease);
      };
    } catch (error) {
      console.warn('Wake lock request failed:', error);
      onStatusChange?.('Wake lock is unavailable. Keep the screen awake while recording.');
    }
  }, [onStatusChange]);

  const stopRecording = useCallback(async (params?: { preserveStatusMessage?: boolean }) => {
    isStoppingRef.current = true;

    clearTrackListeners();
    clearPageLifecycleListeners();
    await releaseWakeLock();

    if (processorNodeRef.current) {
      processorNodeRef.current.disconnect();
      processorNodeRef.current.onaudioprocess = null;
      processorNodeRef.current = null;
    }
    if (audioSourceNodeRef.current) {
      audioSourceNodeRef.current.disconnect();
      audioSourceNodeRef.current = null;
    }
    if (silentGainNodeRef.current) {
      silentGainNodeRef.current.disconnect();
      silentGainNodeRef.current = null;
    }
    if (audioContextRef.current) {
      try {
        audioContextRef.current.onstatechange = null;
        await audioContextRef.current.close();
      } catch (e) {}
      audioContextRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (!params?.preserveStatusMessage) {
      onStatusChange?.('Microphone stopped.');
    }
    isStoppingRef.current = false;
  }, [onStatusChange, releaseWakeLock]);

  const registerTrackListeners = useCallback((stream: MediaStream) => {
    clearTrackListeners();

    const handleEnded = () => {
      if (isStoppingRef.current) return;
      const message = 'Microphone input ended. Recording was interrupted by the browser or operating system.';
      onStatusChange?.(message);
      onError?.(message);
      onInterrupted?.(message);
      void stopRecording({ preserveStatusMessage: true });
    };
    const handleMuted = () => {
      if (isStoppingRef.current) return;
      onStatusChange?.('Microphone input is muted by the browser or operating system.');
    };
    const handleUnmuted = () => {
      if (isStoppingRef.current) return;
      onStatusChange?.('Microphone input resumed.');
    };

    stream.getAudioTracks().forEach((track) => {
      track.addEventListener('ended', handleEnded);
      track.addEventListener('mute', handleMuted);
      track.addEventListener('unmute', handleUnmuted);
      trackCleanupRef.current.push(() => {
        track.removeEventListener('ended', handleEnded);
        track.removeEventListener('mute', handleMuted);
        track.removeEventListener('unmute', handleUnmuted);
      });
    });
  }, [onError, onInterrupted, onStatusChange, stopRecording]);

  const registerPageLifecycleListeners = useCallback(() => {
    clearPageLifecycleListeners();
    if (typeof document === 'undefined' || typeof window === 'undefined') return;

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        onStatusChange?.('Page is in the background. Mobile browsers may pause microphone capture.');
        return;
      }

      const audioContext = audioContextRef.current;
      if (audioContext?.state === 'suspended') {
        void audioContext.resume().then(() => {
          onStatusChange?.(`Audio engine running (${audioContext.state}, ${audioContext.sampleRate}Hz).`);
        }).catch((error) => {
          console.warn('Failed to resume audio context:', error);
          onStatusChange?.('Audio engine is suspended. Tap Stop, then Start Recording to recover.');
        });
      } else if (audioContext) {
        onStatusChange?.(`Audio engine running (${audioContext.state}, ${audioContext.sampleRate}Hz).`);
      }
    };

    const handlePageHide = () => {
      onStatusChange?.('Page is closing or suspended. Recording may stop on mobile browsers.');
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('pagehide', handlePageHide);
    pageLifecycleCleanupRef.current = () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('pagehide', handlePageHide);
    };
  }, [onStatusChange]);

  const registerAudioContextStateListener = useCallback((audioContext: AudioContext) => {
    audioContext.onstatechange = () => {
      if (isStoppingRef.current) return;

      const state = audioContext.state as AudioContextState | 'interrupted';

      if (state === 'running') {
        onStatusChange?.(`Audio engine running (${state}, ${audioContext.sampleRate}Hz).`);
        return;
      }

      if (state === 'suspended' || state === 'interrupted') {
        onStatusChange?.('Audio engine is suspended. Keep this tab active and the screen awake.');
        return;
      }

      if (state === 'closed') {
        const message = 'Audio engine closed unexpectedly. Recording was interrupted.';
        onStatusChange?.(message);
        onError?.(message);
        onInterrupted?.(message);
      }
    };
  }, [onError, onInterrupted, onStatusChange]);

  const startRecording = useCallback(async () => {
    try {
      validateRecordingSupport();
      onStatusChange?.('Requesting microphone access...');
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
      streamRef.current = stream;
      registerTrackListeners(stream);
      registerPageLifecycleListeners();
      void requestWakeLock();
      onStatusChange?.('Microphone access granted.');

      const AudioContextCtor = getAudioContextConstructor();
      if (!AudioContextCtor) {
        throw new Error('Browser audio processing is not supported in this browser.');
      }

      const audioContext = new AudioContextCtor();
      registerAudioContextStateListener(audioContext);
      await audioContext.resume();
      audioContextRef.current = audioContext;

      onStatusChange?.(`Audio engine running (${audioContext.state}, ${audioContext.sampleRate}Hz).`);

      const audioSourceNode = audioContext.createMediaStreamSource(stream);
      audioSourceNodeRef.current = audioSourceNode;

      if (typeof audioContext.createScriptProcessor !== 'function') {
        throw new Error('ScriptProcessorNode is not supported in this browser.');
      }
      const processorNode = audioContext.createScriptProcessor(2048, 1, 1);
      processorNodeRef.current = processorNode;

      const silentGainNode = audioContext.createGain();
      silentGainNode.gain.value = 0;
      silentGainNodeRef.current = silentGainNode;

      processorNode.onaudioprocess = (event) => {
        const inputData = event.inputBuffer.getChannelData(0);
        const normalizedChunk = downsampleAudio(inputData, event.inputBuffer.sampleRate, TARGET_SAMPLE_RATE);
        onAudioData(encodePcm16Chunk(normalizedChunk));
      };

      audioSourceNode.connect(processorNode);
      processorNode.connect(silentGainNode);
      silentGainNode.connect(audioContext.destination);

    } catch (error) {
      console.error('Failed to start recording:', error);
      onError?.(error instanceof Error ? error.message : String(error));
      await stopRecording({ preserveStatusMessage: true });
      throw error;
    }
  }, [
    onAudioData,
    onStatusChange,
    onError,
    registerAudioContextStateListener,
    registerPageLifecycleListeners,
    registerTrackListeners,
    requestWakeLock,
    stopRecording,
  ]);

  return {
    startRecording,
    stopRecording
  };
}
