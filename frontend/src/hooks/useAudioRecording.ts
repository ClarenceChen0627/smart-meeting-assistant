import { useRef, useCallback } from 'react';

const TARGET_SAMPLE_RATE = 16000;

export function useAudioRecording({
  onAudioData,
  onStatusChange,
  onError
}: {
  onAudioData: (data: ArrayBuffer) => void;
  onStatusChange?: (status: string) => void;
  onError?: (error: Error | string) => void;
}) {
  const audioContextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const processorNodeRef = useRef<ScriptProcessorNode | null>(null);
  const audioSourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const silentGainNodeRef = useRef<GainNode | null>(null);

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

  const stopRecording = useCallback(async (params?: { preserveStatusMessage?: boolean }) => {
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
  }, [onStatusChange]);

  const startRecording = useCallback(async () => {
    try {
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
      onStatusChange?.('Microphone access granted.');

      const audioContext = new AudioContext();
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
  }, [onAudioData, onStatusChange, onError, stopRecording]);

  return {
    startRecording,
    stopRecording
  };
}
