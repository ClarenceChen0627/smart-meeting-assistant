export interface TranscriptItem {
  speaker: string
  text: string
  start: number
  end: number
}

export interface MeetingSummary {
  todos: string[]
  decisions: string[]
  risks: string[]
}

export interface WebSocketMessage {
  type: 'transcript' | 'summary' | 'error'
  data: TranscriptItem | MeetingSummary | string
}

export interface WebSocketControlMessage {
  type: 'finalize'
}
