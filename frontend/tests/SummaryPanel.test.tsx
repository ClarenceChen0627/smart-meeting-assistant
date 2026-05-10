import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { SummaryPanel } from '../src/app/components/SummaryPanel';
import type { MeetingSummary, MeetingSummaryUpdate, TranscriptItem } from '../src/types';

const summary: MeetingSummary = {
  title: 'Launch Plan Review',
  overview: 'The team aligned on launch readiness and next steps.',
  key_topics: ['Launch readiness'],
  decisions: ['Proceed with the release candidate'],
  risks: ['Support staffing is not final'],
  action_items: [
    {
      task: 'Send the final launch checklist',
      assignee: 'Speaker 1',
      deadline: 'Friday',
      status: 'pending',
      source_excerpt: 'I will send the final launch checklist by Friday.',
      transcript_index: 0,
      is_actionable: true,
      confidence: 0.92,
      owner_explicit: true,
      deadline_explicit: true,
    },
  ],
};

const transcripts: TranscriptItem[] = [
  {
    transcript_index: 0,
    speaker: 'Speaker 1',
    speaker_is_final: true,
    transcript_is_final: true,
    text: 'I will send the final launch checklist by Friday.',
    start: 65,
    end: 78,
  },
];

afterEach(() => {
  vi.restoreAllMocks();
});

describe('SummaryPanel', () => {
  it('exports rendered meeting notes when summary has content', async () => {
    const user = userEvent.setup();
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const revokeSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:meeting-notes');

    render(
      <SummaryPanel
        summary={summary}
        transcripts={transcripts}
        meetingDate="2026-05-08T01:00:00Z"
        meetingId="meeting-1"
      />
    );

    await user.click(screen.getByRole('button', { name: /export notes/i }));

    expect(URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(revokeSpy).toHaveBeenCalledWith('blob:meeting-notes');
  });

  it('does not show export for an empty summary', () => {
    render(
      <SummaryPanel
        summary={{ title: '', overview: '', key_topics: [], decisions: [], risks: [], action_items: [] }}
        meetingId="meeting-1"
      />
    );

    expect(screen.queryByRole('button', { name: /export notes/i })).not.toBeInTheDocument();
    expect(screen.getByText(/no concise meeting summary was generated/i)).toBeInTheDocument();
  });

  it('marks provisional live summaries and hides saved-meeting actions', () => {
    render(
      <SummaryPanel
        summary={summary}
        transcripts={transcripts}
        meetingId="meeting-1"
        isProvisional
        onSaveSummary={vi.fn()}
      />
    );

    expect(screen.getByText(/live rolling summary/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /export notes/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /edit summary/i })).not.toBeInTheDocument();
  });

  it('keeps edit and save behavior', async () => {
    const user = userEvent.setup();
    const onSaveSummary = vi.fn<(_: string, update: MeetingSummaryUpdate) => Promise<void>>()
      .mockResolvedValue(undefined);

    render(
      <SummaryPanel
        summary={summary}
        transcripts={transcripts}
        meetingId="meeting-1"
        onSaveSummary={onSaveSummary}
      />
    );

    await user.click(screen.getByRole('button', { name: /edit summary/i }));
    const overview = screen.getByLabelText(/overview/i);
    await user.clear(overview);
    await user.type(overview, 'Edited overview.');
    await user.click(screen.getByRole('button', { name: /save summary/i }));

    expect(onSaveSummary).toHaveBeenCalledWith(
      'meeting-1',
      expect.objectContaining({ overview: 'Edited overview.' })
    );
  });
});
