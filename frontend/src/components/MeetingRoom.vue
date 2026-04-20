<template>
  <div class="meeting-room">
    <aside class="sidebar" :style="sidebarStyle">
      <div class="logo">
        <h2>Smart Meeting Assistant</h2>
      </div>

      <div class="scene-selector">
        <h3>Meeting Scene</h3>
        <el-radio-group v-model="selectedScene" @change="handleSceneChange">
          <el-radio label="finance">Finance</el-radio>
          <el-radio label="hr">HR</el-radio>
        </el-radio-group>
      </div>

      <div class="translation-selector">
        <h3>Translation</h3>
        <el-select
          v-model="selectedTargetLanguage"
          :disabled="isStarting || isRecording || isFinalizing"
          size="large"
          class="translation-select"
        >
          <el-option
            v-for="option in targetLanguageOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
      </div>

      <div class="summary-section">
        <h3>Meeting Summary</h3>
        <div v-if="summary" class="summary-content">
          <div class="summary-item" v-if="summary.todos?.length">
            <h4>To-Dos</h4>
            <ul>
              <li v-for="(todo, idx) in summary.todos" :key="idx">{{ todo }}</li>
            </ul>
          </div>
          <div class="summary-item" v-if="summary.decisions?.length">
            <h4>Decisions</h4>
            <ul>
              <li v-for="(decision, idx) in summary.decisions" :key="idx">{{ decision }}</li>
            </ul>
          </div>
          <div class="summary-item" v-if="summary.risks?.length">
            <h4>Risks</h4>
            <ul>
              <li v-for="(risk, idx) in summary.risks" :key="idx">{{ risk }}</li>
            </ul>
          </div>
          <div v-if="!hasSummaryContent" class="summary-empty">
            No actionable items were extracted from this meeting.
          </div>
        </div>
        <div v-else class="summary-empty">Summary pending...</div>
      </div>

      <div class="analysis-section">
        <h3>Meeting Analysis</h3>
        <div v-if="analysis" class="analysis-content">
          <div class="analysis-item">
            <h4>Overall Sentiment</h4>
            <p>{{ formatOverallSentiment(analysis.overall_sentiment) }}</p>
          </div>
          <div class="analysis-item">
            <h4>Engagement Level</h4>
            <p>{{ formatEngagementLevel(analysis.engagement_level) }}</p>
          </div>
          <div class="analysis-item">
            <h4>Engagement Summary</h4>
            <p>{{ analysis.engagement_summary || 'Analysis pending...' }}</p>
          </div>
          <div class="analysis-item">
            <h4>Signals</h4>
            <ul>
              <li>Agreement: {{ analysis.signal_counts.agreement }}</li>
              <li>Disagreement: {{ analysis.signal_counts.disagreement }}</li>
              <li>Tension: {{ analysis.signal_counts.tension }}</li>
              <li>Hesitation: {{ analysis.signal_counts.hesitation }}</li>
            </ul>
          </div>
        </div>
        <div v-else class="analysis-empty">Analysis pending...</div>
      </div>

      <div class="controls">
        <el-button
          :type="isRecording ? 'danger' : 'success'"
          :icon="isRecording ? VideoPause : VideoPlay"
          :disabled="isStarting || isFinalizing"
          :loading="isStarting || isFinalizing"
          @click="toggleRecording"
          size="large"
          round
        >
          {{ buttonText }}
        </el-button>
      </div>

      <p v-if="isFinalizing" class="finalizing-hint">Generating final summary...</p>
      <p v-if="serverError" class="error-hint">{{ serverError }}</p>

      <details class="diagnostics">
        <summary class="diagnostics-summary">Session Status</summary>
        <p class="diagnostic-line">{{ connectionStatus }}</p>
        <p class="diagnostic-line">{{ audioStatus }}</p>
        <p class="diagnostic-line diagnostic-error">{{ lastFailure }}</p>
      </details>
    </aside>

    <div
      class="sidebar-resizer"
      @mousedown="startResizing"
      @dblclick="resetSidebarWidth"
      title="Drag to resize. Double-click to reset."
    ></div>

    <main class="main-content">
      <div class="audio-visualizer" v-if="isRecording">
        <div class="wave-container">
          <div
            v-for="i in 50"
            :key="i"
            class="wave-bar"
            :style="{ animationDelay: `${i * 0.05}s` }"
          ></div>
        </div>
      </div>

      <div class="transcript-container">
        <div class="transcript-header">
          <h2>Live Transcript</h2>
          <span class="status" :class="{ active: statusActive }">
            {{ statusText }}
          </span>
        </div>

        <div class="transcript-list" ref="transcriptList">
          <div
            v-for="(item, idx) in transcripts"
            :key="idx"
            class="transcript-item"
            :class="[`speaker-${item.speaker}`, analysisHighlightClass(item.analysisSignal)]"
          >
            <div class="speaker-badge">{{ item.speaker }}</div>
            <div class="transcript-content">
              <div class="transcript-text">{{ item.text }}</div>
              <div v-if="item.translatedText" class="transcript-translation">
                <span class="translation-label">{{ translationLabel(item.translatedTargetLang) }}</span>
                <span>{{ item.translatedText }}</span>
              </div>
              <div v-if="item.analysisSignal" class="transcript-analysis">
                <span class="analysis-tag">{{ formatSignalLabel(item.analysisSignal) }}</span>
                <span>{{ item.analysisReason }}</span>
              </div>
            </div>
            <div class="transcript-time">{{ formatTime(item.start) }}</div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { useWebSocket } from '@/composables/useWebSocket'
