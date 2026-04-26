import { CheckCircle2, FileText, Plus, Save, Target, Trash2, TrendingUp, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import type {
  ActionItem,
  ActionItemStatus,
  MeetingSummary,
  MeetingSummaryUpdate,
  TranscriptItem,
} from '../../types';

interface SummaryPanelProps {
  summary: MeetingSummary | null;
  transcripts?: TranscriptItem[];
  meetingDate?: string | null;
  meetingId?: string | null;
  isSaving?: boolean;
  onSaveSummary?: (meetingId: string, summary: MeetingSummaryUpdate) => Promise<void> | void;
  onSaveError?: (message: string) => void;
}

interface SummaryDraft {
  overview: string;
  key_topics: string[];
  decisions: string[];
  risks: string[];
  action_items: ActionItem[];
}

const emptyActionItem = (): ActionItem => ({
  task: '',
  assignee: 'Unassigned',
  deadline: 'Not specified',
  status: 'pending',
  source_excerpt: '',
  transcript_index: null,
  is_actionable: true,
  confidence: 0.7,
  owner_explicit: false,
  deadline_explicit: false,
});

const toDraft = (summary: MeetingSummary): SummaryDraft => ({
  overview: summary.overview,
  key_topics: [...summary.key_topics],
  decisions: [...summary.decisions],
  risks: [...summary.risks],
  action_items: summary.action_items.map((item) => ({ ...item })),
});

const sanitizeStringList = (items: string[]) =>
  items.map((item) => item.trim()).filter(Boolean);

const sanitizeActionItems = (items: ActionItem[]) =>
  items
    .map((item) => ({
      ...item,
      task: item.task.trim(),
      assignee: item.assignee.trim() || 'Unassigned',
      deadline: item.deadline.trim() || 'Not specified',
      source_excerpt: item.source_excerpt.trim(),
    }))
    .filter((item) => item.task);

const formatDuration = (transcripts: TranscriptItem[] = []) => {
  if (!transcripts.length) {
    return 'Not available';
  }

  const start = transcripts[0]?.start ?? 0;
  const end = transcripts.reduce((latest, item) => Math.max(latest, item.end ?? item.start ?? 0), start);
  const totalSeconds = Math.max(0, Math.round(end - start));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (minutes === 0) {
    return `${seconds} seconds`;
  }

  return seconds > 0 ? `${minutes} min ${seconds} sec` : `${minutes} minutes`;
};

const formatSessionDate = (meetingDate?: string | null) => {
  const value = meetingDate ? new Date(meetingDate) : new Date();
  return new Intl.DateTimeFormat('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  }).format(value);
};

const formatTranscriptReference = (item: ActionItem, transcripts: TranscriptItem[]) => {
  if (item.transcript_index == null) {
    return 'Summary';
  }

  const transcript = transcripts[item.transcript_index];
  if (!transcript) {
    return `#${item.transcript_index + 1}`;
  }

  const minutes = Math.floor(transcript.start / 60);
  const seconds = Math.floor(transcript.start % 60);
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
};

interface EditableListProps {
  title: string;
  items: string[];
  placeholder: string;
  onChange: (items: string[]) => void;
}

function EditableList({ title, items, placeholder, onChange }: EditableListProps) {
  const updateItem = (index: number, value: string) => {
    onChange(items.map((item, itemIndex) => (itemIndex === index ? value : item)));
  };

  const removeItem = (index: number) => {
    onChange(items.filter((_, itemIndex) => itemIndex !== index));
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-medium text-gray-900">{title}</h3>
        <button
          type="button"
          onClick={() => onChange([...items, ''])}
          className="inline-flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-1.5 text-xs text-gray-600 transition-colors hover:bg-gray-50"
        >
          <Plus className="h-3.5 w-3.5" />
          <span>Add</span>
        </button>
      </div>

      <div className="space-y-2">
        {items.length === 0 && (
          <p className="rounded-lg border border-dashed border-gray-200 bg-gray-50 p-3 text-sm text-gray-500">
            No items yet.
          </p>
        )}
        {items.map((item, index) => (
          <div key={index} className="flex items-center gap-2">
            <input
              value={item}
              onChange={(event) => updateItem(index, event.target.value)}
              placeholder={placeholder}
              className="min-w-0 flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
            />
            <button
              type="button"
              onClick={() => removeItem(index)}
              className="rounded-lg border border-gray-200 p-2 text-gray-400 transition-colors hover:border-red-200 hover:bg-red-50 hover:text-red-600"
              aria-label={`Remove ${title} item`}
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

interface ActionItemEditorProps {
  items: ActionItem[];
  onChange: (items: ActionItem[]) => void;
}

function ActionItemEditor({ items, onChange }: ActionItemEditorProps) {
  const updateItem = (index: number, update: Partial<ActionItem>) => {
    onChange(items.map((item, itemIndex) => (itemIndex === index ? { ...item, ...update } : item)));
  };

  const removeItem = (index: number) => {
    onChange(items.filter((_, itemIndex) => itemIndex !== index));
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-medium text-gray-900">Action Items</h3>
        <button
          type="button"
          onClick={() => onChange([...items, emptyActionItem()])}
          className="inline-flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-1.5 text-xs text-gray-600 transition-colors hover:bg-gray-50"
        >
          <Plus className="h-3.5 w-3.5" />
          <span>Add</span>
        </button>
      </div>

      <div className="space-y-3">
        {items.length === 0 && (
          <p className="rounded-lg border border-dashed border-gray-200 bg-gray-50 p-3 text-sm text-gray-500">
            No action items yet.
          </p>
        )}
        {items.map((item, index) => (
          <div key={index} className="rounded-lg border border-gray-100 bg-gray-50 p-3">
            <div className="mb-3 flex items-start gap-2">
              <textarea
                value={item.task}
                onChange={(event) => updateItem(index, { task: event.target.value })}
                placeholder="Action item task"
                rows={2}
                className="min-w-0 flex-1 resize-none rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              />
              <button
                type="button"
                onClick={() => removeItem(index)}
                className="rounded-lg border border-gray-200 bg-white p-2 text-gray-400 transition-colors hover:border-red-200 hover:bg-red-50 hover:text-red-600"
                aria-label="Remove action item"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>

            <div className="grid gap-2 md:grid-cols-3">
              <input
                value={item.assignee}
                onChange={(event) => updateItem(index, { assignee: event.target.value })}
                placeholder="Assignee"
                className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              />
              <input
                value={item.deadline}
                onChange={(event) => updateItem(index, { deadline: event.target.value })}
                placeholder="Deadline"
                className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              />
              <select
                value={item.status}
                onChange={(event) => updateItem(index, { status: event.target.value as ActionItemStatus })}
                className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              >
                <option value="pending">pending</option>
                <option value="completed">completed</option>
              </select>
            </div>

            <input
              value={item.source_excerpt}
              onChange={(event) => updateItem(index, { source_excerpt: event.target.value })}
              placeholder="Optional source excerpt"
              className="mt-2 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
            />
          </div>
        ))}
      </div>
    </div>
  );
}

export function SummaryPanel({
  summary,
  transcripts = [],
  meetingDate,
  meetingId,
  isSaving = false,
  onSaveSummary,
  onSaveError,
}: SummaryPanelProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState<SummaryDraft | null>(summary ? toDraft(summary) : null);

  useEffect(() => {
    if (!isEditing) {
      setDraft(summary ? toDraft(summary) : null);
    }
  }, [summary, isEditing]);

  if (!summary) {
    return (
      <div className="max-w-5xl mx-auto flex items-center justify-center py-20 text-gray-500">
        <div className="text-center">
          <FileText className="w-12 h-12 text-gray-300 mx-auto mb-3" />
          <p>Meeting summary will appear here once processing is complete.</p>
        </div>
      </div>
    );
  }

  const displayedActionItems = summary.action_items.filter((item) => item.is_actionable);
  const hasMeaningfulSummary =
    Boolean(summary.overview.trim()) ||
    summary.key_topics.length > 0 ||
    summary.decisions.length > 0 ||
    summary.risks.length > 0 ||
    displayedActionItems.length > 0;

  const canEdit = Boolean(meetingId && onSaveSummary);

  const startEditing = () => {
    setDraft(toDraft(summary));
    setIsEditing(true);
  };

  const cancelEditing = () => {
    setDraft(toDraft(summary));
    setIsEditing(false);
  };

  const saveSummary = async () => {
    if (!meetingId || !draft || !onSaveSummary) {
      return;
    }

    try {
      await onSaveSummary(meetingId, {
        overview: draft.overview.trim(),
        key_topics: sanitizeStringList(draft.key_topics),
        decisions: sanitizeStringList(draft.decisions),
        risks: sanitizeStringList(draft.risks),
        action_items: sanitizeActionItems(draft.action_items),
      });
      setIsEditing(false);
    } catch (error) {
      onSaveError?.(error instanceof Error ? error.message : 'Failed to update meeting summary');
    }
  };

  if (isEditing && draft) {
    return (
      <div className="max-w-5xl mx-auto space-y-4">
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-sm font-medium text-blue-900">Edit Summary</h2>
              <p className="text-xs text-blue-700">Changes are saved to this meeting record.</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={cancelEditing}
                disabled={isSaving}
                className="inline-flex items-center gap-2 rounded-lg border border-blue-200 bg-white px-3 py-2 text-sm text-blue-700 transition-colors hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <X className="h-4 w-4" />
                <span>Cancel</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  void saveSummary();
                }}
                disabled={isSaving}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm text-white transition-colors hover:bg-blue-700 disabled:cursor-wait disabled:opacity-60"
              >
                <Save className="h-4 w-4" />
                <span>{isSaving ? 'Saving...' : 'Save Summary'}</span>
              </button>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <label className="mb-2 block text-sm font-medium text-gray-900" htmlFor="summary-overview">
            Overview
          </label>
          <textarea
            id="summary-overview"
            value={draft.overview}
            onChange={(event) => setDraft({ ...draft, overview: event.target.value })}
            rows={5}
            className="w-full resize-y rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
          />
        </div>

        <EditableList
          title="Key Topics"
          items={draft.key_topics}
          placeholder="Topic"
          onChange={(items) => setDraft({ ...draft, key_topics: items })}
        />
        <EditableList
          title="Decisions"
          items={draft.decisions}
          placeholder="Decision"
          onChange={(items) => setDraft({ ...draft, decisions: items })}
        />
        <EditableList
          title="Risks"
          items={draft.risks}
          placeholder="Risk or open question"
          onChange={(items) => setDraft({ ...draft, risks: items })}
        />
        <ActionItemEditor
          items={draft.action_items}
          onChange={(items) => setDraft({ ...draft, action_items: items })}
        />
      </div>
    );
  }

  if (!hasMeaningfulSummary) {
    return (
      <div className="max-w-5xl mx-auto space-y-4">
        {canEdit && (
          <div className="flex justify-end">
            <button
              type="button"
              onClick={startEditing}
              className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50"
            >
              <FileText className="h-4 w-4" />
              <span>Edit Summary</span>
            </button>
          </div>
        )}
        <div className="flex items-center justify-center py-20 text-gray-500">
          <p>No concise meeting summary was generated for this session.</p>
        </div>
      </div>
    );
  }

  const displayedOverview = summary.overview.trim() || 'No meeting overview was generated for this session.';
  const displayedTopics = summary.key_topics.length ? summary.key_topics : ['No key topics extracted.'];
  const displayedDecisions = summary.decisions.length ? summary.decisions : ['No decisions extracted.'];
  const displayedRisks = summary.risks.length ? summary.risks : [];

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {canEdit && (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={startEditing}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50"
          >
            <FileText className="h-4 w-4" />
            <span>Edit Summary</span>
          </button>
        </div>
      )}

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-start gap-3 mb-4">
          <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
            <FileText className="w-5 h-5 text-blue-600" />
          </div>
          <div className="flex-1">
            <h2 className="text-gray-900 mb-2">Meeting Overview</h2>
            <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-line">
              {displayedOverview}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 mt-4 pt-4 border-t border-gray-100">
          <div>
            <p className="text-xs text-gray-500 mb-1">Date</p>
            <p className="text-sm text-gray-900">{formatSessionDate(meetingDate)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-1">Duration</p>
            <p className="text-sm text-gray-900">{formatDuration(transcripts)}</p>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
            <TrendingUp className="w-5 h-5 text-purple-600" />
          </div>
          <h2 className="text-gray-900">Key Topics</h2>
        </div>

        <div className="space-y-2">
          {displayedTopics.map((topic, index) => (
            <div key={index} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg border border-gray-100">
              <div className="w-6 h-6 bg-purple-100 text-purple-600 rounded-full flex items-center justify-center flex-shrink-0 text-xs">
                {index + 1}
              </div>
              <p className="text-sm text-gray-700 flex-1">{topic}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
            <Target className="w-5 h-5 text-green-600" />
          </div>
          <h2 className="text-gray-900">Decisions Made</h2>
        </div>

        <div className="space-y-2">
          {displayedDecisions.map((decision, index) => (
            <div key={index} className="flex items-start gap-3 p-3 bg-green-50 rounded-lg border border-green-100">
              <div className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5">
                <svg className="w-full h-full" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <p className="text-sm text-gray-700 flex-1">{decision}</p>
            </div>
          ))}
        </div>
      </div>

      {displayedRisks.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-red-100 rounded-lg flex items-center justify-center">
              <Target className="w-5 h-5 text-red-600" />
            </div>
            <h2 className="text-gray-900">Risks and Open Questions</h2>
          </div>

          <div className="space-y-2">
            {displayedRisks.map((risk, index) => (
              <div key={index} className="rounded-lg border border-red-100 bg-red-50 p-3 text-sm text-gray-700">
                {risk}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 bg-amber-100 rounded-lg flex items-center justify-center">
            <CheckCircle2 className="w-5 h-5 text-amber-600" />
          </div>
          <h2 className="text-gray-900">Follow-up Actions</h2>
        </div>

        {displayedActionItems.length > 0 ? (
          <div className="space-y-3">
            {displayedActionItems.map((item, index) => (
              <div key={index} className="p-4 rounded-lg border border-amber-100 bg-amber-50">
                <div className="flex items-start justify-between gap-4">
                  <p className="text-sm text-gray-900 flex-1">{item.task}</p>
                  <span className="px-2 py-1 rounded text-xs bg-white text-amber-700 border border-amber-200">
                    {item.status}
                  </span>
                </div>

                <div className="flex flex-wrap gap-2 mt-3 text-xs text-gray-500">
                  <span className="px-2 py-1 rounded-full bg-white border border-gray-200">
                    Owner: {item.assignee}
                  </span>
                  <span className="px-2 py-1 rounded-full bg-white border border-gray-200">
                    Deadline: {item.deadline}
                  </span>
                  <span className="px-2 py-1 rounded-full bg-white border border-gray-200">
                    Source: {formatTranscriptReference(item, transcripts)}
                  </span>
                  <span className="px-2 py-1 rounded-full bg-white border border-gray-200">
                    Confidence: {Math.round(item.confidence * 100)}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-4 rounded-lg border border-dashed border-gray-200 bg-gray-50 text-sm text-gray-500">
            No follow-up actions extracted.
          </div>
        )}
      </div>
    </div>
  );
}
