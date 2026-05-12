import {
  AlertCircle,
  CalendarDays,
  CheckCircle2,
  Circle,
  ClipboardList,
  Flag,
  FolderKanban,
  HelpCircle,
  ListChecks,
  Loader2,
  RefreshCcw,
  ShieldAlert,
  Target,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { useMemo, useState } from 'react';

import type {
  ActionItemStatus,
  MeetingMemoryOverview,
  MemoryActionItem,
  MemoryDecisionItem,
  MemoryMeetingReference,
  MemoryOpenQuestionItem,
  MemoryRiskItem,
  MemorySourceReference,
} from '../../types';

interface MeetingMemoryPanelProps {
  overview: MeetingMemoryOverview | null;
  selectedCollectionId: string;
  isLoading: boolean;
  error: string;
  onCollectionChange: (collectionId: string) => void;
  onRefresh: () => void;
  onOpenMeeting: (meetingId: string) => void;
  onActionStatusChange: (
    meetingId: string,
    actionItemIndex: number,
    status: ActionItemStatus
  ) => Promise<void> | void;
  onActionStatusChangeError?: (message: string) => void;
}

const statusClasses: Record<ActionItemStatus, string> = {
  pending: 'border-amber-200 bg-amber-50 text-amber-700',
  completed: 'border-green-200 bg-green-50 text-green-700',
};

const formatTimestamp = (value: string) =>
  new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));

const formatMeetingDate = (meeting: MemoryMeetingReference) => formatTimestamp(meeting.updated_at || meeting.created_at);

const buildCollectionLabel = (collection: MeetingMemoryOverview['collections'][number]) => {
  const typeLabel = collection.collection_type === 'tag'
    ? 'Project'
    : collection.collection_type === 'scene'
      ? 'Scene'
      : 'Workspace';
  return `${typeLabel}: ${collection.name} (${collection.meeting_count})`;
};

const artifactSourceLabel = (source: MemorySourceReference) => {
  if (source.transcript_index == null) {
    return 'Summary';
  }
  return `Transcript #${source.transcript_index + 1}`;
};

function SourceLine({
  source,
  onOpenMeeting,
}: {
  source: MemorySourceReference;
  onOpenMeeting: (meetingId: string) => void;
}) {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-gray-500">
      <button
        type="button"
        onClick={() => onOpenMeeting(source.meeting_id)}
        className="min-w-0 max-w-full truncate rounded-lg border border-gray-200 bg-white px-2 py-1 text-left text-gray-700 transition-colors hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
      >
        {source.title}
      </button>
      <span className="inline-flex items-center gap-1">
        <CalendarDays className="h-3.5 w-3.5" />
        {formatTimestamp(source.updated_at)}
      </span>
      <span>{artifactSourceLabel(source)}</span>
      {source.tags.map((tag) => (
        <span key={tag} className="rounded-full bg-gray-100 px-2 py-0.5 text-gray-600">
          {tag}
        </span>
      ))}
    </div>
  );
}

function StatTile({
  label,
  value,
  icon,
}: {
  label: string;
  value: number;
  icon: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="text-sm text-gray-500">{label}</p>
        <div className="rounded-lg bg-gray-50 p-2 text-gray-500">{icon}</div>
      </div>
      <p className="text-2xl font-semibold text-gray-900">{value}</p>
    </div>
  );
}

function RecentMeetingList({
  meetings,
  onOpenMeeting,
}: {
  meetings: MemoryMeetingReference[];
  onOpenMeeting: (meetingId: string) => void;
}) {
  if (meetings.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50 p-4 text-sm text-gray-500">
        No recent meetings.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {meetings.map((meeting) => (
        <button
          key={meeting.meeting_id}
          type="button"
          onClick={() => onOpenMeeting(meeting.meeting_id)}
          className="block w-full rounded-lg border border-gray-200 bg-white p-3 text-left transition-colors hover:border-blue-200 hover:bg-blue-50"
        >
          <p className="truncate text-sm font-medium text-gray-900">{meeting.title}</p>
          <p className="mt-1 text-xs text-gray-500">{formatMeetingDate(meeting)} - {meeting.source_type}</p>
        </button>
      ))}
    </div>
  );
}

