import { useEffect, useMemo, useState } from 'react';
import { Check, Clock, Mic, Pencil, User, X } from 'lucide-react';
import type { SpeakerLabelUpdate, TranslationTargetLanguage } from '../../types';

interface DisplayTranscriptItem {
  id: string; // for React key
  transcript_index: number;
  speaker: string;
  speaker_is_final: boolean;
  transcript_is_final: boolean;
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
  title?: string;
  description?: string;
  emptyMessage?: string;
  showLiveBadge?: boolean;
  canEditSpeakers?: boolean;
  isSavingSpeakers?: boolean;
  onSaveSpeakerUpdates?: (updates: SpeakerLabelUpdate[]) => Promise<void> | void;
  onSpeakerSaveError?: (message: string) => void;
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
  'Speaker 3': 'bg-orange-100 text-orange-700 border-orange-200',
  Unknown: 'bg-gray-100 text-gray-500 border-gray-200'
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

const normalizeSpeakerLabel = (value: string) => value.replace(/\s+/g, ' ').trim();

export function TranscriptPanel({
  isRecording,
  currentLanguage,
  transcripts,
  title = 'Live Transcript',
  description = 'Real-time speech-to-text with speaker identification',
  emptyMessage = 'Click "Start Recording" to begin transcription',
  showLiveBadge = true,
  canEditSpeakers = false,
  isSavingSpeakers = false,
  onSaveSpeakerUpdates,
  onSpeakerSaveError,
}: TranscriptPanelProps) {
  const [isEditingSpeakers, setIsEditingSpeakers] = useState(false);
  const [speakerDrafts, setSpeakerDrafts] = useState<Record<string, string>>({});
  const [speakerError, setSpeakerError] = useState<string | null>(null);
  // Always show translation if available, regardless of whether it is 'en'
  const showTranslation = true;
  
  // Calculate unique speakers for stats
  const safeTranscripts = transcripts || [];
  const finalSpeakerLabels = useMemo(
    () => Array.from(new Set(
      safeTranscripts
        .filter((t) => t.speaker_is_final && t.speaker !== 'Unknown')
        .map((t) => t.speaker)
    )).sort((left, right) => left.localeCompare(right)),
    [safeTranscripts]
  );
  const uniqueSpeakers = finalSpeakerLabels.length;
  const canShowSpeakerEditor = canEditSpeakers && finalSpeakerLabels.length > 0 && onSaveSpeakerUpdates;

  useEffect(() => {
    if (!isEditingSpeakers) {
      setSpeakerDrafts(Object.fromEntries(finalSpeakerLabels.map((speaker) => [speaker, speaker])));
      setSpeakerError(null);
    }
  }, [finalSpeakerLabels, isEditingSpeakers]);

  const startSpeakerEditing = () => {
    setSpeakerDrafts(Object.fromEntries(finalSpeakerLabels.map((speaker) => [speaker, speaker])));
    setSpeakerError(null);
    setIsEditingSpeakers(true);
  };

  const cancelSpeakerEditing = () => {
    setSpeakerDrafts(Object.fromEntries(finalSpeakerLabels.map((speaker) => [speaker, speaker])));
    setSpeakerError(null);
    setIsEditingSpeakers(false);
  };

  const saveSpeakerUpdates = async () => {
    if (!onSaveSpeakerUpdates) {
      return;
    }
    const updates = finalSpeakerLabels
      .map((speaker) => ({
        from: speaker,
        to: normalizeSpeakerLabel(speakerDrafts[speaker] ?? speaker),
      }))
      .filter((update) => update.from !== update.to);

    if (updates.some((update) => !update.to)) {
      setSpeakerError('Speaker names cannot be empty.');
      return;
    }
    if (updates.length === 0) {
      setIsEditingSpeakers(false);
      setSpeakerError(null);
      return;
    }

    try {
      setSpeakerError(null);
      await onSaveSpeakerUpdates(updates);
      setIsEditingSpeakers(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to update speakers.';
      setSpeakerError(message);
      onSpeakerSaveError?.(message);
    }
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-gray-900">{title}</h2>
            <p className="text-sm text-gray-500 mt-1">
              {description}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {canShowSpeakerEditor && !isEditingSpeakers && (
              <button
                type="button"
                onClick={startSpeakerEditing}
                className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50"
              >
                <Pencil className="h-4 w-4" />
                <span>Edit speakers</span>
              </button>
            )}
            {showLiveBadge && isRecording && (
              <div className="flex items-center gap-2 text-red-600">
                <div className="w-2 h-2 bg-red-600 rounded-full animate-pulse" />
                <span className="text-sm">Live</span>
              </div>
            )}
          </div>
        </div>
        {isEditingSpeakers && (
          <div className="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-3">
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {finalSpeakerLabels.map((speaker) => (
                <label key={speaker} className="block text-xs text-gray-500">
                  <span className="mb-1 block truncate">{speaker}</span>
                  <input
                    value={speakerDrafts[speaker] ?? speaker}
                    disabled={isSavingSpeakers}
                    onChange={(event) => {
                      setSpeakerDrafts((drafts) => ({
                        ...drafts,
                        [speaker]: event.target.value,
                      }));
                    }}
                    className="h-9 w-full rounded-md border border-gray-200 bg-white px-3 text-sm text-gray-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100 disabled:cursor-not-allowed disabled:opacity-50"
                    aria-label={`Speaker label for ${speaker}`}
                  />
                </label>
              ))}
            </div>
            {speakerError && (
              <p className="mt-2 text-xs text-red-600">{speakerError}</p>
            )}
            <div className="mt-3 flex justify-end gap-2">
              <button
                type="button"
                onClick={cancelSpeakerEditing}
                disabled={isSavingSpeakers}
                className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <X className="h-4 w-4" />
                <span>Cancel</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  void saveSpeakerUpdates();
                }}
                disabled={isSavingSpeakers}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Check className="h-4 w-4" />
                <span>{isSavingSpeakers ? 'Saving...' : 'Save speakers'}</span>
              </button>
            </div>
          </div>
        )}
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
                <span className={`text-sm ${entry.speaker_is_final ? 'text-gray-900' : 'text-gray-500'}`}>
                  {entry.speaker}
                </span>
                {!entry.speaker_is_final && (
                  <span className="text-xs px-2 py-0.5 rounded border bg-gray-50 text-gray-500 border-gray-200">
                    Identifying...
                  </span>
                )}
                {!entry.transcript_is_final && (
                  <span className="text-xs px-2 py-0.5 rounded border bg-blue-50 text-blue-600 border-blue-200">
                    Listening...
                  </span>
                )}
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
                <p className={`text-sm leading-relaxed ${entry.transcript_is_final ? 'text-gray-700' : 'text-gray-500 italic'}`}>
                  {entry.text}
                </p>

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
            <p className="text-gray-500">{emptyMessage}</p>
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
