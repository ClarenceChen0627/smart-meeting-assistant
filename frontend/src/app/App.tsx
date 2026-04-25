import { useEffect, useState } from 'react';
import { AlertCircle, History, Mic, MicOff, Pause, Play, RotateCcw } from 'lucide-react';

import { ActionItemsPanel } from './components/ActionItemsPanel';
import { ASRProviderControls } from './components/ASRProviderControls';
import { MeetingAnalysisPanel } from './components/MeetingAnalysisPanel';
import { MeetingHistorySheet } from './components/MeetingHistorySheet';
import { SceneControls } from './components/SceneControls';
import { SummaryPanel } from './components/SummaryPanel';
import { TranscriptPanel } from './components/TranscriptPanel';
import { TranslationControls } from './components/TranslationControls';
import { useAudioRecording } from '../hooks/useAudioRecording';
import { useWebSocket } from '../hooks/useWebSocket';
import type {
  ASRProvider,
  MeetingAnalysis,
  MeetingHistoryListItem,
  MeetingHistoryTranscriptItem,
  MeetingRecord,
  MeetingSummary,
  TranscriptItem,
  TranslationTargetLanguage,
} from '../types';

interface DisplayTranscriptItem extends TranscriptItem {
  id: string;
  translatedText?: string;
  translatedTargetLang?: TranslationTargetLanguage;
  analysisSignal?: string;
  analysisReason?: string;
  analysisSeverity?: 'low' | 'medium' | 'high';
}

const buildApiBaseUrl = () => {
  const explicitBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
  if (explicitBaseUrl) {
    return explicitBaseUrl.replace(/\/+$/, '');
  }

  const webSocketBaseUrl = import.meta.env.VITE_WS_BASE_URL?.trim();
  if (webSocketBaseUrl) {
    return webSocketBaseUrl.replace(/^ws/i, 'http').replace(/\/+$/, '');
  }

  return 'http://localhost:8080';
};

const buildWebSocketUrl = (scene: string, targetLang: string, provider: ASRProvider) => {
  const baseUrl = import.meta.env.VITE_WS_BASE_URL?.trim() || 'ws://localhost:8080';
  return `${baseUrl.replace(/\/+$/, '')}/ws/meeting?scene=${scene}&target_lang=${targetLang}&provider=${provider}`;
};

const decorateTranscriptsWithAnalysis = (
  transcripts: DisplayTranscriptItem[],
  analysis: MeetingAnalysis | null
) => {
  const next = transcripts.map((item) => ({
    ...item,
    analysisSignal: undefined,
    analysisReason: undefined,
    analysisSeverity: undefined,
  }));

  if (!analysis) {
    return next;
  }

  analysis.highlights.forEach((highlight) => {
    const item = next.find((entry) => entry.transcript_index === highlight.transcript_index);
    if (!item) {
      return;
    }
    item.analysisSignal = highlight.signal;
    item.analysisReason = highlight.reason;
    item.analysisSeverity = highlight.severity;
  });

  return next;
};

const toDisplayTranscript = (
  transcript: MeetingHistoryTranscriptItem,
  prefix: 'history' | 'live'
): DisplayTranscriptItem => ({
  ...transcript,
  id: `${prefix}-${transcript.transcript_index}`,
  translatedText: transcript.translated_text ?? undefined,
  translatedTargetLang: transcript.translated_target_lang ?? undefined,
});

const formatHistoryTimestamp = (value: string) =>
  new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));

