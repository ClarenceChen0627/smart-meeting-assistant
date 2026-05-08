import { describe, expect, it } from 'vitest';

import { buildSentimentTrend } from '../src/app/components/MeetingAnalysisPanel';
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
