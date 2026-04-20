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
  onStatusChange?: (message: string) => void
}

export function useWebSocket(options: UseWebSocketOptions) {
  const ws = ref<WebSocket | null>(null)
  const isConnected = ref(false)
  const OPEN_TIMEOUT_MS = 8000
  let finalizeResolve: (() => void) | null = null
  let finalizeReject: ((reason?: unknown) => void) | null = null

  const clearFinalize = () => {
    finalizeResolve = null
    finalizeReject = null
  }

  const connect = (url: string): Promise<void> => {
    return new Promise((resolve, reject) => {
      let settled = false
      let openTimeout: ReturnType<typeof setTimeout> | null = null
      const settleResolve = () => {
        if (settled) {
          return
        }
        settled = true
        if (openTimeout) {
          clearTimeout(openTimeout)
          openTimeout = null
        }
        resolve()
      }
      const settleReject = (error: unknown) => {
        if (settled) {
          return
        }
        settled = true
        if (openTimeout) {
          clearTimeout(openTimeout)
          openTimeout = null
        }
        reject(error)
      }

      try {
        options.onStatusChange?.('Connecting to realtime service...')
        console.log('Connecting WebSocket:', url)
        const socket = new WebSocket(url)
        ws.value = socket
        openTimeout = setTimeout(() => {
          if (socket.readyState === WebSocket.CONNECTING) {
            options.onStatusChange?.('Realtime service connection timed out.')
            try {
              socket.close()
            } catch {}
            settleReject(new Error('Realtime service connection timed out.'))
          }
        }, OPEN_TIMEOUT_MS)

        socket.onopen = () => {
          isConnected.value = true
          options.onStatusChange?.('Realtime service connected.')
          console.log('WebSocket connected')
          settleResolve()
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
          options.onStatusChange?.('Realtime service reported a network error.')
          console.error('WebSocket error:', error)
        }

        socket.onclose = (event) => {
          const wasConnected = isConnected.value
          isConnected.value = false
          ws.value = null
          const closeMessage = `Realtime service disconnected (${event.code}${
            event.reason ? `: ${event.reason}` : ''
          }).`
          options.onStatusChange?.(closeMessage)
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
            settleReject(new Error(`WebSocket failed to connect: ${event.code} ${event.reason}`))
          }
        }
      } catch (error) {
        options.onStatusChange?.('Failed to create realtime connection.')
        console.error('Failed to create WebSocket:', error)
        settleReject(error)
      }
    })
  }

  const disconnect = (params?: { preserveStatusMessage?: boolean }) => {
    if (finalizeReject) {
      finalizeReject(new Error('WebSocket closed before finalize completed.'))
      clearFinalize()
    }
    if (ws.value) {
      ws.value.close(1000, 'Client disconnect')
      ws.value = null
    }
    isConnected.value = false
    if (!params?.preserveStatusMessage) {
      options.onStatusChange?.('Realtime connection closed locally.')
    }
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
