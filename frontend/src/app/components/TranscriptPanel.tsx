import { User, Clock, Mic } from 'lucide-react';
import type { TranslationTargetLanguage } from '../../types';

interface DisplayTranscriptItem {
  id: string; // for React key
  speaker: string;
  text: string;
  start: number;
  end: number;
  translatedText?: string;
  translatedTargetLang?: TranslationTargetLanguage;
  analysisSignal?: string;
  analysisReason?: string;
  analysisSeverity?: 'low' | 'medium' | 'high';
}

interface TranscriptPanelProps {
  isRecording: boolean;
  currentLanguage: string;
  transcripts: DisplayTranscriptItem[];
}

const formatTime = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
};

const speakerColorCache: Record<string, string> = {
  'Speaker 0': 'bg-blue-100 text-blue-700 border-blue-200',
  'Speaker 1': 'bg-green-100 text-green-700 border-green-200',
  'Speaker 2': 'bg-purple-100 text-purple-700 border-purple-200',
  'Speaker 3': 'bg-orange-100 text-orange-700 border-orange-200'
};

const defaultColors = [
  'bg-blue-100 text-blue-700 border-blue-200',
  'bg-green-100 text-green-700 border-green-200',
  'bg-purple-100 text-purple-700 border-purple-200',
  'bg-orange-100 text-orange-700 border-orange-200',
  'bg-pink-100 text-pink-700 border-pink-200',
  'bg-teal-100 text-teal-700 border-teal-200'
];

let speakerCount = 0;

const getSpeakerColor = (speaker: string) => {
  if (!speakerColorCache[speaker]) {
    speakerColorCache[speaker] = defaultColors[speakerCount % defaultColors.length];
    speakerCount++;
  }
  return speakerColorCache[speaker];
};

export function TranscriptPanel({ isRecording, currentLanguage, transcripts }: TranscriptPanelProps) {
  const showTranslation = currentLanguage !== 'en';
  
  // Calculate unique speakers for stats
  const safeTranscripts = transcripts || [];
  const uniqueSpeakers = new Set(safeTranscripts.map(t => t.speaker)).size;

  return (
    <div className="bg-white rounded-lg border border-gray-200">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-gray-900">Live Transcript</h2>
            <p className="text-sm text-gray-500 mt-1">
              Real-time speech-to-text with speaker identification
            </p>
          </div>
          <div className="flex items-center gap-2">
            {isRecording && (
              <div className="flex items-center gap-2 text-red-600">
                <div className="w-2 h-2 bg-red-600 rounded-full animate-pulse" />
                <span className="text-sm">Live</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Transcript Content */}
      <div className="p-6 space-y-4 max-h-[600px] overflow-y-auto">
        {safeTranscripts.map((entry) => (
          <div key={entry.id} className="flex gap-4">
            {/* Speaker Avatar */}
            <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 border ${getSpeakerColor(entry.speaker)}`}>
              <User className="w-5 h-5" />
            </div>

            {/* Message Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm text-gray-900">{entry.speaker}</span>
                <span className="text-xs text-gray-400 flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {formatTime(entry.start)}
                </span>
                {entry.analysisSignal && (
                  <span className={`text-xs px-2 py-0.5 rounded border ${
                    entry.analysisSignal === 'disagreement' || entry.analysisSignal === 'tension'
                      ? 'bg-red-50 text-red-600 border-red-200' 
                      : entry.analysisSignal === 'agreement'
                      ? 'bg-green-50 text-green-600 border-green-200'
                      : 'bg-yellow-50 text-yellow-600 border-yellow-200'
                  }`}>
                    {entry.analysisSignal}
                  </span>
                )}
              </div>

              <div className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                <p className="text-sm text-gray-700 leading-relaxed">{entry.text}</p>

                {showTranslation && entry.translatedText && (
                  <div className="mt-2 pt-2 border-t border-gray-200">
                    <p className="text-xs text-gray-500 mb-1">Translation ({entry.translatedTargetLang?.toUpperCase() || currentLanguage.toUpperCase()}):</p>
                    <p className="text-sm text-gray-600 italic leading-relaxed">{entry.translatedText}</p>
                  </div>
                )}
                
                {entry.analysisReason && (
                   <div className="mt-2 pt-2 border-t border-gray-200">
                     <p className="text-xs text-gray-500 mb-1">AI Reason:</p>
                     <p className="text-xs text-indigo-600 italic leading-relaxed">{entry.analysisReason}</p>
                   </div>
                )}
              </div>
            </div>
          </div>
        ))}

        {!isRecording && safeTranscripts.length === 0 && (
          <div className="text-center py-12">
            <Mic className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500">Click "Start Recording" to begin transcription</p>
          </div>
        )}
      </div>

      {/* Footer Stats */}
      <div className="px-6 py-3 border-t border-gray-200 bg-gray-50 rounded-b-lg">
        <div className="flex items-center justify-between text-sm text-gray-600">
          <span>{safeTranscripts.length} messages transcribed</span>
          <span>{uniqueSpeakers} speakers identified</span>
        </div>
      </div>
    </div>
  );
}
