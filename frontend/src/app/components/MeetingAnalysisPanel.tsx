import { useMemo } from 'react';
import { LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { TrendingUp, AlertCircle, Smile, Meh, Frown, Clock, MessageSquare, Users } from 'lucide-react';
import type { MeetingAnalysis, MeetingSignalCounts, MeetingSignalType, ParticipantAnalysis } from '../../types';

interface DisplayTranscriptItem {
  speaker: string;
  text: string;
  start: number;
  end?: number;
}

interface MeetingAnalysisPanelProps {
  analysis: MeetingAnalysis | null;
  transcripts: DisplayTranscriptItem[];
}

type SentimentBucket = 'positive' | 'neutral' | 'negative';

const emotionColors: Record<MeetingSignalType, string> = {
  agreement: 'bg-green-100 text-green-700 border-green-200',
  disagreement: 'bg-red-100 text-red-700 border-red-200',
  hesitation: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  tension: 'bg-orange-100 text-orange-700 border-orange-200'
};

const emotionLabels: Record<MeetingSignalType, string> = {
  agreement: 'Agreement',
  disagreement: 'Concern',
  hesitation: 'Hesitation',
  tension: 'Tension'
};

const signalOrder: MeetingSignalType[] = ['agreement', 'disagreement', 'hesitation', 'tension'];

const sentimentColors = {
  positive: '#10b981',
  neutral: '#6b7280',
  negative: '#ef4444'
};

const sentimentBadgeColors: Record<ParticipantAnalysis['sentiment'], string> = {
  positive: 'bg-green-100 text-green-700 border-green-200',
  neutral: 'bg-gray-100 text-gray-700 border-gray-200',
  negative: 'bg-red-100 text-red-700 border-red-200',
  mixed: 'bg-orange-100 text-orange-700 border-orange-200'
};

const engagementBadgeColors: Record<ParticipantAnalysis['engagement_level'], string> = {
  low: 'bg-gray-100 text-gray-700 border-gray-200',
  medium: 'bg-blue-100 text-blue-700 border-blue-200',
  high: 'bg-purple-100 text-purple-700 border-purple-200'
};

const emptySignalCounts: MeetingSignalCounts = {
  agreement: 0,
  disagreement: 0,
  tension: 0,
  hesitation: 0
};

const emptyTranscripts: DisplayTranscriptItem[] = [];

const signalToSentiment: Record<MeetingSignalType, SentimentBucket> = {
  agreement: 'positive',
  disagreement: 'negative',
  tension: 'negative',
  hesitation: 'neutral'
};

const sentimentFallbacks: Record<MeetingAnalysis['overall_sentiment'], Record<SentimentBucket, number>> = {
  positive: { positive: 68, neutral: 25, negative: 7 },
  neutral: { positive: 20, neutral: 70, negative: 10 },
  negative: { positive: 10, neutral: 25, negative: 65 },
  mixed: { positive: 40, neutral: 25, negative: 35 }
};

const engagementScores: Record<MeetingAnalysis['engagement_level'], number> = {
  low: 35,
  medium: 65,
  high: 85
};

const formatTime = (seconds: number): string => {
  if (!Number.isFinite(seconds)) {
    return 'Unknown time';
  }

  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
};

const formatDuration = (seconds: number): string => {
  if (!Number.isFinite(seconds)) {
    return '0s';
  }

  const totalSeconds = Math.max(0, Math.round(seconds));
  const mins = Math.floor(totalSeconds / 60);
  const secs = totalSeconds % 60;

  if (mins === 0) {
    return `${secs}s`;
  }

  if (secs === 0) {
    return `${mins}m`;
  }

  return `${mins}m ${secs}s`;
};

const capitalize = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);

const getSignalCounts = (analysis: MeetingAnalysis) => analysis.signal_counts ?? emptySignalCounts;

const getSignalTotal = (counts: MeetingSignalCounts) =>
  counts.agreement + counts.disagreement + counts.tension + counts.hesitation;

