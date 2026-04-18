export interface TranscriptItem {
  speaker: string
  text: string
  start: number
  end: number
}

export type TranslationTargetLanguage = 'en' | 'ja' | 'ko'

export interface TranscriptTranslation {
  transcript_index: number
  target_lang: TranslationTargetLanguage
  text: string
}

export interface MeetingSummary {
  todos: string[]
  decisions: string[]
  risks: string[]
}

export interface WebSocketMessage {
  type: 'transcript' | 'translation' | 'summary' | 'error'
  data: TranscriptItem | TranscriptTranslation | MeetingSummary | string
}

export interface WebSocketControlMessage {
  type: 'finalize'
}
