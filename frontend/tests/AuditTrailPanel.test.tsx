import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { AuditTrailPanel } from '../src/app/components/AuditTrailPanel';
import type { AuditEventRecord } from '../src/types';

const auditEvents: AuditEventRecord[] = [
  {
    id: 'event-1',
    scope: 'meeting',
    meeting_id: 'meeting-1',
    entity_type: 'meeting',
    entity_id: 'meeting-1',
    action: 'update',
    field_path: 'title',
    before: 'Original title',
    after: 'Edited title',
    metadata: { manual: true },
    created_at: '2026-05-11T08:00:00Z',
  },
  {
    id: 'event-2',
    scope: 'meeting',
    meeting_id: 'meeting-1',
    entity_type: 'speaker',
    entity_id: 'meeting-1',
    action: 'update',
    field_path: 'transcripts.speaker',
    before: { speakers: ['Speaker 1', 'Speaker 2'] },
    after: { speakers: ['Alice', 'Speaker 2'] },
    metadata: { affected_transcript_count: 2 },
    created_at: '2026-05-11T08:01:00Z',
  },
];

describe('AuditTrailPanel', () => {
  it('renders loading, error, and empty states', () => {
    const { rerender } = render(<AuditTrailPanel events={[]} isLoading />);
    expect(screen.getByText(/loading audit history/i)).toBeInTheDocument();

    rerender(<AuditTrailPanel events={[]} error="Failed to load audit history" />);
    expect(screen.getByText(/failed to load audit history/i)).toBeInTheDocument();

    rerender(<AuditTrailPanel events={[]} />);
    expect(screen.getByText(/no edit history recorded/i)).toBeInTheDocument();
  });

  it('renders audit event summaries and metadata', () => {
    render(<AuditTrailPanel events={auditEvents} />);

    expect(screen.getByText('Meeting')).toBeInTheDocument();
    expect(screen.getAllByText('Updated')).toHaveLength(2);
    expect(screen.getByText('title')).toBeInTheDocument();
    expect(screen.getByText(/Original title/)).toBeInTheDocument();
    expect(screen.getByText(/Edited title/)).toBeInTheDocument();
    expect(screen.getByText('Speakers')).toBeInTheDocument();
    expect(screen.getByText(/Speaker 1, Speaker 2/)).toBeInTheDocument();
    expect(screen.getByText(/affected_transcript_count: 2/)).toBeInTheDocument();
  });
});