const formatSignalSummary = (counts: MeetingSignalCounts) => {
  const parts = signalOrder
    .filter((signal) => counts[signal] > 0)
    .map((signal) => `${counts[signal]} ${emotionLabels[signal].toLowerCase()}`);

  return parts.length ? parts.join(', ') : 'No interaction signals';
};

const getSentimentIcon = (sentiment: MeetingAnalysis['overall_sentiment']) => {
  if (sentiment === 'positive') {
    return <Smile className="w-5 h-5 text-green-600" />;
  }

  if (sentiment === 'negative') {
    return <Frown className="w-5 h-5 text-red-600" />;
  }

  if (sentiment === 'mixed') {
    return <AlertCircle className="w-5 h-5 text-orange-600" />;
  }

  return <Meh className="w-5 h-5 text-gray-600" />;
};

const deriveParticipantSentiment = (counts: MeetingSignalCounts): ParticipantAnalysis['sentiment'] => {
  const negativeSignals = counts.disagreement + counts.tension;
  if (negativeSignals && counts.agreement) {
    return 'mixed';
  }
  if (negativeSignals) {
    return 'negative';
  }
  if (counts.agreement) {
    return 'positive';
  }
  return 'neutral';
};

const deriveParticipantEngagement = (
  transcriptCount: number,
  signalTotal: number,
  maxTranscriptCount: number
): ParticipantAnalysis['engagement_level'] => {
  if (signalTotal >= 2 || transcriptCount >= Math.max(3, maxTranscriptCount)) {
    return 'high';
  }
  if (signalTotal >= 1 || transcriptCount > 0) {
    return 'medium';
  }
  return 'low';
};

const buildSentimentDistribution = (analysis: MeetingAnalysis) => {
  const counts = getSignalCounts(analysis);
  const raw = {
    positive: counts.agreement,
    neutral: counts.hesitation,
    negative: counts.disagreement + counts.tension
  };
  const total = raw.positive + raw.neutral + raw.negative;
  const values = total > 0
    ? {
        positive: Math.round((raw.positive / total) * 100),
        neutral: Math.round((raw.neutral / total) * 100),
        negative: Math.max(0, 100 - Math.round((raw.positive / total) * 100) - Math.round((raw.neutral / total) * 100))
      }
    : sentimentFallbacks[analysis.overall_sentiment];

  return [
    { name: 'Positive', value: values.positive, color: sentimentColors.positive },
    { name: 'Neutral', value: values.neutral, color: sentimentColors.neutral },
    { name: 'Negative', value: values.negative, color: sentimentColors.negative }
  ];
};

export const buildSentimentTrend = (analysis: MeetingAnalysis, transcripts: DisplayTranscriptItem[]) => {
  const highlights = [...analysis.highlights].sort((a, b) => {
    const aTime = transcripts[a.transcript_index]?.start ?? a.transcript_index;
    const bTime = transcripts[b.transcript_index]?.start ?? b.transcript_index;
    return aTime - bTime;
  });

  const fallback = sentimentFallbacks[analysis.overall_sentiment];
  if (!highlights.length) {
    return [
      { time: 'Start', positive: fallback.positive, neutral: fallback.neutral, negative: fallback.negative, overall: fallback.positive - fallback.negative },
      { time: 'End', positive: fallback.positive, neutral: fallback.neutral, negative: fallback.negative, overall: fallback.positive - fallback.negative }
    ];
  }

  const running = { positive: 0, neutral: 0, negative: 0 };
  const trend = [
    {
      time: 'Start',
      positive: fallback.positive,
      neutral: fallback.neutral,
      negative: fallback.negative,
      overall: fallback.positive - fallback.negative
    }
  ];

  highlights.forEach((highlight, index) => {
    const bucket = signalToSentiment[highlight.signal];
    running[bucket] += 1;

    const total = index + 1;
    const positive = Math.round((running.positive / total) * 100);
    const neutral = Math.round((running.neutral / total) * 100);
    const negative = Math.max(0, 100 - positive - neutral);
    const transcript = transcripts[highlight.transcript_index];

    trend.push({
      time: transcript ? formatTime(transcript.start) : `#${highlight.transcript_index + 1}`,
      positive,
      neutral,
      negative,
      overall: positive - negative
    });
  });

  const lastPoint = trend[trend.length - 1];
  trend.push({
    time: 'End',
    positive: lastPoint.positive,
    neutral: lastPoint.neutral,
    negative: lastPoint.negative,
    overall: lastPoint.overall
  });

  return trend;
};