import type {
  MeetingAnalysis,
  MeetingSignalType,
  MeetingSummary,
  TranscriptItem,
  TranscriptTranslation,
  TranslationTargetLanguage
} from '@/types'

const TARGET_SAMPLE_RATE = 16000
const DEFAULT_SIDEBAR_WIDTH = 320
const MIN_SIDEBAR_WIDTH = 260
const MIN_MAIN_WIDTH = 480
const SIDEBAR_WIDTH_STORAGE_KEY = 'smart-meeting-assistant:sidebar-width'
const targetLanguageOptions: Array<{ label: string; value: TranslationTargetLanguage }> = [
  { label: 'English', value: 'en' },
  { label: 'Japanese', value: 'ja' },
  { label: 'Korean', value: 'ko' }
]

interface DisplayTranscriptItem extends TranscriptItem {
  translatedText?: string
  translatedTargetLang?: TranslationTargetLanguage
  analysisSignal?: MeetingSignalType
  analysisReason?: string
  analysisSeverity?: 'low' | 'medium' | 'high'
}

const selectedScene = ref<'finance' | 'hr'>('finance')
const selectedTargetLanguage = ref<TranslationTargetLanguage>('en')
const isStarting = ref(false)
const isRecording = ref(false)
const isFinalizing = ref(false)
const serverError = ref('')
const connectionStatus = ref('Realtime service is idle.')
const audioStatus = ref('Microphone is idle.')
const lastFailure = ref('Last failure: none.')
const isResizing = ref(false)
const sidebarWidth = ref(DEFAULT_SIDEBAR_WIDTH)
const transcripts = ref<DisplayTranscriptItem[]>([])
const analysis = ref<MeetingAnalysis | null>(null)
const summary = ref<MeetingSummary | null>(null)
const transcriptList = ref<HTMLElement>()

const statusText = computed(() => {
  if (isStarting.value) {
    return 'Starting'
  }
  if (isRecording.value) {
    return 'Recording'
  }
  if (isFinalizing.value) {
    return 'Generating summary'
  }
  return 'Idle'
})

const statusActive = computed(() => isStarting.value || isRecording.value || isFinalizing.value)
const hasSummaryContent = computed(() =>
  Boolean(summary.value?.todos?.length || summary.value?.decisions?.length || summary.value?.risks?.length)
)
const sidebarStyle = computed(() => ({
  width: `${sidebarWidth.value}px`,
  flex: `0 0 ${sidebarWidth.value}px`
}))

const buttonText = computed(() => {
  if (isStarting.value) {
    return 'Starting...'
  }
  if (isFinalizing.value) {
    return 'Generating...'
  }
  return isRecording.value ? 'Stop Recording' : 'Start Recording'
})