function ActionItemCard({
  item,
  isUpdating,
  onToggle,
  onOpenMeeting,
}: {
  item: MemoryActionItem;
  isUpdating: boolean;
  onToggle: (item: MemoryActionItem) => void;
  onOpenMeeting: (meetingId: string) => void;
}) {
  const nextStatus: ActionItemStatus = item.status === 'completed' ? 'pending' : 'completed';

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex items-start gap-3">
        <button
          type="button"
          onClick={() => onToggle(item)}
          disabled={isUpdating}
          className={`mt-0.5 rounded-lg p-1 transition-colors ${
            item.status === 'completed'
              ? 'text-green-600 hover:bg-green-50'
              : 'text-gray-400 hover:bg-gray-50 hover:text-gray-600'
          } disabled:cursor-wait disabled:opacity-60`}
          aria-label={`Mark action item as ${nextStatus}`}
        >
          {isUpdating ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : item.status === 'completed' ? (
            <CheckCircle2 className="h-5 w-5" />
          ) : (
            <Circle className="h-5 w-5" />
          )}
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <p className={`break-words text-sm font-medium text-gray-900 ${item.status === 'completed' ? 'line-through opacity-70' : ''}`}>
              {item.task}
            </p>
            <span className={`w-fit shrink-0 rounded-full border px-2 py-0.5 text-xs ${statusClasses[item.status]}`}>
              {item.status}
            </span>
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-500">
            <span className="rounded-full border border-gray-200 bg-gray-50 px-2 py-1">Owner: {item.assignee}</span>
            <span className="rounded-full border border-gray-200 bg-gray-50 px-2 py-1">Deadline: {item.deadline}</span>
            <span className="rounded-full border border-gray-200 bg-gray-50 px-2 py-1">
              Confidence: {Math.round(item.confidence * 100)}%
            </span>
          </div>
          {item.source_excerpt && (
            <p className="mt-3 break-words rounded-lg border border-blue-100 bg-blue-50 p-3 text-sm text-gray-700">
              {item.source_excerpt}
            </p>
          )}
          <SourceLine source={item.source} onOpenMeeting={onOpenMeeting} />
        </div>
      </div>
    </div>
  );
}

function DecisionCard({
  item,
  onOpenMeeting,
}: {
  item: MemoryDecisionItem;
  onOpenMeeting: (meetingId: string) => void;
}) {
  return (
    <div className="rounded-lg border border-green-100 bg-green-50 p-4">
      <p className="break-words text-sm font-medium text-gray-900">{item.decision}</p>
      <SourceLine source={item.source} onOpenMeeting={onOpenMeeting} />
    </div>
  );
}

function RiskCard({
  item,
  onOpenMeeting,
}: {
  item: MemoryRiskItem;
  onOpenMeeting: (meetingId: string) => void;
}) {
  return (
    <div className="rounded-lg border border-red-100 bg-red-50 p-4">
      <p className="break-words text-sm font-medium text-gray-900">{item.risk}</p>
      <SourceLine source={item.source} onOpenMeeting={onOpenMeeting} />
    </div>
  );
}

function OpenQuestionCard({
  item,
  onOpenMeeting,
}: {
  item: MemoryOpenQuestionItem;
  onOpenMeeting: (meetingId: string) => void;
}) {
  return (
    <div className="rounded-lg border border-blue-100 bg-blue-50 p-4">
      <p className="break-words text-sm font-medium text-gray-900">{item.question}</p>
      <SourceLine source={item.source} onOpenMeeting={onOpenMeeting} />
    </div>
  );
}