interface ParticipantDetailRow {
  name: string;
  sentiment: ParticipantAnalysis['sentiment'];
  engagementLevel: ParticipantAnalysis['engagement_level'];
  engagementScore: number;
  transcriptCount: number;
  speakingTimeSeconds: number;
  signalCounts: MeetingSignalCounts;
  signalTotal: number;
  signalSummary: string;
  summary: string;
}

export const buildParticipantDetails = (
  analysis: MeetingAnalysis,
  transcripts: DisplayTranscriptItem[]
): ParticipantDetailRow[] => {
  if (analysis.participants?.length) {
    return analysis.participants.map((participant) => ({
      name: participant.speaker,
      sentiment: participant.sentiment,
      engagementLevel: participant.engagement_level,
      engagementScore: engagementScores[participant.engagement_level],
      transcriptCount: participant.transcript_count,
      speakingTimeSeconds: participant.speaking_time_seconds,
      signalCounts: participant.signal_counts,
      signalTotal: getSignalTotal(participant.signal_counts),
      signalSummary: formatSignalSummary(participant.signal_counts),
      summary: participant.engagement_summary
    }));
  }

  const speakerStats = new Map<string, {
    transcriptCount: number;
    speakingTimeSeconds: number;
    signalCounts: MeetingSignalCounts;
  }>();

  transcripts.forEach((transcript) => {
    const speaker = transcript.speaker || 'Unknown';
    const current = speakerStats.get(speaker) ?? {
      transcriptCount: 0,
      speakingTimeSeconds: 0,
      signalCounts: { ...emptySignalCounts }
    };
    current.transcriptCount += 1;
    if (typeof transcript.end === 'number') {
      current.speakingTimeSeconds += Math.max(0, transcript.end - transcript.start);
    }
    speakerStats.set(speaker, current);
  });

  analysis.highlights.forEach((highlight) => {
    const speaker = transcripts[highlight.transcript_index]?.speaker || 'Unknown';
    const current = speakerStats.get(speaker) ?? {
      transcriptCount: 0,
      speakingTimeSeconds: 0,
      signalCounts: { ...emptySignalCounts }
    };
    current.signalCounts[highlight.signal] += 1;
    speakerStats.set(speaker, current);
  });

  const maxTranscriptCount = Math.max(
    ...Array.from(speakerStats.values()).map((stats) => stats.transcriptCount),
    1
  );

  return Array.from(speakerStats.entries())
    .map(([name, stats]) => {
      const signalTotal = getSignalTotal(stats.signalCounts);
      const engagementLevel = deriveParticipantEngagement(
        stats.transcriptCount,
        signalTotal,
        maxTranscriptCount
      );
      return {
        name,
        sentiment: deriveParticipantSentiment(stats.signalCounts),
        engagementLevel,
        engagementScore: engagementScores[engagementLevel],
        transcriptCount: stats.transcriptCount,
        speakingTimeSeconds: Math.round(stats.speakingTimeSeconds * 100) / 100,
        signalCounts: stats.signalCounts,
        signalTotal,
        signalSummary: formatSignalSummary(stats.signalCounts),
        summary: signalTotal
          ? `${name} contributed ${stats.transcriptCount} utterances with ${signalTotal} interaction signals.`
          : `${name} contributed ${stats.transcriptCount} utterances with no explicit interaction signals.`
      };
    })
    .sort((left, right) => right.transcriptCount - left.transcriptCount || left.name.localeCompare(right.name));
};

