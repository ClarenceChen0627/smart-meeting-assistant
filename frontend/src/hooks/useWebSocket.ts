import { useRef, useState, useCallback, useEffect } from 'react';
import type {
  MeetingAnalysis,
  MeetingSummary,
  SpeakerUpdate,
  TranscriptItem,
  TranscriptTranslation,
  WebSocketControlMessage,
  WebSocketMessage
} from '../types';

export interface UseWebSocketOptions {
  onTranscript: (data: TranscriptItem) => void;
  onTranscriptUpdate: (data: TranscriptItem) => void;
  onSpeakerUpdate: (data: SpeakerUpdate) => void;
  onTranslation: (data: TranscriptTranslation) => void;
  onAnalysis: (data: MeetingAnalysis) => void;
  onSummary: (data: MeetingSummary) => void;
  onError?: (message: string) => void;
  onStatusChange?: (message: string) => void;
}

export function useWebSocket(options: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  
  // Use a ref for options to avoid stale closures in socket handlers
  const optionsRef = useRef(options);
  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  const OPEN_TIMEOUT_MS = 8000;
  const finalizeResolveRef = useRef<(() => void) | null>(null);
  const finalizeRejectRef = useRef<((reason?: unknown) => void) | null>(null);

  const clearFinalize = useCallback(() => {
    finalizeResolveRef.current = null;
    finalizeRejectRef.current = null;
  }, []);

  const connect = useCallback((url: string): Promise<void> => {
    return new Promise((resolve, reject) => {
      let settled = false;
      let openTimeout: ReturnType<typeof setTimeout> | null = null;
      
      const settleResolve = () => {
        if (settled) return;
        settled = true;
        if (openTimeout) {
          clearTimeout(openTimeout);
          openTimeout = null;
        }
        resolve();
      };
      
      const settleReject = (error: unknown) => {
        if (settled) return;
        settled = true;
        if (openTimeout) {
          clearTimeout(openTimeout);
          openTimeout = null;
        }
        reject(error);
      };

      try {
        optionsRef.current.onStatusChange?.('Connecting to realtime service...');
        console.log('Connecting WebSocket:', url);
        const socket = new WebSocket(url);
        wsRef.current = socket;
        
        openTimeout = setTimeout(() => {
          if (socket.readyState === WebSocket.CONNECTING) {
            optionsRef.current.onStatusChange?.('Realtime service connection timed out.');
            try {
              socket.close();
            } catch {}
            settleReject(new Error('Realtime service connection timed out.'));
          }
        }, OPEN_TIMEOUT_MS);

        socket.onopen = () => {
          setIsConnected(true);
          optionsRef.current.onStatusChange?.('Realtime service connected.');
          console.log('WebSocket connected');
          settleResolve();
        };

        socket.onmessage = (event) => {
          try {
            const message: WebSocketMessage = JSON.parse(event.data);
            if (message.type === 'transcript') {
              optionsRef.current.onTranscript(message.data as TranscriptItem);
            } else if (message.type === 'transcript_update') {
              optionsRef.current.onTranscriptUpdate(message.data as TranscriptItem);
            } else if (message.type === 'speaker_update') {
              optionsRef.current.onSpeakerUpdate(message.data as SpeakerUpdate);
            } else if (message.type === 'translation') {
              optionsRef.current.onTranslation(message.data as TranscriptTranslation);
            } else if (message.type === 'analysis') {
              optionsRef.current.onAnalysis(message.data as MeetingAnalysis);
            } else if (message.type === 'summary') {
              optionsRef.current.onSummary(message.data as MeetingSummary);
            } else if (message.type === 'error') {
              optionsRef.current.onError?.(message.data as string);
            }
          } catch (error) {
            console.error('Failed to parse websocket message:', error, event.data);
          }
        };

        socket.onerror = (error) => {
          optionsRef.current.onStatusChange?.('Realtime service reported a network error.');
          console.error('WebSocket error:', error);
        };

        socket.onclose = (event) => {
          const wasConnected = wsRef.current !== null && wsRef.current.readyState === WebSocket.OPEN;
          setIsConnected(false);
          wsRef.current = null;
          
          const closeMessage = `Realtime service disconnected (${event.code}${
            event.reason ? `: ${event.reason}` : ''
          }).`;
          optionsRef.current.onStatusChange?.(closeMessage);
          console.log('WebSocket closed:', event.code, event.reason);

          if (finalizeResolveRef.current || finalizeRejectRef.current) {
            if (event.code === 1000 || event.code === 1001) {
              finalizeResolveRef.current?.();
            } else {
              finalizeRejectRef.current?.(
                new Error(`WebSocket closed unexpectedly: ${event.code} ${event.reason}`)
              );
            }
            clearFinalize();
          } else if (!wasConnected && event.code !== 1000 && event.code !== 1001) {
            settleReject(new Error(`WebSocket failed to connect: ${event.code} ${event.reason}`));
          }
        };
      } catch (error) {
        optionsRef.current.onStatusChange?.('Failed to create realtime connection.');
        console.error('Failed to create WebSocket:', error);
        settleReject(error);
      }
    });
  }, [clearFinalize]);

  const disconnect = useCallback((params?: { preserveStatusMessage?: boolean }) => {
    if (finalizeRejectRef.current) {
      finalizeRejectRef.current(new Error('WebSocket closed before finalize completed.'));
      clearFinalize();
    }
    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnect');
      wsRef.current = null;
    }
    setIsConnected(false);
    if (!params?.preserveStatusMessage) {
      optionsRef.current.onStatusChange?.('Realtime connection closed locally.');
    }
  }, [clearFinalize]);

  const sendAudio = useCallback((audioChunk: ArrayBuffer) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(audioChunk);
      return;
    }
    console.warn('WebSocket is not connected; audio chunk skipped.');
  }, []);

  const finalize = useCallback((): Promise<void> => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      return Promise.reject(new Error('WebSocket is not connected.'));
    }

    const controlMessage: WebSocketControlMessage = { type: 'finalize' };
    return new Promise((resolve, reject) => {
      finalizeResolveRef.current = resolve;
      finalizeRejectRef.current = reject;
      try {
        wsRef.current?.send(JSON.stringify(controlMessage));
      } catch (error) {
        clearFinalize();
        reject(error);
      }
    });
  }, [clearFinalize]);

  return {
    connect,
    disconnect,
    finalize,
    sendAudio,
    isConnected
  };
}