export function MeetingMemoryPanel({
  overview,
  selectedCollectionId,
  isLoading,
  error,
  onCollectionChange,
  onRefresh,
  onOpenMeeting,
  onActionStatusChange,
  onActionStatusChangeError,
}: MeetingMemoryPanelProps) {
  const [statusFilter, setStatusFilter] = useState<'all' | ActionItemStatus>('pending');
  const [assigneeFilter, setAssigneeFilter] = useState('all');
  const [updatingActionId, setUpdatingActionId] = useState<string | null>(null);

  const assignees = useMemo(() => {
    if (!overview) {
      return [];
    }
    return Array.from(new Set(overview.action_items.map((item) => item.assignee))).sort((left, right) =>
      left.localeCompare(right)
    );
  }, [overview]);

  const filteredActionItems = useMemo(() => {
    if (!overview) {
      return [];
    }
    return overview.action_items.filter((item) => {
      if (statusFilter !== 'all' && item.status !== statusFilter) {
        return false;
      }
      if (assigneeFilter !== 'all' && item.assignee !== assigneeFilter) {
        return false;
      }
      return true;
    });
  }, [assigneeFilter, overview, statusFilter]);

  const toggleActionStatus = async (item: MemoryActionItem) => {
    const nextStatus: ActionItemStatus = item.status === 'completed' ? 'pending' : 'completed';
    try {
      setUpdatingActionId(item.id);
      await onActionStatusChange(item.source.meeting_id, item.action_item_index, nextStatus);
    } catch (error) {
      onActionStatusChangeError?.(error instanceof Error ? error.message : 'Failed to update action item status');
    } finally {
      setUpdatingActionId(null);
    }
  };

  if (isLoading && !overview) {
    return (
      <div className="mx-auto flex max-w-7xl items-center justify-center py-20 text-gray-500">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
        Loading meeting memory...
      </div>
    );
  }

  if (!overview) {
    return (
      <div className="mx-auto max-w-7xl rounded-lg border border-dashed border-gray-200 bg-white p-10 text-center text-gray-500">
        <FolderKanban className="mx-auto mb-3 h-10 w-10 text-gray-300" />
        <p>Meeting memory is empty.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="rounded-lg border border-gray-200 bg-white p-4 sm:p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="mb-2 flex items-center gap-2 text-sm text-blue-700">
              <FolderKanban className="h-4 w-4" />
              <span>Project Memory</span>
            </div>
            <h2 className="text-xl font-semibold text-gray-900">{overview.next_meeting_brief.collection_name}</h2>
            <p className="mt-2 max-w-3xl break-words text-sm leading-6 text-gray-600">
              {overview.next_meeting_brief.recap}
            </p>
            {error && (
              <p className="mt-2 flex items-center gap-1 text-sm text-red-600">
                <AlertCircle className="h-4 w-4" />
                {error}
              </p>
            )}
          </div>

          <div className="flex w-full flex-col gap-2 sm:w-auto sm:min-w-[320px] sm:flex-row lg:justify-end">
            <select
              value={selectedCollectionId}
              onChange={(event) => onCollectionChange(event.target.value)}
              className="min-w-0 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              aria-label="Memory collection"
            >
              {overview.collections.map((collection) => (
                <option key={collection.collection_id} value={collection.collection_id}>
                  {buildCollectionLabel(collection)}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={onRefresh}
              disabled={isLoading}
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-wait disabled:opacity-60"
            >
              {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
              <span>Refresh</span>
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <StatTile label="Meetings" value={overview.stats.meeting_count} icon={<FolderKanban className="h-4 w-4" />} />
        <StatTile label="Pending" value={overview.stats.open_action_count} icon={<ListChecks className="h-4 w-4" />} />
        <StatTile label="Completed" value={overview.stats.completed_action_count} icon={<CheckCircle2 className="h-4 w-4" />} />
        <StatTile label="Decisions" value={overview.stats.decision_count} icon={<Target className="h-4 w-4" />} />
        <StatTile label="Risks" value={overview.stats.risk_count} icon={<ShieldAlert className="h-4 w-4" />} />
        <StatTile label="Questions" value={overview.stats.open_question_count} icon={<HelpCircle className="h-4 w-4" />} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(320px,0.6fr)]">
        <section className="rounded-lg border border-gray-200 bg-white">
          <div className="border-b border-gray-200 p-4 sm:p-5">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-blue-50 p-2 text-blue-600">
                <ClipboardList className="h-5 w-5" />
              </div>
              <h3 className="text-base font-semibold text-gray-900">Next Meeting Brief</h3>
            </div>
          </div>
          <div className="grid gap-4 p-4 sm:p-5 md:grid-cols-2">
            <div>
              <h4 className="mb-3 text-sm font-medium text-gray-900">Agenda</h4>
              <div className="space-y-2">
                {overview.next_meeting_brief.agenda.map((item, index) => (
                  <div key={`${item}-${index}`} className="flex items-start gap-3 rounded-lg border border-gray-200 bg-gray-50 p-3">
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white text-xs text-gray-600">
                      {index + 1}
                    </span>
                    <p className="break-words text-sm text-gray-700">{item}</p>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h4 className="mb-3 text-sm font-medium text-gray-900">Focus</h4>
              <div className="space-y-2">
                {overview.next_meeting_brief.suggested_focus.map((item, index) => (
                  <div key={`${item}-${index}`} className="flex items-start gap-3 rounded-lg border border-amber-100 bg-amber-50 p-3">
                    <Flag className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                    <p className="break-words text-sm text-gray-700">{item}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="rounded-lg border border-gray-200 bg-white p-4 sm:p-5">
          <h3 className="mb-4 text-base font-semibold text-gray-900">Recent Meetings</h3>
          <RecentMeetingList meetings={overview.next_meeting_brief.recent_meetings} onOpenMeeting={onOpenMeeting} />
        </section>
      </div>

      <section className="rounded-lg border border-gray-200 bg-white">
        <div className="flex flex-col gap-4 border-b border-gray-200 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-amber-50 p-2 text-amber-600">
              <ListChecks className="h-5 w-5" />
            </div>
            <h3 className="text-base font-semibold text-gray-900">Action Item Center</h3>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:w-auto">
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}
              className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700"
              aria-label="Action status filter"
            >
              <option value="pending">Pending</option>
              <option value="completed">Completed</option>
              <option value="all">All statuses</option>
            </select>
            <select
              value={assigneeFilter}
              onChange={(event) => setAssigneeFilter(event.target.value)}
              className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700"
              aria-label="Action assignee filter"
            >
              <option value="all">All owners</option>
              {assignees.map((assignee) => (
                <option key={assignee} value={assignee}>{assignee}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="space-y-3 p-4 sm:p-5">
          {filteredActionItems.length === 0 ? (
            <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50 p-5 text-sm text-gray-500">
              No action items match this view.
            </div>
          ) : (
            filteredActionItems.map((item) => (
              <ActionItemCard
                key={item.id}
                item={item}
                isUpdating={updatingActionId === item.id}
                onToggle={(nextItem) => {
                  void toggleActionStatus(nextItem);
                }}
                onOpenMeeting={onOpenMeeting}
              />
            ))
          )}
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-3">
        <section className="rounded-lg border border-gray-200 bg-white">
          <div className="border-b border-gray-200 p-4 sm:p-5">
            <h3 className="text-base font-semibold text-gray-900">Decision Log</h3>
          </div>
          <div className="space-y-3 p-4 sm:p-5">
            {overview.decisions.length === 0 ? (
              <p className="rounded-lg border border-dashed border-gray-200 bg-gray-50 p-4 text-sm text-gray-500">
                No decisions recorded.
              </p>
            ) : (
              overview.decisions.map((item) => (
                <DecisionCard key={item.id} item={item} onOpenMeeting={onOpenMeeting} />
              ))
            )}
          </div>
        </section>

        <section className="rounded-lg border border-gray-200 bg-white">
          <div className="border-b border-gray-200 p-4 sm:p-5">
            <h3 className="text-base font-semibold text-gray-900">Risk Tracker</h3>
          </div>
          <div className="space-y-3 p-4 sm:p-5">
            {overview.risks.length === 0 ? (
              <p className="rounded-lg border border-dashed border-gray-200 bg-gray-50 p-4 text-sm text-gray-500">
                No risks recorded.
              </p>
            ) : (
              overview.risks.map((item) => (
                <RiskCard key={item.id} item={item} onOpenMeeting={onOpenMeeting} />
              ))
            )}
          </div>
        </section>

        <section className="rounded-lg border border-gray-200 bg-white">
          <div className="border-b border-gray-200 p-4 sm:p-5">
            <h3 className="text-base font-semibold text-gray-900">Open Questions</h3>
          </div>
          <div className="space-y-3 p-4 sm:p-5">
            {overview.open_questions.length === 0 ? (
              <p className="rounded-lg border border-dashed border-gray-200 bg-gray-50 p-4 text-sm text-gray-500">
                No open questions recorded.
              </p>
            ) : (
              overview.open_questions.map((item) => (
                <OpenQuestionCard key={item.id} item={item} onOpenMeeting={onOpenMeeting} />
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