const { connect, disconnect, finalize, sendAudio, isConnected } = useWebSocket({
  onTranscript: (data: TranscriptItem) => {
    transcripts.value.push({ ...data })
    nextTick(() => {
      if (transcriptList.value) {
        transcriptList.value.scrollTop = transcriptList.value.scrollHeight
      }
    })
  },
  onTranslation: (data: TranscriptTranslation) => {
    const transcript = transcripts.value[data.transcript_index]
    if (!transcript) {
      return
    }
    transcript.translatedText = data.text
    transcript.translatedTargetLang = data.target_lang
    nextTick(() => {
      if (transcriptList.value) {
        transcriptList.value.scrollTop = transcriptList.value.scrollHeight
      }
    })
  },
  onAnalysis: (data: MeetingAnalysis) => {
    analysis.value = data
    transcripts.value.forEach((item) => {
      item.analysisSignal = undefined
      item.analysisReason = undefined
      item.analysisSeverity = undefined
    })
    data.highlights.forEach((highlight) => {
      const transcript = transcripts.value[highlight.transcript_index]
      if (!transcript) {
        return
      }
      transcript.analysisSignal = highlight.signal
      transcript.analysisReason = highlight.reason
      transcript.analysisSeverity = highlight.severity
    })
  },
  onSummary: (data: MeetingSummary) => {
    summary.value = data
  },
  onError: (message: string) => {
    serverError.value = message
    lastFailure.value = `Last failure: ${message}`
    console.error('WebSocket server error:', message)
  },
  onStatusChange: (message: string) => {
    connectionStatus.value = message
  }
})

let audioStream: MediaStream | null = null
let audioContext: AudioContext | null = null
let audioSourceNode: MediaStreamAudioSourceNode | null = null
let processorNode: ScriptProcessorNode | null = null
let silentGainNode: GainNode | null = null

const buildWebSocketUrl = (
  scene: 'finance' | 'hr',
  targetLanguage: TranslationTargetLanguage
): string => {
  const configuredBaseUrl = import.meta.env.VITE_WS_BASE_URL?.trim()
  const query = `scene=${encodeURIComponent(scene)}&target_lang=${encodeURIComponent(targetLanguage)}`
  if (configuredBaseUrl) {
    const normalizedBaseUrl = configuredBaseUrl.replace(/\/+$/, '')
    return `${normalizedBaseUrl}/ws/meeting?${query}`
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.hostname
  const port = import.meta.env.DEV ? '8080' : window.location.port
  return `${protocol}//${host}:${port}/ws/meeting?${query}`
}

const handleSceneChange = (scene: string) => {
  console.log('Scene changed:', scene)
}

const clampSidebarWidth = (width: number): number => {
  const maxWidth = Math.max(MIN_SIDEBAR_WIDTH, window.innerWidth - MIN_MAIN_WIDTH)
  return Math.min(Math.max(width, MIN_SIDEBAR_WIDTH), maxWidth)
}

const applySidebarWidth = (width: number) => {
  sidebarWidth.value = clampSidebarWidth(width)
}

const persistSidebarWidth = () => {
  localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(sidebarWidth.value))
}

const stopResizing = () => {
  if (!isResizing.value) {
    return
  }
  isResizing.value = false
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  window.removeEventListener('mousemove', handleResize)
  window.removeEventListener('mouseup', stopResizing)
  persistSidebarWidth()
}

const handleResize = (event: MouseEvent) => {
  if (!isResizing.value) {
    return
  }
  applySidebarWidth(event.clientX)
}

const startResizing = (event: MouseEvent) => {
  event.preventDefault()
  isResizing.value = true
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('mousemove', handleResize)
  window.addEventListener('mouseup', stopResizing)
}

const resetSidebarWidth = () => {
  applySidebarWidth(DEFAULT_SIDEBAR_WIDTH)
  persistSidebarWidth()
}

const handleWindowResize = () => {
  applySidebarWidth(sidebarWidth.value)
}

const formatClientError = (error: unknown): string => {
  if (error instanceof Error) {
    return error.message || error.name
  }
  if (typeof error === 'string') {
    return error
  }
  return 'Unknown client-side error.'
}

const toggleRecording = async () => {
  if (isFinalizing.value) {
    return
  }
  if (isRecording.value) {
    await stopRecording()
    return
  }
  await startRecording()
}

