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
import { UploadMeetingControls } from './components/UploadMeetingControls';
import { useAudioRecording } from '../hooks/useAudioRecording';
import { useWebSocket } from '../hooks/useWebSocket';
import type {
  ActionItemStatus,
  ASRProvider,
  MeetingAnalysis,
  MeetingHistoryListItem,
  MeetingHistoryTranscriptItem,
  MeetingProcessingStage,
  MeetingRecord,
  MeetingSourceType,
  MeetingSummary,
  MeetingSummaryUpdate,
  TranscriptItem,
  TranslationTargetLanguage,
} from '../types';

type InputMode = 'live' | 'upload';

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

const processingStageLabels: Record<MeetingProcessingStage, string> = {
  transcribing: 'Transcribing uploaded audio',
  translating: 'Generating transcript translations',
  analyzing: 'Analyzing meeting dynamics',
  summarizing: 'Generating meeting summary',
};

const sourceLabels: Record<MeetingSourceType, string> = {
  live: 'live',
  upload: 'upload',
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
  prefix: 'history' | 'live' | 'upload'
): DisplayTranscriptItem => ({
  ...transcript,
  id: `${prefix}-${transcript.transcript_index}`,
  translatedText: transcript.translated_text ?? undefined,
  translatedTargetLang: transcript.translated_target_lang ?? undefined,
});

const toHistoryListItem = (meeting: MeetingRecord): MeetingHistoryListItem => ({
  meeting_id: meeting.meeting_id,
  status: meeting.status,
  source_type: meeting.source_type,
  scene: meeting.scene,
  target_lang: meeting.target_lang,
  provider: meeting.provider,
  created_at: meeting.created_at,
  updated_at: meeting.updated_at,
  title: meeting.title,
  title_manually_edited: meeting.title_manually_edited,
  summary_manually_edited: meeting.summary_manually_edited,
  transcript_count: meeting.transcript_count,
  preview_text: meeting.preview_text,
  processing_stage: meeting.processing_stage,
  error_message: meeting.error_message,
  source_name: meeting.source_name,
});

const mergeMeetingIntoHistoryList = (
  meetings: MeetingHistoryListItem[],
  meeting: MeetingRecord
) => {
  const nextItem = toHistoryListItem(meeting);
  const next = meetings.some((item) => item.meeting_id === nextItem.meeting_id)
    ? meetings.map((item) => (item.meeting_id === nextItem.meeting_id ? nextItem : item))
    : [nextItem, ...meetings];

  return next.sort((left, right) => right.updated_at.localeCompare(left.updated_at));
};

const formatHistoryTimestamp = (value: string) =>
  new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));

const buildUploadStatusMessage = (
  meeting: MeetingRecord | null,
  isUploadingFile: boolean
) => {
  if (isUploadingFile) {
    return 'Uploading audio file...';
  }

  if (!meeting) {
    return 'Select a meeting audio file to generate transcript, summary, action items, and analysis.';
  }

  if (meeting.status === 'processing') {
    return meeting.processing_stage
      ? processingStageLabels[meeting.processing_stage]
      : 'Processing uploaded meeting...';
  }

  if (meeting.status === 'failed') {
    return meeting.error_message || 'Upload processing failed.';
  }

  return 'Upload meeting is ready to review.';
};

