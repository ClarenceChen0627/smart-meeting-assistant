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
export type MeetingHistoryStatus = 'draft' | 'finalized'

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

export interface SessionStarted {
  meeting_id: string
  status: MeetingHistoryStatus
  created_at: string
  scene: string
  target_lang: TranslationTargetLanguage | null
  provider: ASRProvider
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
  overview: string
  key_topics: string[]
  action_items: ActionItem[]
  decisions: string[]
  risks: string[]
}

export interface ActionItem {
  task: string
  assignee: string
  deadline: string
  status: 'pending' | 'completed'
  source_excerpt: string
  transcript_index: number | null
  is_actionable: boolean
  confidence: number
  owner_explicit: boolean
  deadline_explicit: boolean
}

export interface MeetingHistoryTranscriptItem extends TranscriptItem {
  translated_text: string | null
  translated_target_lang: TranslationTargetLanguage | null
}

export interface MeetingHistoryListItem {
  meeting_id: string
  status: MeetingHistoryStatus
  scene: string
  target_lang: TranslationTargetLanguage | null
  provider: ASRProvider
  created_at: string
  updated_at: string
  transcript_count: number
  preview_text: string
}

export interface MeetingRecord extends MeetingHistoryListItem {
  transcripts: MeetingHistoryTranscriptItem[]
  summary: MeetingSummary | null
  analysis: MeetingAnalysis | null
}

export interface WebSocketMessage {
  type: 'session_started' | 'transcript' | 'transcript_update' | 'speaker_update' | 'translation' | 'analysis' | 'summary' | 'error'
  data: SessionStarted | TranscriptItem | SpeakerUpdate | TranscriptTranslation | MeetingAnalysis | MeetingSummary | string
}

export interface WebSocketControlMessage {
  type: 'finalize'
}