const buildParticipantEngagement = (
  analysis: MeetingAnalysis,
  transcripts: DisplayTranscriptItem[],
  participantDetails = buildParticipantDetails(analysis, transcripts)
) => {
  if (participantDetails.length) {
    return participantDetails.map((participant) => ({
      name: participant.name,
      engagement: participant.engagementScore,
      contributions: participant.transcriptCount
    }));
  }

  const speakerStats = new Map<string, { contributions: number; signals: number }>();

  transcripts.forEach((transcript) => {
    const speaker = transcript.speaker || 'Unknown';
    const current = speakerStats.get(speaker) ?? { contributions: 0, signals: 0 };
    current.contributions += 1;
    speakerStats.set(speaker, current);
  });

  analysis.highlights.forEach((highlight) => {
    const speaker = transcripts[highlight.transcript_index]?.speaker || 'Unknown';
    const current = speakerStats.get(speaker) ?? { contributions: 0, signals: 0 };
    current.signals += 1;
    speakerStats.set(speaker, current);
  });

  if (!speakerStats.size) {
    return [
      {
        name: 'Overall',
        engagement: engagementScores[analysis.engagement_level],
        contributions: analysis.highlights.length
      }
    ];
  }

  const maxContributions = Math.max(...Array.from(speakerStats.values()).map((item) => item.contributions), 1);

  return Array.from(speakerStats.entries()).map(([name, stats]) => ({
    name,
    engagement: Math.min(
      100,
      Math.round(35 + (stats.contributions / maxContributions) * 45 + stats.signals * 8)
    ),
    contributions: stats.contributions
  }));
};

const buildEmotionalMoments = (
  analysis: MeetingAnalysis,
  transcripts: DisplayTranscriptItem[]
) => {
  return analysis.highlights.map((highlight) => {
    const transcript = transcripts[highlight.transcript_index];

    return {
      time: transcript ? formatTime(transcript.start) : `#${highlight.transcript_index + 1}`,
      speaker: transcript?.speaker || 'Unknown',
      emotion: emotionLabels[highlight.signal],
      text: transcript?.text || highlight.reason,
      type: highlight.signal,
      intensity: highlight.severity,
      reason: highlight.reason
    };
  });
};

const buildInsights = (analysis: MeetingAnalysis) => {
  const counts = getSignalCounts(analysis);
  const totalSignals = counts.agreement + counts.disagreement + counts.tension + counts.hesitation;
  const insights = [
    analysis.engagement_summary || `Meeting engagement is currently ${analysis.engagement_level}.`
  ];

  if (totalSignals > 0) {
    insights.push(
      `${totalSignals} interaction signal${totalSignals === 1 ? '' : 's'} detected across agreement, concern, hesitation, and tension.`
    );
  } else {
    insights.push('No strong interaction signals were detected in the available transcript.');
  }

  if (analysis.highlights.length > 0) {
    insights.push(`${analysis.highlights.length} emotionally significant point${analysis.highlights.length === 1 ? '' : 's'} should be reviewed in context.`);
  } else {
    insights.push('No emotionally significant moments were highlighted by the analysis service.');
  }

  return insights;
};

