import { FileClock, Loader2 } from 'lucide-react';
import type { AuditEventRecord } from '../../types';

interface AuditTrailPanelProps {
  events: AuditEventRecord[];
  isLoading?: boolean;
  error?: string;
}

const actionLabels: Record<string, string> = {
  create: 'Created',
  update: 'Updated',
  delete: 'Deleted',
};

const entityLabels: Record<string, string> = {
  meeting: 'Meeting',
  summary: 'Summary',
  action_item: 'Action item',
  speaker: 'Speakers',
  glossary_term: 'Glossary term',
};

const formatTimestamp = (value: string) =>
  new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));

const compactValue = (value: unknown): string => {
  if (value == null) {
    return 'None';
  }
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  if (Array.isArray(value)) {
    return `${value.length} item${value.length === 1 ? '' : 's'}`;
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    if (typeof record.title === 'string') {
      return record.title;
    }
    if (typeof record.overview === 'string') {
      return record.overview;
    }
    if (typeof record.task === 'string') {
      return record.task;
    }
    if (typeof record.term === 'string') {
      return record.term;
    }
    if (Array.isArray(record.speakers)) {
      return record.speakers.join(', ') || 'No speakers';
    }
    return JSON.stringify(record);
  }
  return String(value);
};

const formatMetadata = (metadata: Record<string, unknown>) => {
  const entries = Object.entries(metadata).filter(([, value]) => value != null && value !== '');
  if (!entries.length) {
    return null;
  }
  return entries.map(([key, value]) => `${key}: ${compactValue(value)}`).join(' | ');
};

export function AuditTrailPanel({ events, isLoading = false, error }: AuditTrailPanelProps) {
  if (isLoading) {
    return (
      <div className="mx-auto flex max-w-5xl items-center justify-center gap-2 py-20 text-sm text-gray-500">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading audit history...
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-5xl rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        {error}
      </div>
    );
  }

  if (!events.length) {
    return (
      <div className="mx-auto flex max-w-5xl flex-col items-center justify-center rounded-lg border border-dashed border-gray-200 bg-white py-16 text-center">
        <FileClock className="mb-3 h-10 w-10 text-gray-300" />
        <p className="text-sm text-gray-600">No edit history recorded for this meeting.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-3">
      {events.map((event) => {
        const metadata = formatMetadata(event.metadata);
        return (
          <article key={event.id} className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded border border-blue-200 bg-blue-50 px-2 py-0.5 text-xs text-blue-700">
                    {entityLabels[event.entity_type] ?? event.entity_type}
                  </span>
                  <span className="rounded border border-gray-200 bg-gray-50 px-2 py-0.5 text-xs text-gray-600">
                    {actionLabels[event.action] ?? event.action}
                  </span>
                  {event.field_path && (
                    <span className="text-xs text-gray-500">{event.field_path}</span>
                  )}
                </div>
                <p className="mt-3 text-sm text-gray-900">
                  <span className="text-gray-500">Before:</span> {compactValue(event.before)}
                </p>
                <p className="mt-1 text-sm text-gray-900">
                  <span className="text-gray-500">After:</span> {compactValue(event.after)}
                </p>
                {metadata && (
                  <p className="mt-2 text-xs text-gray-500">{metadata}</p>
                )}
              </div>
              <time className="shrink-0 text-xs text-gray-500" dateTime={event.created_at}>
                {formatTimestamp(event.created_at)}
              </time>
            </div>
          </article>
        );
      })}
    </div>
  );
}