const startRecording = async () => {
  try {
    isStarting.value = true
    lastFailure.value = 'Last failure: none.'
    audioStatus.value = 'Requesting microphone access...'
    audioStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      }
    })
    audioStatus.value = 'Microphone access granted.'
    audioStream.getTracks().forEach((track) => {
      track.onended = () => {
        audioStatus.value = 'Microphone stream ended.'
      }
      track.onmute = () => {
        audioStatus.value = 'Microphone track muted.'
      }
      track.onunmute = () => {
        audioStatus.value = 'Microphone track active.'
      }
    })
    const wsUrl = buildWebSocketUrl(selectedScene.value, selectedTargetLanguage.value)

    await connect(wsUrl)

    audioContext = new AudioContext()
    await audioContext.resume()
    audioStatus.value = `Audio engine running (${audioContext.state}, ${audioContext.sampleRate}Hz).`
    audioContext.onstatechange = () => {
      audioStatus.value = `Audio engine state: ${audioContext?.state ?? 'closed'} (${audioContext?.sampleRate ?? 'unknown'}Hz).`
    }

    audioSourceNode = audioContext.createMediaStreamSource(audioStream)
    if (typeof audioContext.createScriptProcessor !== 'function') {
      throw new Error('ScriptProcessorNode is not supported in this browser.')
    }
    processorNode = audioContext.createScriptProcessor(2048, 1, 1)
    silentGainNode = audioContext.createGain()
    silentGainNode.gain.value = 0

    processorNode.onaudioprocess = (event) => {
      if (!isConnected.value) {
        return
      }
      const inputData = event.inputBuffer.getChannelData(0)
      const normalizedChunk = downsampleAudio(
        inputData,
        event.inputBuffer.sampleRate,
        TARGET_SAMPLE_RATE
      )
      sendAudio(encodePcm16Chunk(normalizedChunk))
    }

    audioSourceNode.connect(processorNode)
    processorNode.connect(silentGainNode)
    silentGainNode.connect(audioContext.destination)

    isRecording.value = true
    isFinalizing.value = false
    serverError.value = ''
    connectionStatus.value = 'Realtime service connected.'
    transcripts.value = []
    analysis.value = null
    summary.value = null
  } catch (error) {
    const errorMessage = formatClientError(error)
    serverError.value = errorMessage
    lastFailure.value = `Last failure: ${errorMessage}`
    connectionStatus.value = 'Realtime startup failed.'
    audioStatus.value = `Failed to start microphone or audio pipeline: ${errorMessage}`
    console.error('Failed to start recording:', error)
    await cleanupLocalAudio({ preserveStatusMessage: true })
    disconnect({ preserveStatusMessage: true })
  } finally {
    isStarting.value = false
  }
}

const translationLabel = (targetLanguage?: TranslationTargetLanguage): string => {
  return targetLanguageOptions.find((option) => option.value === targetLanguage)?.label ?? 'Translation'
}

const formatOverallSentiment = (value: MeetingAnalysis['overall_sentiment']): string => {
  return {
    positive: 'Positive',
    neutral: 'Neutral',
    negative: 'Negative',
    mixed: 'Mixed'
  }[value]
}

const formatEngagementLevel = (value: MeetingAnalysis['engagement_level']): string => {
  return {
    low: 'Low',
    medium: 'Medium',
    high: 'High'
  }[value]
}

const formatSignalLabel = (value: MeetingSignalType): string => {
  return {
    agreement: 'Agreement',
    disagreement: 'Disagreement',
    tension: 'Tension',
    hesitation: 'Hesitation'
  }[value]
}

const analysisHighlightClass = (signal?: MeetingSignalType): string | undefined => {
  if (!signal) {
    return undefined
  }
  return `analysis-${signal}`
}

const stopRecording = async () => {
  audioStatus.value = 'Stopping microphone...'
  await cleanupLocalAudio()
  isRecording.value = false
  audioStatus.value = 'Microphone stopped.'

  if (!isConnected.value) {
    disconnect()
    return
  }

  isFinalizing.value = true
  try {
    await finalize()
  } catch (error) {
    const errorMessage = formatClientError(error)
    serverError.value = errorMessage
    lastFailure.value = `Last failure: ${errorMessage}`
    console.error('Failed to finalize session:', error)
    disconnect()
  } finally {
    isFinalizing.value = false
  }
}

const encodePcm16Chunk = (inputData: Float32Array): ArrayBuffer => {
  const buffer = new ArrayBuffer(inputData.length * 2)
  const view = new DataView(buffer)

  for (let index = 0; index < inputData.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, inputData[index]))
    const normalized = sample < 0 ? sample * 0x8000 : sample * 0x7fff
    view.setInt16(index * 2, normalized, true)
  }

  return buffer
}

