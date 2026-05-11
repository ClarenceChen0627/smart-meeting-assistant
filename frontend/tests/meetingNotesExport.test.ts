import { describe, expect, it } from 'vitest';

import { buildActionItemsMarkdown, buildMeetingNotesFilename, buildMeetingNotesMarkdown } from '../src/app/meetingNotesExport';
import type { MeetingSummary, TranscriptItem } from '../src/types';

const summary: MeetingSummary = {
  title: 'Launch Plan Review',
  overview: 'The team aligned on launch readiness and next steps.',
  key_topics: ['Launch readiness', 'Support coverage'],
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
    {
      task: 'Consider a later retro',
      assignee: 'Unassigned',
      deadline: 'Not specified',
      status: 'pending',
      source_excerpt: '',
      transcript_index: null,
      is_actionable: false,
      confidence: 0.4,
      owner_explicit: false,
      deadline_explicit: false,
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

describe('meeting notes export', () => {
  it('builds Markdown with summary fields and actionable transcript references', () => {
    const markdown = buildMeetingNotesMarkdown({
      summary,
      transcripts,
      meetingDate: '2026-05-08T01:00:00Z',
    });

    expect(markdown).toContain('# Launch Plan Review');
    expect(markdown).toContain('- Date: May 8, 2026');
    expect(markdown).toContain('- Duration: 13 seconds');
    expect(markdown).toContain('## Overview');
    expect(markdown).toContain('- Launch readiness');
    expect(markdown).toContain('- Proceed with the release candidate');
    expect(markdown).toContain('- Support staffing is not final');
    expect(markdown).toContain(
      '- Send the final launch checklist (Owner: Speaker 1; Deadline: Friday; Status: pending; Source: 01:05; Confidence: 92%)'
    );
    expect(markdown).not.toContain('Consider a later retro');
  });

  it('uses the meeting record title before the summary title', () => {
    const markdown = buildMeetingNotesMarkdown({
      summary,
      meetingTitle: 'Saved Customer Review',
    });

    expect(markdown.startsWith('# Saved Customer Review')).toBe(true);
  });

  it('builds the Chinese meeting minutes template', () => {
    const markdown = buildMeetingNotesMarkdown({
      summary,
      transcripts,
      meetingDate: '2026-05-08T01:00:00Z',
      template: 'chinese_minutes',
    });

    expect(markdown).toContain('# Launch Plan Review');
    expect(markdown).toContain('## 会议概览');
    expect(markdown).toContain('## 后续行动');
    expect(markdown).toContain('负责人: Speaker 1');
  });

  it('builds an action item only export', () => {
    const markdown = buildActionItemsMarkdown({
      summary,
      transcripts,
      meetingDate: '2026-05-08T01:00:00Z',
    });

    expect(markdown).toContain('# Launch Plan Review - Action Items');
    expect(markdown).toContain('| Task | Owner | Deadline | Status | Source | Confidence |');
    expect(markdown).toContain('| Send the final launch checklist | Speaker 1 | Friday | pending | 01:05 | 92% |');
    expect(markdown).not.toContain('Consider a later retro');
  });

  it('sanitizes exported filenames', () => {
    expect(buildMeetingNotesFilename({ ...summary, title: 'Launch: Plan / Review?' }, 'meeting-1')).toBe(
      'launch-plan-review.md'
    );
    expect(buildMeetingNotesFilename(summary, 'meeting-1', 'Saved: Customer / Review?')).toBe(
      'saved-customer-review.md'
    );
    expect(buildMeetingNotesFilename({ ...summary, title: '' }, 'meeting-1')).toBe('meeting-1.md');
  });
});
