export interface TranscriptItem {
  transcript_index: number
  speaker: string
  speaker_is_final: boolean
  transcript_is_final: boolean
  text: string
  start: number
  end: number
}

export interface SpeakerUpdate {
  transcript_index: number
  speaker: string
  speaker_is_final: true
}

export type ASRProvider = 'volcengine' | 'dashscope'

export type TranslationTargetLanguage =
  | 'en'
  | 'es'
  | 'fr'
  | 'de'
  | 'zh'
  | 'ja'
  | 'ko'
  | 'pt'
  | 'ar'
  | 'hi'

export interface TranscriptTranslation {
  transcript_index: number
  target_lang: TranslationTargetLanguage
  text: string
}

export type MeetingSignalType = 'agreement' | 'disagreement' | 'tension' | 'hesitation'
export type MeetingSentimentLevel = 'positive' | 'neutral' | 'negative' | 'mixed'
export type MeetingEngagementLevel = 'low' | 'medium' | 'high'

export interface MeetingSignalCounts {
  agreement: number
  disagreement: number
  tension: number
  hesitation: number
}

export interface MeetingAnalysisHighlight {
  transcript_index: number
  signal: MeetingSignalType
  severity: 'low' | 'medium' | 'high'
  reason: string
}

export interface MeetingAnalysis {
  overall_sentiment: MeetingSentimentLevel
  engagement_level: MeetingEngagementLevel
  engagement_summary: string
  signal_counts: MeetingSignalCounts
  highlights: MeetingAnalysisHighlight[]
}

export interface MeetingSummary {
  todos: string[]
  decisions: string[]
  risks: string[]
}

export interface WebSocketMessage {
  type: 'transcript' | 'transcript_update' | 'speaker_update' | 'translation' | 'analysis' | 'summary' | 'error'
  data: TranscriptItem | SpeakerUpdate | TranscriptTranslation | MeetingAnalysis | MeetingSummary | string
}

export interface WebSocketControlMessage {
  type: 'finalize'
}
