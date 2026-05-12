import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { MeetingMemoryPanel } from '../src/app/components/MeetingMemoryPanel';
import type { MeetingMemoryOverview } from '../src/types';

const overview: MeetingMemoryOverview = {
  collection_id: 'tag:Launch',
  generated_at: '2026-05-12T10:00:00Z',
  collections: [
    {
      collection_id: 'all',
      collection_type: 'all',
      name: 'All active meetings',
      meeting_count: 2,
      finalized_count: 2,
      open_action_count: 1,
      completed_action_count: 1,
      decision_count: 1,
      risk_count: 1,
      open_question_count: 1,
      updated_at: '2026-05-12T09:00:00Z',
    },
    {
      collection_id: 'tag:Launch',
      collection_type: 'tag',
      name: 'Launch',
      meeting_count: 2,
      finalized_count: 2,
      open_action_count: 1,
      completed_action_count: 1,
      decision_count: 1,
      risk_count: 1,
      open_question_count: 1,
      updated_at: '2026-05-12T09:00:00Z',
    },
    {
      collection_id: 'tag:Budget',
      collection_type: 'tag',
      name: 'Budget',
      meeting_count: 1,
      finalized_count: 1,
      open_action_count: 0,
      completed_action_count: 1,
      decision_count: 1,
      risk_count: 0,
      open_question_count: 0,
      updated_at: '2026-05-11T09:00:00Z',
    },
  ],
  stats: {
    meeting_count: 2,
    finalized_count: 2,
    action_count: 2,
    open_action_count: 1,
    completed_action_count: 1,
    decision_count: 1,
    risk_count: 1,
    open_question_count: 1,
  },
  action_items: [
    {
      id: 'launch-1:action:0',
      action_item_index: 0,
      task: 'Send the launch checklist',
      assignee: 'Speaker 1',
      deadline: 'Friday',
      status: 'pending',
      source_excerpt: 'I will send the launch checklist by Friday.',
      confidence: 0.92,
      owner_explicit: true,
      deadline_explicit: true,
      source: {
        meeting_id: 'launch-1',
        title: 'Launch Readiness',
        created_at: '2026-05-12T08:00:00Z',
        updated_at: '2026-05-12T09:00:00Z',
        scene: 'general',
        source_type: 'live',
        tags: ['Launch'],
        transcript_index: 1,
        source_excerpt: 'I will send the launch checklist by Friday.',
      },
    },
    {
      id: 'launch-2:action:0',
      action_item_index: 0,
      task: 'Share the budget update',
      assignee: 'Speaker 2',
      deadline: 'Today',
      status: 'completed',
      source_excerpt: 'I will share the budget update today.',
      confidence: 0.9,
      owner_explicit: true,
      deadline_explicit: true,
      source: {
        meeting_id: 'launch-2',
        title: 'Launch Budget',
        created_at: '2026-05-11T08:00:00Z',
        updated_at: '2026-05-11T09:00:00Z',
        scene: 'finance',
        source_type: 'upload',
        tags: ['Launch', 'Budget'],
        transcript_index: null,
        source_excerpt: 'I will share the budget update today.',
      },
    },
  ],
  decisions: [
    {
      id: 'launch-1:decision:0',
      decision: 'Keep the launch date',
      source: {
        meeting_id: 'launch-1',
        title: 'Launch Readiness',
        created_at: '2026-05-12T08:00:00Z',
        updated_at: '2026-05-12T09:00:00Z',
        scene: 'general',
        source_type: 'live',
        tags: ['Launch'],
        transcript_index: 0,
        source_excerpt: 'We decided to keep the launch date.',
      },
    },
  ],
  risks: [
    {
      id: 'launch-1:risk:0',
      risk: 'Integration risk needs mitigation',
      source: {
        meeting_id: 'launch-1',
        title: 'Launch Readiness',
        created_at: '2026-05-12T08:00:00Z',
        updated_at: '2026-05-12T09:00:00Z',
        scene: 'general',
        source_type: 'live',
        tags: ['Launch'],
        transcript_index: 0,
        source_excerpt: 'Integration risk needs mitigation.',
      },
    },
  ],
  open_questions: [
    {
      id: 'launch-1:question:0',
      question: 'Who owns support coverage?',
      source: {
        meeting_id: 'launch-1',
        title: 'Launch Readiness',
        created_at: '2026-05-12T08:00:00Z',
        updated_at: '2026-05-12T09:00:00Z',
        scene: 'general',
        source_type: 'live',
        tags: ['Launch'],
        transcript_index: 0,
        source_excerpt: 'Who owns support coverage?',
      },
    },
  ],
  next_meeting_brief: {
    collection_id: 'tag:Launch',
    collection_name: 'Launch',
    generated_at: '2026-05-12T10:00:00Z',
    recap: 'Launch has 2 active meetings, 1 pending action items, 1 decisions, 1 risks, and 1 open questions.',
    agenda: ['Confirm progress: Send the launch checklist'],
    suggested_focus: ['Close pending follow-up work.'],
    recent_meetings: [
      {
        meeting_id: 'launch-1',
        title: 'Launch Readiness',
        created_at: '2026-05-12T08:00:00Z',
        updated_at: '2026-05-12T09:00:00Z',
        scene: 'general',
        source_type: 'live',
        tags: ['Launch'],
      },
    ],
  },
};

describe('MeetingMemoryPanel', () => {
  it('renders project memory sections and switches collections', async () => {
    const user = userEvent.setup();
    const onCollectionChange = vi.fn();

    render(
      <MeetingMemoryPanel
        overview={overview}
        selectedCollectionId="tag:Launch"
        isLoading={false}
        error=""
        onCollectionChange={onCollectionChange}
        onRefresh={vi.fn()}
        onOpenMeeting={vi.fn()}
        onActionStatusChange={vi.fn()}
      />
    );

    expect(screen.getByText('Project Memory')).toBeInTheDocument();
    expect(screen.getByText('Send the launch checklist')).toBeInTheDocument();
    expect(screen.getByText('Keep the launch date')).toBeInTheDocument();
    expect(screen.getByText('Integration risk needs mitigation')).toBeInTheDocument();
    expect(screen.getByText('Who owns support coverage?')).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(/memory collection/i), 'tag:Budget');

    expect(onCollectionChange).toHaveBeenCalledWith('tag:Budget');
  });

  it('updates action item status with meeting context', async () => {
    const user = userEvent.setup();
    const onActionStatusChange = vi.fn().mockResolvedValue(undefined);

    render(
      <MeetingMemoryPanel
        overview={overview}
        selectedCollectionId="tag:Launch"
        isLoading={false}
        error=""
        onCollectionChange={vi.fn()}
        onRefresh={vi.fn()}
        onOpenMeeting={vi.fn()}
        onActionStatusChange={onActionStatusChange}
      />
    );

    await user.click(screen.getByRole('button', { name: /mark action item as completed/i }));

    expect(onActionStatusChange).toHaveBeenCalledWith('launch-1', 0, 'completed');
  });
});