export function MeetingAnalysisPanel({ analysis, transcripts }: MeetingAnalysisPanelProps) {
  const safeTranscripts = transcripts ?? emptyTranscripts;
  const derivedAnalysis = useMemo(() => {
    if (!analysis) {
      return null;
    }

    const participantDetails = buildParticipantDetails(analysis, safeTranscripts);

    return {
      sentimentOverTime: buildSentimentTrend(analysis, safeTranscripts),
      overallSentiment: buildSentimentDistribution(analysis),
      participantDetails,
      engagementByParticipant: buildParticipantEngagement(analysis, safeTranscripts, participantDetails),
      emotionalMoments: buildEmotionalMoments(analysis, safeTranscripts),
      insights: buildInsights(analysis)
    };
  }, [analysis, safeTranscripts]);

  if (!analysis || !derivedAnalysis) {
    return (
      <div className="max-w-7xl mx-auto flex items-center justify-center py-20 text-gray-500">
        <p>Meeting analysis will appear here once the server processes the data.</p>
      </div>
    );
  }

  const {
    sentimentOverTime,
    overallSentiment,
    participantDetails,
    engagementByParticipant,
    emotionalMoments,
    insights
  } = derivedAnalysis;

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="bg-white rounded-lg border border-gray-200 p-4 sm:p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm text-gray-500">Overall Sentiment</h3>
            {getSentimentIcon(analysis.overall_sentiment)}
          </div>
          <p className="text-gray-900 mb-1">{capitalize(analysis.overall_sentiment)}</p>
          <p className="text-sm text-gray-600">
            {overallSentiment[0].value}% positive sentiment detected
          </p>
        </div>

        <div className="bg-white rounded-lg border border-gray-200 p-4 sm:p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm text-gray-500">Engagement Level</h3>
            <TrendingUp className="w-5 h-5 text-blue-600" />
          </div>
          <p className="text-gray-900 mb-1">{capitalize(analysis.engagement_level)}</p>
          <p className="text-sm text-gray-600">
            {analysis.engagement_summary || 'Participant engagement analyzed from meeting signals'}
          </p>
        </div>

        <div className="bg-white rounded-lg border border-gray-200 p-4 sm:p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm text-gray-500">Key Moments</h3>
            <AlertCircle className="w-5 h-5 text-orange-600" />
          </div>
          <p className="text-gray-900 mb-1">{emotionalMoments.length} Identified</p>
          <p className="text-sm text-gray-600">Emotionally significant points</p>
        </div>
      </div>

      {/* Sentiment Over Time Chart */}
      <div className="min-w-0 bg-white rounded-lg border border-gray-200 p-4 sm:p-6">
        <h2 className="text-gray-900 mb-4">Sentiment Trend Over Time</h2>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={sentimentOverTime}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="time" stroke="#6b7280" />
            <YAxis stroke="#6b7280" />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="positive" stroke="#10b981" strokeWidth={2} name="Positive" />
            <Line type="monotone" dataKey="neutral" stroke="#6b7280" strokeWidth={2} name="Neutral" />
            <Line type="monotone" dataKey="negative" stroke="#ef4444" strokeWidth={2} name="Negative" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        {/* Overall Sentiment Distribution */}
        <div className="min-w-0 bg-white rounded-lg border border-gray-200 p-4 sm:p-6">
          <h2 className="text-gray-900 mb-4">Overall Sentiment Distribution</h2>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={overallSentiment}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, value }) => `${name}: ${value}%`}
                outerRadius={80}
                fill="#8884d8"
                dataKey="value"
              >
                {overallSentiment.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Engagement by Participant */}
        <div className="min-w-0 bg-white rounded-lg border border-gray-200 p-4 sm:p-6">
          <h2 className="text-gray-900 mb-4">Participant Engagement</h2>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={engagementByParticipant}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="name" stroke="#6b7280" angle={-15} textAnchor="end" height={80} />
              <YAxis stroke="#6b7280" />
              <Tooltip />
              <Bar dataKey="engagement" fill="#3b82f6" name="Engagement %" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {participantDetails.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200">
          <div className="px-4 py-4 border-b border-gray-200 flex items-center justify-between gap-4 sm:px-6">
            <div className="min-w-0">
              <h2 className="text-gray-900">Participant Details</h2>
              <p className="text-sm text-gray-500 mt-1">Speaker-level sentiment, engagement, and interaction signals</p>
            </div>
            <Users className="w-5 h-5 text-blue-600 shrink-0" />
          </div>

          <div className="divide-y divide-gray-100">
            {participantDetails.map((participant) => (
              <div key={participant.name} className="p-4 sm:p-6">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0 space-y-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="min-w-0 break-words text-gray-900">{participant.name}</h3>
                      <span className={`rounded border px-2 py-0.5 text-xs ${sentimentBadgeColors[participant.sentiment]}`}>
                        {capitalize(participant.sentiment)}
                      </span>
                      <span className={`rounded border px-2 py-0.5 text-xs ${engagementBadgeColors[participant.engagementLevel]}`}>
                        {capitalize(participant.engagementLevel)} engagement
                      </span>
                    </div>

                    <p className="text-sm text-gray-600">{participant.summary}</p>

                    <div className="flex flex-wrap gap-2">
                      {participant.signalTotal > 0 ? (
                        signalOrder
                          .filter((signal) => participant.signalCounts[signal] > 0)
                          .map((signal) => (
                            <span
                              key={signal}
                              className={`rounded border px-2 py-1 text-xs ${emotionColors[signal]}`}
                            >
                              {participant.signalCounts[signal]} {emotionLabels[signal]}
                            </span>
                          ))
                      ) : (
                        <span className="rounded border border-gray-200 bg-gray-50 px-2 py-1 text-xs text-gray-500">
                          {participant.signalSummary}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="grid w-full grid-cols-1 gap-3 sm:grid-cols-3 lg:max-w-sm">
                    <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                      <div className="mb-1 flex items-center gap-1.5 text-xs text-gray-500">
                        <MessageSquare className="h-3.5 w-3.5" />
                        Utterances
                      </div>
                      <p className="text-gray-900">{participant.transcriptCount}</p>
                    </div>

                    <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                      <div className="mb-1 flex items-center gap-1.5 text-xs text-gray-500">
                        <Clock className="h-3.5 w-3.5" />
                        Speaking
                      </div>
                      <p className="text-gray-900">{formatDuration(participant.speakingTimeSeconds)}</p>
                    </div>

                    <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                      <div className="mb-1 flex items-center gap-1.5 text-xs text-gray-500">
                        <TrendingUp className="h-3.5 w-3.5" />
                        Score
                      </div>
                      <p className="text-gray-900">{participant.engagementScore}%</p>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Emotionally Significant Moments */}
      <div className="bg-white rounded-lg border border-gray-200">
        <div className="px-4 py-4 border-b border-gray-200 sm:px-6">
          <h2 className="text-gray-900">Emotionally Significant Moments</h2>
          <p className="text-sm text-gray-500 mt-1">Key emotional dynamics detected during the meeting</p>
        </div>

        {emotionalMoments.length > 0 ? (
          <div className="divide-y divide-gray-100">
            {emotionalMoments.map((moment, index) => (
              <div key={index} className="p-4 sm:p-6">
                <div className="flex flex-col items-start gap-4 sm:flex-row">
                  <div className={`shrink-0 px-3 py-1 rounded-lg text-sm border ${emotionColors[moment.type]}`}>
                    {moment.emotion}
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-3 mb-2">
                      <span className="text-sm text-gray-900">{moment.speaker}</span>
                      <span className="text-xs text-gray-400">{moment.time}</span>
                      <span className={`text-xs px-2 py-0.5 rounded ${
                        moment.intensity === 'high' ? 'bg-red-100 text-red-700' : 'bg-yellow-100 text-yellow-700'
                      }`}>
                        {moment.intensity} intensity
                      </span>
                    </div>

                    <div className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                      <p className="text-sm text-gray-700 italic">"{moment.text}"</p>
                    </div>

                    <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-gray-500">
                      {moment.type === 'disagreement' && (
                        <span className="flex items-center gap-1">
                          <Frown className="w-3 h-3" />
                          Indicates concern or disagreement
                        </span>
                      )}
                      {moment.type === 'agreement' && (
                        <span className="flex items-center gap-1">
                          <Smile className="w-3 h-3" />
                          Shows enthusiasm or agreement
                        </span>
                      )}
                      {(moment.type === 'tension' || moment.type === 'hesitation') && (
                        <span className="flex items-center gap-1">
                          <Meh className="w-3 h-3" />
                          {moment.reason}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-6 text-sm text-gray-500">
            No emotionally significant moments were detected.
          </div>
        )}
      </div>

      {/* Insights */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 sm:p-6">
        <h3 className="text-sm text-blue-900 mb-2">AI Insights</h3>
        <ul className="space-y-2 text-sm text-blue-800">
          {insights.map((insight, index) => (
            <li key={index} className="flex items-start gap-2">
              <span className="text-blue-600 mt-0.5">-</span>
              <span>{insight}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
