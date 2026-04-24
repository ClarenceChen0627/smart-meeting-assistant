import { useState } from 'react';
import { Play, Pause, Mic, MicOff, AlertCircle } from 'lucide-react';
import { TranscriptPanel } from './components/TranscriptPanel';
import { SummaryPanel } from './components/SummaryPanel';
import { ActionItemsPanel } from './components/ActionItemsPanel';
import { MeetingAnalysisPanel } from './components/MeetingAnalysisPanel';
import { ASRProviderControls } from './components/ASRProviderControls';
import { TranslationControls } from './components/TranslationControls';
import { SceneControls } from './components/SceneControls';
import { useWebSocket } from '../hooks/useWebSocket';
import { useAudioRecording } from '../hooks/useAudioRecording';
import type { ASRProvider, TranscriptItem, MeetingAnalysis, MeetingSummary, TranslationTargetLanguage } from '../types';

interface DisplayTranscriptItem extends TranscriptItem {
  id: string; // for React key
  translatedText?: string;
  translatedTargetLang?: TranslationTargetLanguage;
  analysisSignal?: string;
  analysisReason?: string;
  analysisSeverity?: 'low' | 'medium' | 'high';
}

export default function App() {
  const [activeTab, setActiveTab] = useState<'transcript' | 'summary' | 'actions' | 'analysis'>('transcript');
  const [currentScene, setCurrentScene] = useState<string>('general');
  const [isRecording, setIsRecording] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [isFinalizing, setIsFinalizing] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [currentLanguage, setCurrentLanguage] = useState<TranslationTargetLanguage>('en');
  const [currentProvider, setCurrentProvider] = useState<ASRProvider>('volcengine');

  // Meeting State
  const [transcripts, setTranscripts] = useState<DisplayTranscriptItem[]>([]);
  const [analysis, setAnalysis] = useState<MeetingAnalysis | null>(null);
  const [summary, setSummary] = useState<MeetingSummary | null>(null);

  const [statusMessage, setStatusMessage] = useState('Ready to start meeting');
  const [serverError, setServerError] = useState('');

  const { connect, disconnect, finalize, sendAudio, isConnected } = useWebSocket({
    onTranscript: (data) => {
      setTranscripts((prev) => [...prev, { ...data, id: Math.random().toString() }]);
    },
    onTranscriptUpdate: (data) => {
      setTranscripts((prev) => {
        const next = [...prev];
        const item = next[data.transcript_index];
        if (item) {
          item.text = data.text;
          item.start = data.start;
          item.end = data.end;
          item.speaker = data.speaker;
          item.speaker_is_final = data.speaker_is_final;
          item.transcript_is_final = data.transcript_is_final;
        }
        return next;
      });
    },
    onSpeakerUpdate: (data) => {
      setTranscripts((prev) => {
        const next = [...prev];
        const item = next[data.transcript_index];
        if (item) {
          item.speaker = data.speaker;
          item.speaker_is_final = data.speaker_is_final;
        }
        return next;
      });
    },
    onTranslation: (data) => {
      setTranscripts((prev) => {
        const next = [...prev];
        const item = next[data.transcript_index];
        if (item) {
          item.translatedText = data.text;
          item.translatedTargetLang = data.target_lang;
        }
        return next;
      });
    },
    onAnalysis: (data) => {
      setAnalysis(data);
      setTranscripts((prev) => {
        const next = [...prev];
        // Clear previous highlights
        next.forEach((item) => {
          item.analysisSignal = undefined;
          item.analysisReason = undefined;
          item.analysisSeverity = undefined;
        });
        // Apply new highlights
        data.highlights.forEach((highlight) => {
          const transcript = next[highlight.transcript_index];
          if (transcript) {
            transcript.analysisSignal = highlight.signal;
            transcript.analysisReason = highlight.reason;
            transcript.analysisSeverity = highlight.severity;
          }
        });
        return next;
      });
    },
    onSummary: (data) => {
      setSummary(data);
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
      // you could append this to diagnostic logs
      console.log(status);
    },
    onError: (error) => {
      setServerError(error instanceof Error ? error.message : String(error));
    }
  });

  const buildWebSocketUrl = (scene: string, targetLang: string, provider: ASRProvider) => {
    // Modify based on your backend config. Assuming Vite proxy or localhost:8080 fallback.
    const baseUrl = import.meta.env.VITE_WS_BASE_URL?.trim() || `ws://localhost:8080`;
    const normalizedBaseUrl = baseUrl.replace(/\/+$/, '');
    return `${normalizedBaseUrl}/ws/meeting?scene=${scene}&target_lang=${targetLang}&provider=${provider}`;
  };

  const handleStartRecording = async () => {
    try {
      const wsUrl = buildWebSocketUrl(currentScene, currentLanguage, currentProvider);
      setIsStarting(true);
      setServerError('');
      setTranscripts([]);
      setAnalysis(null);
      setSummary(null);

      await connect(wsUrl);
      await startAudio();
      
      setIsRecording(true);
      setIsFinalizing(false);
    } catch (e) {
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
    } catch (e) {
      setServerError('Failed to finalize session');
    } finally {
      setIsFinalizing(false);
      disconnect();
      setStatusMessage('Session finalized.');
    }
  };

  const toggleRecording = () => {
    if (isStarting || isFinalizing) return;
    if (isRecording) {
      handleStopRecording();
    } else {
      handleStartRecording();
    }
  };

  const tabs = [
    { id: 'transcript', label: 'Live Transcript' },
    { id: 'summary', label: 'Summary' },
    { id: 'actions', label: 'Action Items' },
    { id: 'analysis', label: 'Analysis' }
  ];

  return (
    <div className="size-full bg-gray-50 flex flex-col">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between">
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

          {/* Recording Controls */}
          <div className="flex items-center gap-3">
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

      {/* Navigation Tabs */}
      <div className="bg-white border-b border-gray-200 px-6">
        <div className="flex gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
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

      {/* Main Content Area */}
      <div className="flex-1 overflow-auto">
        <div className="p-6">
          {activeTab === 'transcript' && (
            <TranscriptPanel 
              isRecording={isRecording} 
              currentLanguage={currentLanguage} 
              transcripts={transcripts}
            />
          )}
          {activeTab === 'summary' && <SummaryPanel summary={summary} transcripts={transcripts} />}
          {activeTab === 'actions' && <ActionItemsPanel summary={summary} />}
          {activeTab === 'analysis' && <MeetingAnalysisPanel analysis={analysis} transcripts={transcripts} />}
        </div>
      </div>
    </div>
  );
}
