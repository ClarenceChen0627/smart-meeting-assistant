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
  type: 'transcript' | 'translation' | 'analysis' | 'summary' | 'error'
  data: TranscriptItem | TranscriptTranslation | MeetingAnalysis | MeetingSummary | string
}

export interface WebSocketControlMessage {
  type: 'finalize'
}
