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

export type ASRProvider = 'volcengine' | 'dashscope' | 'demo'
export type MeetingHistoryStatus = 'draft' | 'processing' | 'failed' | 'finalized'
export type MeetingSourceType = 'live' | 'upload'
export type MeetingProcessingStage = 'transcribing' | 'translating' | 'analyzing' | 'summarizing'

export interface GlossaryTerm {
  term: string
  replacement: string | null
  note: string | null
}

export interface GlossaryTermRecord extends GlossaryTerm {
  id: string
  created_at: string
  updated_at: string
}

export interface GlossaryTermCreate {
  term: string
  replacement?: string | null
  note?: string | null
}

export interface GlossaryTermUpdate {
  term?: string | null
  replacement?: string | null
  note?: string | null
}

export interface SpeakerLabelUpdate {
  from: string
  to: string
}

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
  source_type: MeetingSourceType
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

export interface ParticipantAnalysis {
  speaker: string
  transcript_count: number
  speaking_time_seconds: number
  signal_counts: MeetingSignalCounts
  sentiment: MeetingSentimentLevel
  engagement_level: MeetingEngagementLevel
  engagement_summary: string
}

export interface MeetingAnalysis {
  overall_sentiment: MeetingSentimentLevel
  engagement_level: MeetingEngagementLevel
  engagement_summary: string
  signal_counts: MeetingSignalCounts
  highlights: MeetingAnalysisHighlight[]
  participants: ParticipantAnalysis[]
}

export interface MeetingSummary {
  title: string
  overview: string
  key_topics: string[]
  action_items: ActionItem[]
  decisions: string[]
  risks: string[]
}

export interface MeetingSummaryUpdate {
  overview: string
  key_topics: string[]
  action_items: ActionItem[]
  decisions: string[]
  risks: string[]
}

export type ActionItemStatus = 'pending' | 'completed'

export interface ActionItem {
  task: string
  assignee: string
  deadline: string
  status: ActionItemStatus
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
  source_type: MeetingSourceType
  scene: string
  target_lang: TranslationTargetLanguage | null
  provider: ASRProvider
  created_at: string
  updated_at: string
  title: string
  title_manually_edited: boolean
  summary_manually_edited: boolean
  transcript_count: number
  preview_text: string
  processing_stage: MeetingProcessingStage | null
  error_message: string | null
  source_name: string | null
  raw_audio_retained: boolean
  raw_audio_filename: string | null
  raw_audio_content_type: string | null
  raw_audio_size_bytes: number | null
}

export interface MeetingRecord extends MeetingHistoryListItem {
  glossary_terms: GlossaryTerm[]
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