const downsampleAudio = (
  inputData: Float32Array,
  sourceSampleRate: number,
  targetSampleRate: number
): Float32Array => {
  if (sourceSampleRate === targetSampleRate) {
    return inputData
  }

  const sampleRateRatio = sourceSampleRate / targetSampleRate
  const outputLength = Math.round(inputData.length / sampleRateRatio)
  const output = new Float32Array(outputLength)
  let outputIndex = 0
  let inputIndex = 0

  while (outputIndex < outputLength) {
    const nextInputIndex = Math.round((outputIndex + 1) * sampleRateRatio)
    let accumulator = 0
    let count = 0

    for (let index = inputIndex; index < nextInputIndex && index < inputData.length; index += 1) {
      accumulator += inputData[index]
      count += 1
    }

    output[outputIndex] = count > 0 ? accumulator / count : 0
    outputIndex += 1
    inputIndex = nextInputIndex
  }

  return output
}

const cleanupLocalAudio = async (params?: { preserveStatusMessage?: boolean }) => {
  if (processorNode) {
    processorNode.disconnect()
    processorNode.onaudioprocess = null
    processorNode = null
  }

  if (audioSourceNode) {
    audioSourceNode.disconnect()
    audioSourceNode = null
  }

  if (silentGainNode) {
    silentGainNode.disconnect()
    silentGainNode = null
  }

  if (audioContext) {
    await audioContext.close()
    audioContext = null
    if (!params?.preserveStatusMessage) {
      audioStatus.value = 'Audio engine closed.'
    }
  }

  if (audioStream) {
    audioStream.getTracks().forEach((track) => track.stop())
    audioStream = null
    if (!params?.preserveStatusMessage) {
      audioStatus.value = 'Microphone tracks stopped.'
    }
  }
}

const formatTime = (seconds: number): string => {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

onUnmounted(() => {
  stopResizing()
  window.removeEventListener('resize', handleWindowResize)
  void cleanupLocalAudio()
  disconnect()
})

onMounted(() => {
  const savedWidth = Number(localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY))
  if (Number.isFinite(savedWidth) && savedWidth > 0) {
    applySidebarWidth(savedWidth)
  } else {
    applySidebarWidth(DEFAULT_SIDEBAR_WIDTH)
  }

  window.addEventListener('resize', handleWindowResize)
})
</script>

<style scoped>
.meeting-room {
  display: flex;
  width: 100%;
  height: 100vh;
  min-height: 0;
}

.sidebar {
  background-color: var(--color-bg-secondary);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  border-right: 1px solid var(--color-border);
  overflow-y: auto;
  min-width: 0;
}

.sidebar-resizer {
  flex: 0 0 10px;
  cursor: col-resize;
  position: relative;
  background:
    linear-gradient(
      to right,
      transparent 0,
      transparent 4px,
      rgba(255, 255, 255, 0.08) 4px,
      rgba(255, 255, 255, 0.08) 6px,
      transparent 6px,
      transparent 100%
    );
}

.sidebar-resizer:hover {
  background:
    linear-gradient(
      to right,
      transparent 0,
      transparent 3px,
      rgba(249, 163, 37, 0.7) 3px,
      rgba(249, 163, 37, 0.7) 7px,
      transparent 7px,
      transparent 100%
    );
}

.logo h2 {
  color: var(--color-accent-amber);
  font-size: 24px;
  font-weight: 600;
}

.scene-selector h3,
.translation-selector h3,
.analysis-section h3,
.diagnostics h3,
.summary-section h3 {
  font-size: 16px;
  margin-bottom: 12px;
  color: var(--color-text-primary);
}

.el-radio-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.translation-select {
  width: 100%;
}

.analysis-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.analysis-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.analysis-item {
  padding: 12px;
  border-radius: 8px;
  background-color: var(--color-bg-tertiary);
}

.analysis-item h4 {
  margin-bottom: 6px;
  font-size: 13px;
  color: var(--color-accent-emerald);
}

.analysis-item p,
.analysis-item li {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-secondary);
}

.analysis-item ul {
  margin: 0;
  padding-left: 16px;
}

