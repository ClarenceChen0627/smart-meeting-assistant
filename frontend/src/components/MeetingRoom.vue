<template>
  <div class="meeting-room">
    <aside class="sidebar">
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

      <div class="controls">
        <el-button
          :type="isRecording ? 'danger' : 'success'"
          :icon="isRecording ? VideoPause : VideoPlay"
          :disabled="isFinalizing"
          :loading="isFinalizing"
          @click="toggleRecording"
          size="large"
          round
        >
          {{ buttonText }}
        </el-button>
      </div>

      <p v-if="isFinalizing" class="finalizing-hint">Generating final summary...</p>

      <div class="summary-section" v-if="summary">
        <h3>Meeting Summary</h3>
        <div class="summary-content">
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
        </div>
      </div>
    </aside>

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
            :class="`speaker-${item.speaker}`"
          >
            <div class="speaker-badge">{{ item.speaker }}</div>
            <div class="transcript-text">{{ item.text }}</div>
            <div class="transcript-time">{{ formatTime(item.start) }}</div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref } from 'vue'
import { VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { useWebSocket } from '@/composables/useWebSocket'
import type { MeetingSummary, TranscriptItem } from '@/types'

const selectedScene = ref<'finance' | 'hr'>('finance')
const isRecording = ref(false)
const isFinalizing = ref(false)
const transcripts = ref<TranscriptItem[]>([])
const summary = ref<MeetingSummary | null>(null)
const transcriptList = ref<HTMLElement>()

const statusText = computed(() => {
  if (isRecording.value) {
    return 'Recording'
  }
  if (isFinalizing.value) {
    return 'Generating summary'
  }
  return 'Idle'
})

const statusActive = computed(() => isRecording.value || isFinalizing.value)

const buttonText = computed(() => {
  if (isFinalizing.value) {
    return 'Generating...'
  }
  return isRecording.value ? 'Stop Recording' : 'Start Recording'
})

const { connect, disconnect, finalize, sendAudio, isConnected } = useWebSocket({
  onTranscript: (data: TranscriptItem) => {
    transcripts.value.push(data)
    nextTick(() => {
      if (transcriptList.value) {
        transcriptList.value.scrollTop = transcriptList.value.scrollHeight
      }
    })
  },
  onSummary: (data: MeetingSummary) => {
    summary.value = data
  },
  onError: (message: string) => {
    console.error('WebSocket server error:', message)
  }
})

let mediaRecorder: MediaRecorder | null = null
let audioStream: MediaStream | null = null

const buildWebSocketUrl = (scene: 'finance' | 'hr'): string => {
  const configuredBaseUrl = import.meta.env.VITE_WS_BASE_URL?.trim()
  if (configuredBaseUrl) {
    const normalizedBaseUrl = configuredBaseUrl.replace(/\/+$/, '')
    return `${normalizedBaseUrl}/ws/meeting?scene=${scene}`
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.hostname
  const port = import.meta.env.DEV ? '8080' : window.location.port
  return `${protocol}//${host}:${port}/ws/meeting?scene=${scene}`
}

const handleSceneChange = (scene: string) => {
  console.log('Scene changed:', scene)
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
    audioStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const wsUrl = buildWebSocketUrl(selectedScene.value)

    await connect(wsUrl)

    mediaRecorder = new MediaRecorder(audioStream, {
      mimeType: 'audio/webm;codecs=opus',
      audioBitsPerSecond: 16000
    })

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0 && isConnected.value) {
        sendAudio(event.data)
      }
    }

    mediaRecorder.start(3000)
    isRecording.value = true
    isFinalizing.value = false
    transcripts.value = []
    summary.value = null
  } catch (error) {
    console.error('Failed to start recording:', error)
    cleanupLocalAudio()
    disconnect()
  }
}

const stopRecording = async () => {
  const recorder = mediaRecorder
  if (recorder && recorder.state !== 'inactive') {
    await new Promise<void>((resolve) => {
      recorder.addEventListener('stop', () => resolve(), { once: true })
      recorder.stop()
    })
  }

  mediaRecorder = null
  cleanupLocalAudio()
  isRecording.value = false

  if (!isConnected.value) {
    disconnect()
    return
  }

  isFinalizing.value = true
  try {
    await finalize()
  } catch (error) {
    console.error('Failed to finalize session:', error)
    disconnect()
  } finally {
    isFinalizing.value = false
  }
}

const cleanupLocalAudio = () => {
  if (audioStream) {
    audioStream.getTracks().forEach((track) => track.stop())
    audioStream = null
  }
}

const formatTime = (seconds: number): string => {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

onUnmounted(() => {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop()
  }
  mediaRecorder = null
  cleanupLocalAudio()
  disconnect()
})
</script>

<style scoped>
.meeting-room {
  display: flex;
  width: 100%;
  height: 100vh;
}

.sidebar {
  width: 320px;
  background-color: var(--color-bg-secondary);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  border-right: 1px solid var(--color-border);
}

.logo h2 {
  color: var(--color-accent-amber);
  font-size: 24px;
  font-weight: 600;
}

.scene-selector h3,
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

.controls {
  display: flex;
  justify-content: center;
}

.finalizing-hint {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-secondary);
  text-align: center;
}

.summary-section {
  flex: 1;
  overflow-y: auto;
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

.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  background-color: var(--color-bg-primary);
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
  flex: 1;
  color: var(--color-text-primary);
  line-height: 1.6;
}

.transcript-time {
  color: var(--color-text-secondary);
  font-size: 12px;
  align-self: flex-start;
}
</style>
