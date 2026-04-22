import { LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { TrendingUp, AlertCircle, Smile, Meh, Frown } from 'lucide-react';
import type { MeetingAnalysis, MeetingSignalCounts, MeetingSignalType } from '../../types';

interface DisplayTranscriptItem {
  speaker: string;
  text: string;
  start: number;
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

const sentimentColors = {
  positive: '#10b981',
  neutral: '#6b7280',
  negative: '#ef4444'
};

const emptySignalCounts: MeetingSignalCounts = {
  agreement: 0,
  disagreement: 0,
  tension: 0,
  hesitation: 0
};

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

const capitalize = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);

const getSignalCounts = (analysis: MeetingAnalysis) => analysis.signal_counts ?? emptySignalCounts;

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

const buildSentimentTrend = (analysis: MeetingAnalysis, transcripts: DisplayTranscriptItem[]) => {
  const highlights = [...analysis.highlights].sort((a, b) => {
    const aTime = transcripts[a.transcript_index]?.start ?? a.transcript_index;
    const bTime = transcripts[b.transcript_index]?.start ?? b.transcript_index;
    return aTime - bTime;
  });

  if (!highlights.length) {
    const fallback = sentimentFallbacks[analysis.overall_sentiment];
    return [
      { time: 'Start', positive: fallback.positive, neutral: fallback.neutral, negative: fallback.negative, overall: fallback.positive - fallback.negative },
      { time: 'Current', positive: fallback.positive, neutral: fallback.neutral, negative: fallback.negative, overall: fallback.positive - fallback.negative }
    ];
  }

  const running = { positive: 0, neutral: 0, negative: 0 };

  return highlights.map((highlight, index) => {
    const bucket = signalToSentiment[highlight.signal];
    running[bucket] += 1;

    const total = index + 1;
    const positive = Math.round((running.positive / total) * 100);
    const neutral = Math.round((running.neutral / total) * 100);
    const negative = Math.max(0, 100 - positive - neutral);
    const transcript = transcripts[highlight.transcript_index];

    return {
      time: transcript ? formatTime(transcript.start) : `#${highlight.transcript_index + 1}`,
      positive,
      neutral,
      negative,
      overall: positive - negative
    };
  });
};

const buildParticipantEngagement = (
  analysis: MeetingAnalysis,
  transcripts: DisplayTranscriptItem[]
) => {
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
  const safeTranscripts = transcripts || [];

  if (!analysis) {
    return (
      <div className="max-w-7xl mx-auto flex items-center justify-center py-20 text-gray-500">
        <p>Meeting analysis will appear here once the server processes the data.</p>
      </div>
    );
  }

  const sentimentOverTime = buildSentimentTrend(analysis, safeTranscripts);
  const overallSentiment = buildSentimentDistribution(analysis);
  const engagementByParticipant = buildParticipantEngagement(analysis, safeTranscripts);
  const emotionalMoments = buildEmotionalMoments(analysis, safeTranscripts);
  const insights = buildInsights(analysis);

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm text-gray-500">Overall Sentiment</h3>
            {getSentimentIcon(analysis.overall_sentiment)}
          </div>
          <p className="text-gray-900 mb-1">{capitalize(analysis.overall_sentiment)}</p>
          <p className="text-sm text-gray-600">
            {overallSentiment[0].value}% positive sentiment detected
          </p>
        </div>

        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm text-gray-500">Engagement Level</h3>
            <TrendingUp className="w-5 h-5 text-blue-600" />
          </div>
          <p className="text-gray-900 mb-1">{capitalize(analysis.engagement_level)}</p>
          <p className="text-sm text-gray-600">
            {analysis.engagement_summary || 'Participant engagement analyzed from meeting signals'}
          </p>
        </div>

        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm text-gray-500">Key Moments</h3>
            <AlertCircle className="w-5 h-5 text-orange-600" />
          </div>
          <p className="text-gray-900 mb-1">{emotionalMoments.length} Identified</p>
          <p className="text-sm text-gray-600">Emotionally significant points</p>
        </div>
      </div>

      {/* Sentiment Over Time Chart */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
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

      <div className="grid grid-cols-2 gap-6">
        {/* Overall Sentiment Distribution */}
        <div className="bg-white rounded-lg border border-gray-200 p-6">
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
        <div className="bg-white rounded-lg border border-gray-200 p-6">
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

      {/* Emotionally Significant Moments */}
      <div className="bg-white rounded-lg border border-gray-200">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-gray-900">Emotionally Significant Moments</h2>
          <p className="text-sm text-gray-500 mt-1">Key emotional dynamics detected during the meeting</p>
        </div>

        {emotionalMoments.length > 0 ? (
          <div className="divide-y divide-gray-100">
            {emotionalMoments.map((moment, index) => (
              <div key={index} className="p-6">
                <div className="flex items-start gap-4">
                  <div className={`px-3 py-1 rounded-lg text-sm border ${emotionColors[moment.type]}`}>
                    {moment.emotion}
                  </div>

                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
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

                    <div className="mt-2 flex items-center gap-4 text-xs text-gray-500">
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
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
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