export default function App() {
  const [activeTab, setActiveTab] = useState<'transcript' | 'summary' | 'actions' | 'analysis'>('transcript');
  const [inputMode, setInputMode] = useState<InputMode>('live');
  const [currentScene, setCurrentScene] = useState<string>('general');
  const [isRecording, setIsRecording] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [isFinalizing, setIsFinalizing] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [isUploadingFile, setIsUploadingFile] = useState(false);
  const [currentLanguage, setCurrentLanguage] = useState<TranslationTargetLanguage>('en');
  const [currentProvider, setCurrentProvider] = useState<ASRProvider>('volcengine');
  const [currentMeetingId, setCurrentMeetingId] = useState<string | null>(null);
  const [selectedUploadFile, setSelectedUploadFile] = useState<File | null>(null);
  const [uploadInputKey, setUploadInputKey] = useState(0);

  const [transcripts, setTranscripts] = useState<DisplayTranscriptItem[]>([]);
  const [analysis, setAnalysis] = useState<MeetingAnalysis | null>(null);
  const [summary, setSummary] = useState<MeetingSummary | null>(null);

  const [historyList, setHistoryList] = useState<MeetingHistoryListItem[]>([]);
  const [historyMeeting, setHistoryMeeting] = useState<MeetingRecord | null>(null);
  const [activeUploadMeeting, setActiveUploadMeeting] = useState<MeetingRecord | null>(null);
  const [isHistorySheetOpen, setIsHistorySheetOpen] = useState(false);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [loadingMeetingId, setLoadingMeetingId] = useState<string | null>(null);
  const [deletingMeetingId, setDeletingMeetingId] = useState<string | null>(null);
  const [isSavingSummary, setIsSavingSummary] = useState(false);

  const [statusMessage, setStatusMessage] = useState('Ready to start meeting');
  const [serverError, setServerError] = useState('');

  const resetLiveSessionState = () => {
    setCurrentMeetingId(null);
    setTranscripts([]);
    setAnalysis(null);
    setSummary(null);
  };

  const updateHistoryFromMeeting = (meeting: MeetingRecord) => {
    setHistoryList((prev) => mergeMeetingIntoHistoryList(prev, meeting));
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

  const refreshMeetingDetail = async (meetingId: string) => {
    const response = await fetch(`${buildApiBaseUrl()}/api/meetings/${meetingId}`);
    if (!response.ok) {
      throw new Error(`Failed to load meeting record (${response.status})`);
    }

    const payload = await response.json() as MeetingRecord;
    setActiveUploadMeeting((prev) => (prev?.meeting_id === payload.meeting_id ? payload : prev));
    setHistoryMeeting((prev) => (prev?.meeting_id === payload.meeting_id ? payload : prev));
    updateHistoryFromMeeting(payload);
    return payload;
  };

  useEffect(() => {
    void loadHistoryList();
  }, []);

  useEffect(() => {
    const meetingIds = Array.from(
      new Set(
        [
          activeUploadMeeting?.status === 'processing' ? activeUploadMeeting.meeting_id : null,
          historyMeeting?.status === 'processing' ? historyMeeting.meeting_id : null,
        ].filter((value): value is string => Boolean(value))
      )
    );

    if (meetingIds.length === 0) {
      return;
    }

    let cancelled = false;
    const poll = async () => {
      for (const meetingId of meetingIds) {
        try {
          await refreshMeetingDetail(meetingId);
        } catch (error) {
          if (!cancelled) {
            setServerError(error instanceof Error ? error.message : 'Failed to refresh meeting record');
          }
        }
      }
    };

    void poll();
    const intervalId = window.setInterval(() => {
      void poll();
    }, 2000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [activeUploadMeeting?.meeting_id, activeUploadMeeting?.status, historyMeeting?.meeting_id, historyMeeting?.status]);

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

  const handleInputModeChange = (mode: InputMode) => {
    if (isRecording || isStarting || isFinalizing) {
      return;
    }
    setInputMode(mode);
    setHistoryMeeting(null);
  };

  const handleStartRecording = async () => {
    try {
      setIsStarting(true);
      setServerError('');
      setInputMode('live');
      setHistoryMeeting(null);
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

  const handleUploadMeeting = async () => {
    if (!selectedUploadFile) {
      setServerError('Please select an audio file to upload.');
      return;
    }

    try {
      setIsUploadingFile(true);
      setServerError('');
      setHistoryMeeting(null);
      setActiveTab('transcript');

      const formData = new FormData();
      formData.append('file', selectedUploadFile);
      formData.append('scene', currentScene);
      formData.append('target_lang', currentLanguage);
      formData.append('provider', currentProvider);

      const response = await fetch(`${buildApiBaseUrl()}/api/meetings/upload`, {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) {
        let detail = `Failed to upload meeting audio (${response.status})`;
        try {
          const payload = await response.json() as { detail?: string };
          if (payload.detail) {
            detail = payload.detail;
          }
        } catch {
          // ignore response parse failures
        }
        throw new Error(detail);
      }

      const payload = await response.json() as MeetingRecord;
      setActiveUploadMeeting(payload);
      updateHistoryFromMeeting(payload);
      setSelectedUploadFile(null);
      setUploadInputKey((prev) => prev + 1);
    } catch (error) {
      setServerError(error instanceof Error ? error.message : 'Failed to upload meeting audio');
    } finally {
      setIsUploadingFile(false);
    }
  };

  const handleSelectHistoryMeeting = async (meetingId: string) => {
    try {
      setLoadingMeetingId(meetingId);
      setServerError('');
      const payload = await refreshMeetingDetail(meetingId);
      setHistoryMeeting(payload);
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

      if (historyMeeting?.meeting_id === meetingId) {
        setHistoryMeeting(null);
      }

      if (activeUploadMeeting?.meeting_id === meetingId) {
        setActiveUploadMeeting(null);
      }

      if (currentMeetingId === meetingId) {
        resetLiveSessionState();
        setStatusMessage('Ready to start meeting');
        setActiveTab('transcript');
      }
    } catch (error) {
      setServerError(error instanceof Error ? error.message : 'Failed to delete meeting record');
    } finally {
      setDeletingMeetingId(null);
    }
  };

  const handleActionItemStatusChange = async (
    actionItemIndex: number,
    status: ActionItemStatus
  ) => {
    const meetingId = displayedMeeting?.meeting_id ?? currentMeetingId;
    if (!meetingId) {
      return;
    }

    const response = await fetch(`${buildApiBaseUrl()}/api/meetings/${meetingId}/action-items/${actionItemIndex}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ status }),
    });

    if (!response.ok) {
      let detail = `Failed to update action item status (${response.status})`;
      try {
        const payload = await response.json() as { detail?: string };
        if (payload.detail) {
          detail = payload.detail;
        }
      } catch {
        // ignore response parse failures
      }
      throw new Error(detail);
    }

    const payload = await response.json() as MeetingRecord;
    updateHistoryFromMeeting(payload);

    if (historyMeeting?.meeting_id === payload.meeting_id) {
      setHistoryMeeting(payload);
    }

    if (activeUploadMeeting?.meeting_id === payload.meeting_id) {
      setActiveUploadMeeting(payload);
    }

    if (currentMeetingId === payload.meeting_id) {
      setSummary(payload.summary);
    }
  };

  const handleRenameMeeting = async (meetingId: string, title: string) => {
    const response = await fetch(`${buildApiBaseUrl()}/api/meetings/${meetingId}/title`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ title }),
    });

    if (!response.ok) {
      let detail = `Failed to rename meeting (${response.status})`;
      try {
        const payload = await response.json() as { detail?: string };
        if (payload.detail) {
          detail = payload.detail;
        }
      } catch {
        // ignore response parse failures
      }
      throw new Error(detail);
    }

    const payload = await response.json() as MeetingRecord;
    updateHistoryFromMeeting(payload);

    if (historyMeeting?.meeting_id === payload.meeting_id) {
      setHistoryMeeting(payload);
    }

    if (activeUploadMeeting?.meeting_id === payload.meeting_id) {
      setActiveUploadMeeting(payload);
    }
  };

  const handleSummarySave = async (meetingId: string, nextSummary: MeetingSummaryUpdate) => {
    try {
      setIsSavingSummary(true);
      setServerError('');
      const response = await fetch(`${buildApiBaseUrl()}/api/meetings/${meetingId}/summary`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(nextSummary),
      });

      if (!response.ok) {
        let detail = `Failed to update meeting summary (${response.status})`;
        try {
          const payload = await response.json() as { detail?: string };
          if (payload.detail) {
            detail = payload.detail;
          }
        } catch {
          // ignore response parse failures
        }
        throw new Error(detail);
      }

      const payload = await response.json() as MeetingRecord;
      updateHistoryFromMeeting(payload);

      if (historyMeeting?.meeting_id === payload.meeting_id) {
        setHistoryMeeting(payload);
      }

      if (activeUploadMeeting?.meeting_id === payload.meeting_id) {
        setActiveUploadMeeting(payload);
      }

      if (currentMeetingId === payload.meeting_id) {
        setSummary(payload.summary);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to update meeting summary';
      setServerError(message);
      throw error;
    } finally {
      setIsSavingSummary(false);
    }
  };

  const displayedMeeting = historyMeeting ?? (inputMode === 'upload' ? activeUploadMeeting : null);
  const isHistoryView = historyMeeting !== null;
  const isUploadCurrentView = !isHistoryView && inputMode === 'upload';
  const displayedTranscripts = displayedMeeting
    ? decorateTranscriptsWithAnalysis(
        displayedMeeting.transcripts.map((item) =>
          toDisplayTranscript(item, isHistoryView ? 'history' : 'upload')
        ),
        displayedMeeting.analysis
      )
    : transcripts;
  const displayedSummary = displayedMeeting?.summary ?? (displayedMeeting ? null : summary);
  const displayedAnalysis = displayedMeeting?.analysis ?? (displayedMeeting ? null : analysis);
  const displayedLanguage = displayedMeeting?.target_lang ?? currentLanguage;
  const displayedMeetingDate = displayedMeeting?.created_at ?? null;
  const canOpenHistory = !isRecording && !isStarting && !isFinalizing;
  const canSwitchInputMode = !isRecording && !isStarting && !isFinalizing;
  const selectedMeetingId = historyMeeting?.meeting_id
    ?? (inputMode === 'upload' ? activeUploadMeeting?.meeting_id ?? null : currentMeetingId);
  const summaryMeetingId = displayedMeeting?.meeting_id ?? currentMeetingId;

  const displayStatusMessage = isHistoryView
    ? `Viewing saved ${sourceLabels[historyMeeting.source_type]} meeting record`
    : inputMode === 'upload'
      ? buildUploadStatusMessage(activeUploadMeeting, isUploadingFile)
      : statusMessage;

  const tabs = [
    { id: 'transcript', label: 'Transcript' },
    { id: 'summary', label: 'Summary' },
    { id: 'actions', label: 'Action Items' },
    { id: 'analysis', label: 'Analysis' }
  ];

  return (
    <div className="size-full bg-gray-50 flex flex-col">
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-start justify-between gap-6">
          <div>
            <div className="inline-flex rounded-xl bg-gray-100 p-1 mb-3">
              <button
                type="button"
                onClick={() => handleInputModeChange('live')}
                disabled={!canSwitchInputMode}
                className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                  inputMode === 'live'
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                } ${!canSwitchInputMode ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                Live
              </button>
              <button
                type="button"
                onClick={() => handleInputModeChange('upload')}
                disabled={!canSwitchInputMode}
                className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                  inputMode === 'upload'
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                } ${!canSwitchInputMode ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                Upload
              </button>
            </div>

            <h1 className="text-gray-900 mb-1">Smart Meeting Assistant</h1>
            <p className="text-sm text-gray-500">
              {displayStatusMessage}
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

            {inputMode === 'live' ? (
              <>
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
              </>
            ) : (
              <UploadMeetingControls
                inputKey={uploadInputKey}
                selectedFileName={selectedUploadFile?.name ?? null}
                isUploading={isUploadingFile}
                disabled={isRecording || isStarting || isFinalizing}
                onFileChange={setSelectedUploadFile}
                onUpload={() => {
                  void handleUploadMeeting();
                }}
              />
            )}
          </div>
        </div>
      </div>

      <MeetingHistorySheet
        open={isHistorySheetOpen}
        onOpenChange={setIsHistorySheetOpen}
        meetings={historyList}
        isLoading={isHistoryLoading}
        selectedMeetingId={selectedMeetingId}
        loadingMeetingId={loadingMeetingId}
        deletingMeetingId={deletingMeetingId}
        onSelect={(meetingId) => {
          void handleSelectHistoryMeeting(meetingId);
        }}
        onDelete={(meetingId) => {
          void handleDeleteHistoryMeeting(meetingId);
        }}
        onRename={(meetingId, title) => handleRenameMeeting(meetingId, title)}
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
          {isHistoryView && historyMeeting && (
            <div className="max-w-7xl mx-auto rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-medium text-blue-900">
                  Viewing saved {sourceLabels[historyMeeting.source_type]} meeting
                </p>
                <p className="text-sm text-blue-700">
                  {historyMeeting.status} record from {formatHistoryTimestamp(historyMeeting.updated_at)}
                </p>
                {historyMeeting.processing_stage && (
                  <p className="text-xs text-blue-700 mt-1">{processingStageLabels[historyMeeting.processing_stage]}</p>
                )}
                {historyMeeting.error_message && (
                  <p className="text-xs text-red-600 mt-1">{historyMeeting.error_message}</p>
                )}
              </div>
              <button
                type="button"
                onClick={() => setHistoryMeeting(null)}
                className="inline-flex items-center gap-2 rounded-lg border border-blue-200 bg-white px-4 py-2 text-sm text-blue-700 transition-colors hover:bg-blue-100"
              >
                <RotateCcw className="w-4 h-4" />
                <span>Return to Current View</span>
              </button>
            </div>
          )}

          {isUploadCurrentView && activeUploadMeeting && (
            <div className={`max-w-7xl mx-auto rounded-xl border px-4 py-3 ${
              activeUploadMeeting.status === 'failed'
                ? 'border-red-200 bg-red-50'
                : activeUploadMeeting.status === 'processing'
                  ? 'border-blue-200 bg-blue-50'
                  : 'border-green-200 bg-green-50'
            }`}>
              <p className={`text-sm font-medium ${
                activeUploadMeeting.status === 'failed'
                  ? 'text-red-900'
                  : activeUploadMeeting.status === 'processing'
                    ? 'text-blue-900'
                    : 'text-green-900'
              }`}>
                {activeUploadMeeting.status === 'processing'
                  ? 'Processing uploaded meeting'
                  : activeUploadMeeting.status === 'failed'
                    ? 'Uploaded meeting failed'
                    : 'Uploaded meeting ready'}
              </p>
              <p className={`text-sm mt-1 ${
                activeUploadMeeting.status === 'failed'
                  ? 'text-red-700'
                  : activeUploadMeeting.status === 'processing'
                    ? 'text-blue-700'
                    : 'text-green-700'
              }`}>
                {activeUploadMeeting.source_name
                  ? `File: ${activeUploadMeeting.source_name}`
                  : 'Uploaded meeting record'}
              </p>
              {activeUploadMeeting.processing_stage && (
                <p className="text-xs text-blue-700 mt-1">{processingStageLabels[activeUploadMeeting.processing_stage]}</p>
              )}
              {activeUploadMeeting.error_message && (
                <p className="text-xs text-red-600 mt-1">{activeUploadMeeting.error_message}</p>
              )}
            </div>
          )}

          {activeTab === 'transcript' && (
            <TranscriptPanel
              isRecording={isRecording && !isHistoryView && inputMode === 'live'}
              currentLanguage={displayedLanguage}
              transcripts={displayedTranscripts}
              title={
                isHistoryView
                  ? 'Meeting Transcript'
                  : isUploadCurrentView
                    ? 'Uploaded Transcript'
                    : 'Live Transcript'
              }
              description={
                isHistoryView
                  ? 'Saved transcript, translations, and analysis highlights for this meeting.'
                  : isUploadCurrentView
                    ? 'Uploaded audio is processed into the same transcript, summary, action items, and analysis workflow.'
                    : undefined
              }
              emptyMessage={
                isHistoryView
                  ? 'No transcript captured for this meeting.'
                  : isUploadCurrentView
                    ? activeUploadMeeting
                      ? 'Transcript will appear here as soon as transcription completes.'
                      : 'Choose a meeting audio file and click "Process Upload".'
                    : undefined
              }
              showLiveBadge={inputMode === 'live' && !isHistoryView}
            />
          )}
          {activeTab === 'summary' && (
            <SummaryPanel
              summary={displayedSummary}
              transcripts={displayedTranscripts}
              meetingDate={displayedMeetingDate}
              meetingId={summaryMeetingId}
              isSaving={isSavingSummary}
              onSaveSummary={(meetingId, nextSummary) => handleSummarySave(meetingId, nextSummary)}
              onSaveError={setServerError}
            />
          )}
          {activeTab === 'actions' && (
            <ActionItemsPanel
              summary={displayedSummary}
              transcripts={displayedTranscripts}
              onStatusChange={handleActionItemStatusChange}
              onStatusChangeError={setServerError}
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
