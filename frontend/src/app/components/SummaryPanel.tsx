import { FileText, Users, Target, TrendingUp } from 'lucide-react';
import type { MeetingSummary, TranscriptItem } from '../../types';

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

const getParticipants = (transcripts: TranscriptItem[] = []) => {
  const participants = Array.from(
    new Set(
      transcripts
        .map((item) => item.speaker?.trim())
        .filter((speaker): speaker is string => Boolean(speaker))
    )
  );

  return participants.length > 0 ? participants : ['Participants unavailable'];
};

const buildOverview = (summary: MeetingSummary, participantCount: number) => {
  const counts = [
    `${summary.todos?.length ?? 0} action item${summary.todos?.length === 1 ? '' : 's'}`,
    `${summary.decisions?.length ?? 0} decision${summary.decisions?.length === 1 ? '' : 's'}`,
    `${summary.risks?.length ?? 0} risk${summary.risks?.length === 1 ? '' : 's'}`
  ];

  const participantText =
    participantCount > 0 && participantCount !== 1
      ? ` across ${participantCount} participants`
      : participantCount === 1
        ? ' from 1 participant'
        : '';

  return `Meeting summary generated with ${counts.join(', ')}${participantText}. Review the key topics, confirmed decisions, and participant context below.`;
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

  const participants = getParticipants(transcripts);
  const participantCount = participants[0] === 'Participants unavailable' ? 0 : participants.length;
  const keyTopics = [
    ...(summary.todos ?? []),
    ...(summary.risks ?? []).map((risk) => `Risk / blocker: ${risk}`)
  ];
  const decisions = summary.decisions ?? [];
  const displayedKeyTopics = keyTopics.length ? keyTopics : ['No key topics extracted.'];
  const displayedDecisions = decisions.length ? decisions : ['No decisions extracted.'];

  if (!keyTopics.length && !decisions.length) {
    return (
      <div className="max-w-5xl mx-auto flex items-center justify-center py-20 text-gray-500">
        <p>No actionable summary items were extracted from this meeting.</p>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Meeting Overview Card */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-start gap-3 mb-4">
          <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
            <FileText className="w-5 h-5 text-blue-600" />
          </div>
          <div className="flex-1">
            <h2 className="text-gray-900 mb-2">Meeting Overview</h2>
            <p className="text-sm text-gray-600 leading-relaxed">
              {buildOverview(summary, participantCount)}
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

      {/* Key Topics */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
            <TrendingUp className="w-5 h-5 text-purple-600" />
          </div>
          <h2 className="text-gray-900">Key Topics Discussed</h2>
        </div>

        <div className="space-y-2">
          {displayedKeyTopics.map((topic, index) => (
            <div key={index} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg border border-gray-100">
              <div className="w-6 h-6 bg-purple-100 text-purple-600 rounded-full flex items-center justify-center flex-shrink-0 text-xs">
                {index + 1}
              </div>
              <p className="text-sm text-gray-700 flex-1">{topic}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Decisions Made */}
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

      {/* Participants */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 bg-orange-100 rounded-lg flex items-center justify-center">
            <Users className="w-5 h-5 text-orange-600" />
          </div>
          <h2 className="text-gray-900">Participants</h2>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {participants.map((participant, index) => (
            <div key={index} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg border border-gray-100">
              <div className="w-8 h-8 bg-orange-100 text-orange-600 rounded-full flex items-center justify-center text-xs">
                {participant.charAt(0)}
              </div>
              <span className="text-sm text-gray-700">{participant}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