export default function App() {
  const [activeTab, setActiveTab] = useState<'transcript' | 'summary' | 'actions' | 'analysis'>('transcript');
  const [viewMode, setViewMode] = useState<'live' | 'history'>('live');
  const [currentScene, setCurrentScene] = useState<string>('general');
  const [isRecording, setIsRecording] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [isFinalizing, setIsFinalizing] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [currentLanguage, setCurrentLanguage] = useState<TranslationTargetLanguage>('en');
  const [currentProvider, setCurrentProvider] = useState<ASRProvider>('volcengine');
  const [currentMeetingId, setCurrentMeetingId] = useState<string | null>(null);

  const [transcripts, setTranscripts] = useState<DisplayTranscriptItem[]>([]);
  const [analysis, setAnalysis] = useState<MeetingAnalysis | null>(null);
  const [summary, setSummary] = useState<MeetingSummary | null>(null);

  const [historyList, setHistoryList] = useState<MeetingHistoryListItem[]>([]);
  const [selectedHistoryMeeting, setSelectedHistoryMeeting] = useState<MeetingRecord | null>(null);
  const [isHistorySheetOpen, setIsHistorySheetOpen] = useState(false);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [loadingMeetingId, setLoadingMeetingId] = useState<string | null>(null);
  const [deletingMeetingId, setDeletingMeetingId] = useState<string | null>(null);

  const [statusMessage, setStatusMessage] = useState('Ready to start meeting');
  const [serverError, setServerError] = useState('');

  const resetLiveSessionState = () => {
    setCurrentMeetingId(null);
    setTranscripts([]);
    setAnalysis(null);
    setSummary(null);
  };

  const loadHistoryList = async () => {
    try {
      setIsHistoryLoading(true);
      const response = await fetch(`${buildApiBaseUrl()}/api/meetings`);
      if (!response.ok) {
        throw new Error(`Failed to load meeting history (${response.status})`);
      }
      const payload = await response.json() as MeetingHistoryListItem[];
      setHistoryList(payload);
    } catch (error) {
      setServerError(error instanceof Error ? error.message : 'Failed to load meeting history');
    } finally {
      setIsHistoryLoading(false);
    }
  };

  useEffect(() => {
    void loadHistoryList();
  }, []);

  const { connect, disconnect, finalize, sendAudio, isConnected } = useWebSocket({
    onSessionStarted: (data) => {
      setCurrentMeetingId(data.meeting_id);
      setServerError('');
      void loadHistoryList();
    },
    onTranscript: (data) => {
      setTranscripts((prev) => {
        const existing = prev.find((item) => item.transcript_index === data.transcript_index);
        if (existing) {
          return prev.map((item) =>
            item.transcript_index === data.transcript_index
              ? { ...item, ...data }
              : item
          );
        }
        return [...prev, { ...data, id: `live-${data.transcript_index}` }];
      });
    },
    onTranscriptUpdate: (data) => {
      setTranscripts((prev) => prev.map((item) =>
        item.transcript_index === data.transcript_index
          ? { ...item, ...data }
          : item
      ));
    },
    onSpeakerUpdate: (data) => {
      setTranscripts((prev) => prev.map((item) =>
        item.transcript_index === data.transcript_index
          ? { ...item, speaker: data.speaker, speaker_is_final: data.speaker_is_final }
          : item
      ));
    },
    onTranslation: (data) => {
      setTranscripts((prev) => prev.map((item) =>
        item.transcript_index === data.transcript_index
          ? {
              ...item,
              translatedText: data.text,
              translatedTargetLang: data.target_lang,
            }
          : item
      ));
    },
    onAnalysis: (data) => {
      setAnalysis(data);
      setTranscripts((prev) => decorateTranscriptsWithAnalysis(prev, data));
    },
    onSummary: (data) => {
      setSummary(data);
      void loadHistoryList();
    },
    onError: (message) => {
      setServerError(message);
    },
    onStatusChange: (message) => {
      setStatusMessage(message);
    }
  });

  const { startRecording: startAudio, stopRecording: stopAudio } = useAudioRecording({
    onAudioData: (data) => {
      if (!isMuted) {
        sendAudio(data);
      }
    },
    onStatusChange: (status) => {
      console.log(status);
    },
    onError: (error) => {
      setServerError(error instanceof Error ? error.message : String(error));
    }
  });

  const handleStartRecording = async () => {
    try {
      setIsStarting(true);
      setServerError('');
      setViewMode('live');
      setSelectedHistoryMeeting(null);
      setActiveTab('transcript');
      resetLiveSessionState();

      await connect(buildWebSocketUrl(currentScene, currentLanguage, currentProvider));
      await startAudio();

      setIsRecording(true);
      setIsFinalizing(false);
    } catch (error) {
      setServerError('Failed to start recording');
      disconnect();
    } finally {
      setIsStarting(false);
    }
  };

  const handleStopRecording = async () => {
    try {
      setIsFinalizing(true);
      setStatusMessage('Generating summary...');
      await stopAudio();
      setIsRecording(false);

      if (isConnected) {
        await finalize();
      }
    } catch (error) {
      setServerError('Failed to finalize session');
    } finally {
      setIsFinalizing(false);
      disconnect({ preserveStatusMessage: true });
      setStatusMessage('Session finalized.');
      void loadHistoryList();
    }
  };

  const toggleRecording = () => {
    if (isStarting || isFinalizing) {
      return;
    }

    if (isRecording) {
      void handleStopRecording();
      return;
    }

    void handleStartRecording();
  };

  const handleSelectHistoryMeeting = async (meetingId: string) => {
    try {
      setLoadingMeetingId(meetingId);
      setServerError('');
      const response = await fetch(`${buildApiBaseUrl()}/api/meetings/${meetingId}`);
      if (!response.ok) {
        throw new Error(`Failed to load meeting record (${response.status})`);
      }

      const payload = await response.json() as MeetingRecord;
      setSelectedHistoryMeeting(payload);
      setViewMode('history');
      setIsHistorySheetOpen(false);
    } catch (error) {
      setServerError(error instanceof Error ? error.message : 'Failed to load meeting record');
    } finally {
      setLoadingMeetingId(null);
    }
  };

  const handleDeleteHistoryMeeting = async (meetingId: string) => {
    try {
      setDeletingMeetingId(meetingId);
      setServerError('');
      const response = await fetch(`${buildApiBaseUrl()}/api/meetings/${meetingId}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        throw new Error(`Failed to delete meeting record (${response.status})`);
      }

      setHistoryList((prev) => prev.filter((meeting) => meeting.meeting_id !== meetingId));

      if (selectedHistoryMeeting?.meeting_id === meetingId) {
        setSelectedHistoryMeeting(null);
        setViewMode('live');
      }

      if (currentMeetingId === meetingId) {
        resetLiveSessionState();
        setStatusMessage('Ready to start meeting');
        setActiveTab('transcript');
      }

      void loadHistoryList();
    } catch (error) {
      setServerError(error instanceof Error ? error.message : 'Failed to delete meeting record');
    } finally {
      setDeletingMeetingId(null);
    }
  };

  const displayedTranscripts = viewMode === 'history' && selectedHistoryMeeting
    ? decorateTranscriptsWithAnalysis(
        selectedHistoryMeeting.transcripts.map((item) => toDisplayTranscript(item, 'history')),
        selectedHistoryMeeting.analysis
      )
    : transcripts;
  const displayedSummary = viewMode === 'history' ? selectedHistoryMeeting?.summary ?? null : summary;
  const displayedAnalysis = viewMode === 'history' ? selectedHistoryMeeting?.analysis ?? null : analysis;
  const displayedLanguage = viewMode === 'history'
    ? selectedHistoryMeeting?.target_lang ?? currentLanguage
    : currentLanguage;
  const displayedMeetingDate = viewMode === 'history' ? selectedHistoryMeeting?.created_at ?? null : null;
  const isHistoryView = viewMode === 'history' && selectedHistoryMeeting !== null;
  const canOpenHistory = !isRecording && !isStarting && !isFinalizing;

  const tabs = [
    { id: 'transcript', label: 'Live Transcript' },
    { id: 'summary', label: 'Summary' },
    { id: 'actions', label: 'Action Items' },
    { id: 'analysis', label: 'Analysis' }
  ];

  return (
    <div className="size-full bg-gray-50 flex flex-col">
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between gap-6">
          <div>
            <h1 className="text-gray-900 mb-1">Smart Meeting Assistant</h1>
            <p className="text-sm text-gray-500">
              {statusMessage}
            </p>
            {serverError && (
              <p className="text-sm text-red-500 flex items-center gap-1 mt-1">
                <AlertCircle className="w-4 h-4" />
                {serverError}
              </p>
            )}
          </div>

          <div className="flex items-center gap-3 flex-wrap justify-end">
            <button
              type="button"
              onClick={() => setIsHistorySheetOpen(true)}
              disabled={!canOpenHistory}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors text-sm ${
                canOpenHistory
                  ? 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  : 'bg-gray-100 text-gray-400 cursor-not-allowed'
              }`}
            >
              <History className="w-4 h-4" />
              <span>History Meetings</span>
            </button>

            <ASRProviderControls
              currentProvider={currentProvider}
              onProviderChange={setCurrentProvider}
            />
            <SceneControls
              currentScene={currentScene}
              onSceneChange={setCurrentScene}
            />
            <TranslationControls
              currentLanguage={currentLanguage}
              onLanguageChange={(lang) => setCurrentLanguage(lang as TranslationTargetLanguage)}
            />

            <button
              onClick={() => setIsMuted(!isMuted)}
              disabled={!isRecording}
              className={`p-3 rounded-lg transition-colors ${
                !isRecording ? 'opacity-50 cursor-not-allowed bg-gray-100' :
                isMuted
                  ? 'bg-red-100 text-red-600 hover:bg-red-200'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
              title={isMuted ? 'Unmute' : 'Mute'}
            >
              {isMuted ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
            </button>

            <button
              onClick={toggleRecording}
              disabled={isStarting || isFinalizing}
              className={`flex items-center gap-2 px-6 py-3 rounded-lg transition-colors min-w-[200px] justify-center ${
                isStarting || isFinalizing ? 'bg-gray-400 text-white cursor-wait' :
                isRecording
                  ? 'bg-red-600 text-white hover:bg-red-700'
                  : 'bg-blue-600 text-white hover:bg-blue-700'
              }`}
            >
              {isStarting ? (
                <span>Starting...</span>
              ) : isFinalizing ? (
                <span>Generating Summary...</span>
              ) : isRecording ? (
                <>
                  <Pause className="w-5 h-5" />
                  <span>Stop Recording</span>
                </>
              ) : (
                <>
                  <Play className="w-5 h-5" />
                  <span>Start Recording</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      <MeetingHistorySheet
        open={isHistorySheetOpen}
        onOpenChange={setIsHistorySheetOpen}
        meetings={historyList}
        isLoading={isHistoryLoading}
        selectedMeetingId={selectedHistoryMeeting?.meeting_id ?? null}
        loadingMeetingId={loadingMeetingId}
        deletingMeetingId={deletingMeetingId}
        onSelect={(meetingId) => {
          void handleSelectHistoryMeeting(meetingId);
        }}
        onDelete={(meetingId) => {
          void handleDeleteHistoryMeeting(meetingId);
        }}
        onRefresh={() => {
          void loadHistoryList();
        }}
      />

      <div className="bg-white border-b border-gray-200 px-6">
        <div className="flex gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as 'transcript' | 'summary' | 'actions' | 'analysis')}
              className={`px-6 py-3 text-sm transition-colors relative ${
                activeTab === tab.id
                  ? 'text-blue-600'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              {tab.label}
              {activeTab === tab.id && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-600" />
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <div className="p-6 space-y-4">
          {isHistoryView && selectedHistoryMeeting && (
            <div className="max-w-7xl mx-auto rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-medium text-blue-900">Viewing saved meeting record</p>
                <p className="text-sm text-blue-700">
                  {selectedHistoryMeeting.status} meeting from {formatHistoryTimestamp(selectedHistoryMeeting.updated_at)}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setViewMode('live')}
                className="inline-flex items-center gap-2 rounded-lg border border-blue-200 bg-white px-4 py-2 text-sm text-blue-700 transition-colors hover:bg-blue-100"
              >
                <RotateCcw className="w-4 h-4" />
                <span>Return to Live View</span>
              </button>
            </div>
          )}

          {activeTab === 'transcript' && (
            <TranscriptPanel
              isRecording={isRecording && !isHistoryView}
              currentLanguage={displayedLanguage}
              transcripts={displayedTranscripts}
              title={isHistoryView ? 'Meeting Transcript' : 'Live Transcript'}
              description={isHistoryView ? 'Saved transcript, translations, and analysis highlights for this meeting.' : undefined}
              emptyMessage={isHistoryView ? 'No transcript captured for this meeting.' : undefined}
              showLiveBadge={!isHistoryView}
            />
          )}
          {activeTab === 'summary' && (
            <SummaryPanel
              summary={displayedSummary}
              transcripts={displayedTranscripts}
              meetingDate={displayedMeetingDate}
            />
          )}
          {activeTab === 'actions' && (
            <ActionItemsPanel
              summary={displayedSummary}
              transcripts={displayedTranscripts}
              readOnly={isHistoryView}
            />
          )}
          {activeTab === 'analysis' && (
            <MeetingAnalysisPanel analysis={displayedAnalysis} transcripts={displayedTranscripts} />
          )}
        </div>
      </div>
    </div>
  );
}
