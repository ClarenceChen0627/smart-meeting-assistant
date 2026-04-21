import { CheckCircle2, Circle } from 'lucide-react';
import { useState, useEffect } from 'react';
import type { MeetingSummary } from '../../types';

interface ActionItem {
  id: string;
  task: string;
  status: 'pending' | 'completed';
}

interface ActionItemsPanelProps {
  summary: MeetingSummary | null;
}

export function ActionItemsPanel({ summary }: ActionItemsPanelProps) {
  const [items, setItems] = useState<ActionItem[]>([]);

  useEffect(() => {
    if (summary && summary.todos) {
      setItems(summary.todos.map((todo, index) => ({
        id: `action-${index}`,
        task: todo,
        status: 'pending'
      })));
    } else {
      setItems([]);
    }
  }, [summary]);

  const toggleStatus = (id: string) => {
    setItems((prev) => prev.map(item => {
      if (item.id === id) {
        return { ...item, status: item.status === 'completed' ? 'pending' : 'completed' };
      }
      return item;
    }));
  };

  const pendingItems = items.filter(i => i.status !== 'completed');
  const completedItems = items.filter(i => i.status === 'completed');

  if (!summary) {
    return (
      <div className="max-w-5xl mx-auto flex items-center justify-center py-20 text-gray-500">
        <p>Meeting action items will appear here after the session is finalized.</p>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header Stats */}
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

      {/* Pending Action Items */}
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
                    className="mt-1 flex-shrink-0 text-gray-400 hover:text-blue-500"
                  >
                    <Circle className="w-5 h-5" />
                  </button>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-4 mb-2">
                       <h3 className="text-sm text-gray-900">{item.task}</h3>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Completed Action Items */}
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
                    className="mt-1 flex-shrink-0 text-green-500"
                  >
                    <CheckCircle2 className="w-5 h-5" />
                  </button>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-4 mb-2">
                      <h3 className="text-sm text-gray-900 line-through">{item.task}</h3>
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
