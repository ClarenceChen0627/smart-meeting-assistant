import { CheckCircle2, FileText, Target, TrendingUp } from 'lucide-react';
import type { ActionItem, MeetingSummary, TranscriptItem } from '../../types';

interface SummaryPanelProps {
  summary: MeetingSummary | null;
  transcripts?: TranscriptItem[];
}

const formatDuration = (transcripts: TranscriptItem[] = []) => {
  if (!transcripts.length) {
    return 'Not available';
  }

  const start = transcripts[0]?.start ?? 0;
  const end = transcripts.reduce((latest, item) => Math.max(latest, item.end ?? item.start ?? 0), start);
  const totalSeconds = Math.max(0, Math.round(end - start));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (minutes === 0) {
    return `${seconds} seconds`;
  }

  return seconds > 0 ? `${minutes} min ${seconds} sec` : `${minutes} minutes`;
};

const formatSessionDate = () => {
  return new Intl.DateTimeFormat('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric'
  }).format(new Date());
};

const formatTranscriptReference = (item: ActionItem, transcripts: TranscriptItem[]) => {
  if (item.transcript_index == null) {
    return 'Summary';
  }

  const transcript = transcripts[item.transcript_index];
  if (!transcript) {
    return `#${item.transcript_index + 1}`;
  }

  const minutes = Math.floor(transcript.start / 60);
  const seconds = Math.floor(transcript.start % 60);
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
};

export function SummaryPanel({ summary, transcripts = [] }: SummaryPanelProps) {
  if (!summary) {
    return (
      <div className="max-w-5xl mx-auto flex items-center justify-center py-20 text-gray-500">
        <div className="text-center">
          <FileText className="w-12 h-12 text-gray-300 mx-auto mb-3" />
          <p>Meeting summary will appear here after the session is finalized.</p>
        </div>
      </div>
    );
  }

  const displayedActionItems = summary.action_items.filter((item) => item.is_actionable);
  const hasMeaningfulSummary =
    Boolean(summary.overview.trim()) ||
    summary.key_topics.length > 0 ||
    summary.decisions.length > 0 ||
    displayedActionItems.length > 0;

  if (!hasMeaningfulSummary) {
    return (
      <div className="max-w-5xl mx-auto flex items-center justify-center py-20 text-gray-500">
        <p>No concise meeting summary was generated for this session.</p>
      </div>
    );
  }

  const displayedOverview = summary.overview.trim() || 'No meeting overview was generated for this session.';
  const displayedTopics = summary.key_topics.length ? summary.key_topics : ['No key topics extracted.'];
  const displayedDecisions = summary.decisions.length ? summary.decisions : ['No decisions extracted.'];

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-start gap-3 mb-4">
          <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
            <FileText className="w-5 h-5 text-blue-600" />
          </div>
          <div className="flex-1">
            <h2 className="text-gray-900 mb-2">Meeting Overview</h2>
            <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-line">
              {displayedOverview}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 mt-4 pt-4 border-t border-gray-100">
          <div>
            <p className="text-xs text-gray-500 mb-1">Date</p>
            <p className="text-sm text-gray-900">{formatSessionDate()}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-1">Duration</p>
            <p className="text-sm text-gray-900">{formatDuration(transcripts)}</p>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
            <TrendingUp className="w-5 h-5 text-purple-600" />
          </div>
          <h2 className="text-gray-900">Key Topics</h2>
        </div>

        <div className="space-y-2">
          {displayedTopics.map((topic, index) => (
            <div key={index} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg border border-gray-100">
              <div className="w-6 h-6 bg-purple-100 text-purple-600 rounded-full flex items-center justify-center flex-shrink-0 text-xs">
                {index + 1}
              </div>
              <p className="text-sm text-gray-700 flex-1">{topic}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
            <Target className="w-5 h-5 text-green-600" />
          </div>
          <h2 className="text-gray-900">Decisions Made</h2>
        </div>

        <div className="space-y-2">
          {displayedDecisions.map((decision, index) => (
            <div key={index} className="flex items-start gap-3 p-3 bg-green-50 rounded-lg border border-green-100">
              <div className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5">
                <svg className="w-full h-full" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <p className="text-sm text-gray-700 flex-1">{decision}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 bg-amber-100 rounded-lg flex items-center justify-center">
            <CheckCircle2 className="w-5 h-5 text-amber-600" />
          </div>
          <h2 className="text-gray-900">Follow-up Actions</h2>
        </div>

        {displayedActionItems.length > 0 ? (
          <div className="space-y-3">
            {displayedActionItems.map((item, index) => (
              <div key={index} className="p-4 rounded-lg border border-amber-100 bg-amber-50">
                <div className="flex items-start justify-between gap-4">
                  <p className="text-sm text-gray-900 flex-1">{item.task}</p>
                  <span className="px-2 py-1 rounded text-xs bg-white text-amber-700 border border-amber-200">
                    {item.status}
                  </span>
                </div>

                <div className="flex flex-wrap gap-2 mt-3 text-xs text-gray-500">
                  <span className="px-2 py-1 rounded-full bg-white border border-gray-200">
                    Owner: {item.assignee}
                  </span>
                  <span className="px-2 py-1 rounded-full bg-white border border-gray-200">
                    Deadline: {item.deadline}
                  </span>
                  <span className="px-2 py-1 rounded-full bg-white border border-gray-200">
                    Source: {formatTranscriptReference(item, transcripts)}
                  </span>
                  <span className="px-2 py-1 rounded-full bg-white border border-gray-200">
                    Confidence: {Math.round(item.confidence * 100)}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-4 rounded-lg border border-dashed border-gray-200 bg-gray-50 text-sm text-gray-500">
            No follow-up actions extracted.
          </div>
        )}
      </div>
    </div>
  );
}