.analysis-empty {
  padding: 12px;
  border-radius: 8px;
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  font-size: 12px;
}

.controls {
  display: flex;
  justify-content: center;
}

.diagnostics {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: auto;
}

.diagnostics-summary {
  cursor: pointer;
  color: var(--color-text-secondary);
  font-size: 13px;
  user-select: none;
}

.diagnostic-line {
  margin: 0;
  padding: 10px 12px;
  border-radius: 8px;
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  font-size: 12px;
  line-height: 1.5;
  word-break: break-word;
}

.diagnostic-error {
  background-color: rgba(205, 92, 92, 0.12);
  color: #d96c54;
}

.finalizing-hint {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-secondary);
  text-align: center;
}

.error-hint {
  margin: 0;
  padding: 10px 12px;
  border-radius: 8px;
  background-color: rgba(205, 92, 92, 0.12);
  color: #d96c54;
  font-size: 13px;
  line-height: 1.5;
}

.summary-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.summary-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.summary-item h4 {
  font-size: 14px;
  margin-bottom: 8px;
  color: var(--color-accent-emerald);
}

.summary-item ul {
  list-style: none;
  padding-left: 0;
}

.summary-item li {
  padding: 6px 0;
  font-size: 13px;
  color: var(--color-text-secondary);
  border-bottom: 1px solid var(--color-border);
}

.summary-empty {
  padding: 14px 16px;
  border-radius: 8px;
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  background-color: var(--color-bg-primary);
  min-width: 0;
  min-height: 0;
}

.audio-visualizer {
  height: 120px;
  background: linear-gradient(135deg, #2d2d2d 0%, #1a1a1a 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid var(--color-border);
}

.wave-container {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 60px;
}

.wave-bar {
  width: 4px;
  height: 10px;
  background: var(--color-accent-amber);
  border-radius: 2px;
  animation: wave 1s ease-in-out infinite;
}

@keyframes wave {
  0%, 100% { height: 10px; }
  50% { height: 50px; }
}

.transcript-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 24px;
  min-height: 0;
}

.transcript-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.transcript-header h2 {
  font-size: 20px;
  color: var(--color-text-primary);
}

.status {
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 14px;
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
}

.status.active {
  background-color: var(--color-accent-emerald);
  color: white;
}

.transcript-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
  scrollbar-gutter: stable;
}

.transcript-item {
  display: flex;
  gap: 12px;
  padding: 16px;
  background-color: var(--color-bg-secondary);
  border-radius: 8px;
  border-left: 3px solid var(--color-accent-amber);
}

.transcript-item.speaker-Speaker_B {
  border-left-color: var(--color-accent-emerald);
}

.transcript-item.analysis-agreement {
  box-shadow: inset 0 0 0 1px rgba(46, 204, 113, 0.45);
}

.transcript-item.analysis-disagreement {
  box-shadow: inset 0 0 0 1px rgba(231, 76, 60, 0.45);
}

.transcript-item.analysis-tension {
  box-shadow: inset 0 0 0 1px rgba(243, 156, 18, 0.45);
}

.transcript-item.analysis-hesitation {
  box-shadow: inset 0 0 0 1px rgba(241, 196, 15, 0.45);
}

.transcript-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.speaker-badge {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background-color: var(--color-accent-amber);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  flex-shrink: 0;
}

.speaker-Speaker_B .speaker-badge {
  background-color: var(--color-accent-emerald);
}

.transcript-text {
  color: var(--color-text-primary);
  line-height: 1.6;
}

.transcript-translation {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: var(--color-text-secondary);
  line-height: 1.6;
}

.transcript-analysis {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: var(--color-text-secondary);
  line-height: 1.5;
  font-size: 12px;
}

.analysis-tag {
  display: inline-flex;
  align-self: flex-start;
  padding: 4px 8px;
  border-radius: 999px;
  background-color: rgba(255, 255, 255, 0.08);
  color: var(--color-text-primary);
  font-size: 11px;
  font-weight: 600;
}

.translation-label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-accent-emerald);
}

.transcript-time {
  color: var(--color-text-secondary);
  font-size: 12px;
  align-self: flex-start;
}

@media (max-width: 960px) {
  .sidebar-resizer {
    display: none;
  }

  .sidebar {
    width: 320px !important;
    flex: 0 0 320px !important;
  }
}
</style>
