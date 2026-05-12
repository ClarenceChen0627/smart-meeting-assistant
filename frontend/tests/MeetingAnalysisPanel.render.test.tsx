import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('recharts', async () => {
  const React = await import('react');
  const Container = ({ children }: { children?: React.ReactNode }) =>
    React.createElement('div', null, children);
  const Empty = () => null;

  return {
    ResponsiveContainer: Container,
    LineChart: Container,
    Line: Empty,
    BarChart: Container,
    Bar: Empty,
    PieChart: Container,
    Pie: Container,
    Cell: Empty,
    XAxis: Empty,
    YAxis: Empty,
    CartesianGrid: Empty,
    Tooltip: Empty,
    Legend: Empty,
  };
});

import { MeetingAnalysisPanel } from '../src/app/components/MeetingAnalysisPanel';
import type { MeetingAnalysis, TranscriptItem } from '../src/types';

const transcripts: TranscriptItem[] = [
  {
    transcript_index: 0,
    speaker: 'Alice',
    speaker_is_final: true,
    transcript_is_final: true,
    text: 'I agree with the launch plan.',
    start: 0,
    end: 4,
  },
  {
    transcript_index: 1,
    speaker: 'Bob',
    speaker_is_final: true,
    transcript_is_final: true,
    text: 'The risk is high if support coverage slips.',
    start: 6,
    end: 10,
  },
];

const analysis: MeetingAnalysis = {
  overall_sentiment: 'mixed',
  engagement_level: 'high',
  engagement_summary: 'The team showed active launch discussion.',
  signal_counts: {
    agreement: 2,
    disagreement: 0,
    tension: 1,
    hesitation: 0,
  },
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
  participants: [
    {
      speaker: 'Alice',
      transcript_count: 3,
      speaking_time_seconds: 72.4,
      signal_counts: {
        agreement: 2,
        disagreement: 0,
        tension: 0,
        hesitation: 0,
      },
      sentiment: 'positive',
      engagement_level: 'high',
      engagement_summary: 'Alice drove alignment and confirmed next steps.',
    },
    {
      speaker: 'Bob',
      transcript_count: 1,
      speaking_time_seconds: 18,
      signal_counts: {
        agreement: 0,
        disagreement: 0,
        tension: 1,
        hesitation: 0,
      },
      sentiment: 'negative',
      engagement_level: 'medium',
      engagement_summary: 'Bob raised one launch risk.',
    },
  ],
};

describe('MeetingAnalysisPanel participant details', () => {
  it('renders participant-level sentiment, engagement, timing, and signals', () => {
    render(<MeetingAnalysisPanel analysis={analysis} transcripts={transcripts} />);

    expect(screen.getByText('Participant Details')).toBeInTheDocument();
    expect(screen.getAllByText('Alice').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Bob').length).toBeGreaterThan(0);
    expect(screen.getByText('Alice drove alignment and confirmed next steps.')).toBeInTheDocument();
    expect(screen.getByText('Bob raised one launch risk.')).toBeInTheDocument();
    expect(screen.getByText('2 Agreement')).toBeInTheDocument();
    expect(screen.getByText('1 Tension')).toBeInTheDocument();
    expect(screen.getByText('1m 12s')).toBeInTheDocument();
    expect(screen.getByText('18s')).toBeInTheDocument();
    expect(screen.getByText('85%')).toBeInTheDocument();
  });
});
