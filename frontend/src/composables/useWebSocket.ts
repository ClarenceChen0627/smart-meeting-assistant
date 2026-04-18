import { ref } from 'vue'
import type {
  MeetingAnalysis,
  MeetingSummary,
  TranscriptItem,
  TranscriptTranslation,
  WebSocketControlMessage,
  WebSocketMessage
} from '@/types'

interface UseWebSocketOptions {
  onTranscript: (data: TranscriptItem) => void
  onTranslation: (data: TranscriptTranslation) => void
  onAnalysis: (data: MeetingAnalysis) => void
  onSummary: (data: MeetingSummary) => void
  onError?: (message: string) => void
}

export function useWebSocket(options: UseWebSocketOptions) {
  const ws = ref<WebSocket | null>(null)
  const isConnected = ref(false)
  let finalizeResolve: (() => void) | null = null
  let finalizeReject: ((reason?: unknown) => void) | null = null

  const clearFinalize = () => {
    finalizeResolve = null
    finalizeReject = null
  }

  const connect = (url: string): Promise<void> => {
    return new Promise((resolve, reject) => {
      try {
        console.log('Connecting WebSocket:', url)
        const socket = new WebSocket(url)
        ws.value = socket

        socket.onopen = () => {
          isConnected.value = true
          console.log('WebSocket connected')
          resolve()
        }

        socket.onmessage = (event) => {
          try {
            const message: WebSocketMessage = JSON.parse(event.data)
            if (message.type === 'transcript') {
              options.onTranscript(message.data as TranscriptItem)
            } else if (message.type === 'translation') {
              options.onTranslation(message.data as TranscriptTranslation)
            } else if (message.type === 'analysis') {
              options.onAnalysis(message.data as MeetingAnalysis)
            } else if (message.type === 'summary') {
              options.onSummary(message.data as MeetingSummary)
            } else if (message.type === 'error') {
              options.onError?.(message.data as string)
            }
          } catch (error) {
            console.error('Failed to parse websocket message:', error, event.data)
          }
        }

        socket.onerror = (error) => {
          console.error('WebSocket error:', error)
        }

        socket.onclose = (event) => {
          const wasConnected = isConnected.value
          isConnected.value = false
          ws.value = null
          console.log('WebSocket closed:', event.code, event.reason)

          if (finalizeResolve || finalizeReject) {
            if (event.code === 1000 || event.code === 1001) {
              finalizeResolve?.()
            } else {
              finalizeReject?.(
                new Error(`WebSocket closed unexpectedly: ${event.code} ${event.reason}`)
              )
            }
            clearFinalize()
          } else if (!wasConnected && event.code !== 1000 && event.code !== 1001) {
            reject(new Error(`WebSocket failed to connect: ${event.code} ${event.reason}`))
          }
        }
      } catch (error) {
        console.error('Failed to create WebSocket:', error)
        reject(error)
      }
    })
  }

  const disconnect = () => {
    if (finalizeReject) {
      finalizeReject(new Error('WebSocket closed before finalize completed.'))
      clearFinalize()
    }
    if (ws.value) {
      ws.value.close(1000, 'Client disconnect')
      ws.value = null
    }
    isConnected.value = false
  }

  const sendAudio = (audioChunk: ArrayBuffer) => {
    if (ws.value && isConnected.value && ws.value.readyState === WebSocket.OPEN) {
      ws.value.send(audioChunk)
      return
    }
    console.warn('WebSocket is not connected; audio chunk skipped.')
  }

  const finalize = (): Promise<void> => {
    if (!ws.value || ws.value.readyState !== WebSocket.OPEN) {
      return Promise.reject(new Error('WebSocket is not connected.'))
    }

    const controlMessage: WebSocketControlMessage = { type: 'finalize' }
    return new Promise((resolve, reject) => {
      finalizeResolve = resolve
      finalizeReject = reject
      try {
        ws.value?.send(JSON.stringify(controlMessage))
      } catch (error) {
        clearFinalize()
        reject(error)
      }
    })
  }

  return {
    connect,
    disconnect,
    finalize,
    sendAudio,
    isConnected
  }
}
