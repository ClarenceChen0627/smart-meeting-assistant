import { describe, expect, it } from 'vitest';

import { buildParticipantDetails, buildSentimentTrend } from '../src/app/components/MeetingAnalysisPanel';
import type { MeetingAnalysis, TranscriptItem } from '../src/types';

const analysis: MeetingAnalysis = {
  overall_sentiment: 'neutral',
  engagement_level: 'medium',
  engagement_summary: 'A practical conversation with one cooperative moment.',
  signal_counts: {
    agreement: 1,
    disagreement: 0,
    tension: 0,
    hesitation: 0,
  },
  highlights: [
    {
      transcript_index: 13,
      signal: 'agreement',
      severity: 'low',
      reason: 'Speaker asks for help and expects cooperation.',
    },
  ],
  participants: [],
};

const transcripts: TranscriptItem[] = Array.from({ length: 15 }, (_, index) => ({
  transcript_index: index,
  speaker: index % 2 === 0 ? 'Speaker 1' : 'Speaker 2',
  speaker_is_final: true,
  transcript_is_final: true,
  text: `Transcript ${index}`,
  start: index === 13 ? 35.1 : index * 2,
  end: index === 13 ? 37.02 : index * 2 + 1,
}));

describe('buildSentimentTrend', () => {
  it('creates a visible trend even when upload analysis has only one highlight', () => {
    const trend = buildSentimentTrend(analysis, transcripts);

    expect(trend).toHaveLength(3);
    expect(trend[0].time).toBe('Start');
    expect(trend[1]).toEqual(
      expect.objectContaining({
        time: '00:35',
        positive: 100,
        neutral: 0,
        negative: 0,
      })
    );
    expect(trend[2]).toEqual(expect.objectContaining({ time: 'End', positive: 100 }));
  });
});

describe('buildParticipantDetails', () => {
  it('uses backend participant rollups when available', () => {
    const details = buildParticipantDetails(
      {
        ...analysis,
        participants: [
          {
            speaker: 'Alice',
            transcript_count: 4,
            speaking_time_seconds: 72.4,
            signal_counts: {
              agreement: 2,
              disagreement: 0,
              tension: 0,
              hesitation: 1,
            },
            sentiment: 'positive',
            engagement_level: 'high',
            engagement_summary: 'Alice led the launch alignment discussion.',
          },
        ],
      },
      transcripts
    );

    expect(details).toHaveLength(1);
    expect(details[0]).toMatchObject({
      name: 'Alice',
      sentiment: 'positive',
      engagementLevel: 'high',
      engagementScore: 85,
      transcriptCount: 4,
      speakingTimeSeconds: 72.4,
      signalTotal: 3,
      signalSummary: '2 agreement, 1 hesitation',
      summary: 'Alice led the launch alignment discussion.',
    });
  });

  it('builds speaker-level fallback details from highlights and transcript timing', () => {
    const details = buildParticipantDetails(
      {
        ...analysis,
        highlights: [
          {
            transcript_index: 0,
            signal: 'agreement',
            severity: 'medium',
            reason: 'Explicit agreement.',
          },
          {
            transcript_index: 1,
            signal: 'tension',
            severity: 'high',
            reason: 'Explicit risk.',
          },
        ],
      },
      [
        {
          ...transcripts[0],
          speaker: 'Speaker 1',
          start: 0,
          end: 3.2,
        },
        {
          ...transcripts[1],
          speaker: 'Speaker 1',
          start: 5,
          end: 7.5,
        },
        {
          ...transcripts[2],
          speaker: 'Speaker 2',
          start: 10,
          end: 11,
        },
      ]
    );

    expect(details[0]).toMatchObject({
      name: 'Speaker 1',
      sentiment: 'mixed',
      engagementLevel: 'high',
      transcriptCount: 2,
      speakingTimeSeconds: 5.7,
      signalTotal: 2,
      signalSummary: '1 agreement, 1 tension',
    });
    expect(details[1]).toMatchObject({
      name: 'Speaker 2',
      sentiment: 'neutral',
      engagementLevel: 'medium',
      signalSummary: 'No interaction signals',
    });
  });
});
