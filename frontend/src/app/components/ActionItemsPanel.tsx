import { Calendar, CheckCircle2, Circle, Clock, User } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { ActionItem as SummaryActionItem, MeetingSummary, TranscriptItem } from '../../types';

interface ActionItemViewModel extends SummaryActionItem {
  id: string;
  priority: 'high' | 'medium' | 'low';
  timestamp: string;
}

interface ActionItemsPanelProps {
  summary: MeetingSummary | null;
  transcripts?: TranscriptItem[];
}

const priorityColors = {
  high: 'bg-red-100 text-red-700 border-red-200',
  medium: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  low: 'bg-green-100 text-green-700 border-green-200'
};

const statusColors = {
  pending: 'text-gray-400',
  completed: 'text-green-500'
};

const inferPriority = (task: string): ActionItemViewModel['priority'] => {
  const normalized = task.toLowerCase();

  if (/\b(urgent|critical|blocker|risk|asap|high)\b/.test(normalized)) {
    return 'high';
  }

  if (/\b(optional|later|low)\b/.test(normalized)) {
    return 'low';
  }

  return 'medium';
};

const formatTimestamp = (item: SummaryActionItem, transcripts: TranscriptItem[]) => {
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

export function ActionItemsPanel({ summary, transcripts = [] }: ActionItemsPanelProps) {
  const [items, setItems] = useState<ActionItemViewModel[]>([]);

  useEffect(() => {
    if (summary?.action_items?.length) {
      setItems(summary.action_items
        .filter((item) => item.is_actionable)
        .map((item, index) => ({
          ...item,
          id: `action-${index}`,
          priority: inferPriority(item.task),
          timestamp: formatTimestamp(item, transcripts),
        })));
    } else {
      setItems([]);
    }
  }, [summary, transcripts]);

  const toggleStatus = (id: string) => {
    setItems((prev) => prev.map((item) => {
      if (item.id === id) {
        return { ...item, status: item.status === 'completed' ? 'pending' : 'completed' };
      }
      return item;
    }));
  };

  const pendingItems = items.filter((item) => item.status !== 'completed');
  const completedItems = items.filter((item) => item.status === 'completed');

  if (!summary) {
    return (
      <div className="max-w-5xl mx-auto flex items-center justify-center py-20 text-gray-500">
        <p>Meeting action items will appear here after the session is finalized.</p>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <p className="text-sm text-gray-500 mb-1">Total Action Items</p>
          <p className="text-gray-900">{items.length}</p>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <p className="text-sm text-gray-500 mb-1">Pending</p>
          <p className="text-gray-900">{pendingItems.length}</p>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <p className="text-sm text-gray-500 mb-1">Completed</p>
          <p className="text-gray-900">{completedItems.length}</p>
        </div>
      </div>

      {items.length === 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-6 text-sm text-gray-500">
          No follow-up actions were extracted from this meeting.
        </div>
      )}

      {pendingItems.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-gray-900">Pending Action Items</h2>
          </div>

          <div className="divide-y divide-gray-100">
            {pendingItems.map((item) => (
              <div key={item.id} className="p-6 hover:bg-gray-50 transition-colors">
                <div className="flex items-start gap-4">
                  <button
                    onClick={() => toggleStatus(item.id)}
                    className={`mt-1 flex-shrink-0 ${statusColors[item.status]}`}
                  >
                    <Circle className="w-5 h-5" />
                  </button>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-4 mb-2">
                      <h3 className="text-sm text-gray-900">{item.task}</h3>
                      <span className={`px-2 py-1 rounded text-xs border ${priorityColors[item.priority]}`}>
                        {item.priority}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-4 text-sm text-gray-500 mb-3">
                      <div className="flex items-center gap-1.5">
                        <User className="w-4 h-4" />
                        <span>{item.assignee}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Calendar className="w-4 h-4" />
                        <span>{item.deadline}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Clock className="w-4 h-4" />
                        <span>Extracted at {item.timestamp}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span>Confidence {Math.round(item.confidence * 100)}%</span>
                      </div>
                    </div>

                    <div className="bg-blue-50 border border-blue-100 rounded-lg p-3">
                      <p className="text-xs text-blue-600 mb-1">Extracted from transcript:</p>
                      <p className="text-sm text-gray-700 italic">"{item.source_excerpt}"</p>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {completedItems.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-gray-900">Completed Action Items</h2>
          </div>

          <div className="divide-y divide-gray-100">
            {completedItems.map((item) => (
              <div key={item.id} className="p-6 hover:bg-gray-50 transition-colors opacity-60">
                <div className="flex items-start gap-4">
                  <button
                    onClick={() => toggleStatus(item.id)}
                    className={`mt-1 flex-shrink-0 ${statusColors[item.status]}`}
                  >
                    <CheckCircle2 className="w-5 h-5" />
                  </button>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-4 mb-2">
                      <h3 className="text-sm text-gray-900 line-through">{item.task}</h3>
                      <span className={`px-2 py-1 rounded text-xs border ${priorityColors[item.priority]}`}>
                        {item.priority}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-4 text-sm text-gray-500">
                      <div className="flex items-center gap-1.5">
                        <User className="w-4 h-4" />
                        <span>{item.assignee}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Calendar className="w-4 h-4" />
                        <span>{item.deadline}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
