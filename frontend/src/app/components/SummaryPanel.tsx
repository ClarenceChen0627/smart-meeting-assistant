import { FileText, Users, Target, TrendingUp, AlertTriangle } from 'lucide-react';
import type { MeetingSummary } from '../../types';

interface SummaryPanelProps {
  summary: MeetingSummary | null;
}

export function SummaryPanel({ summary }: SummaryPanelProps) {
  if (!summary) {
    return (
      <div className="max-w-5xl mx-auto flex items-center justify-center py-20 text-gray-500">
        <div className="text-center">
          <FileText className="w-12 h-12 text-gray-300 mx-auto mb-3" />
          <p>Meeting summary will appear here after the session is finalized.</p>
        </div>
      </div>
    );
  }

  const hasTodos = summary.todos && summary.todos.length > 0;
  const hasDecisions = summary.decisions && summary.decisions.length > 0;
  const hasRisks = summary.risks && summary.risks.length > 0;

  if (!hasTodos && !hasDecisions && !hasRisks) {
    return (
      <div className="max-w-5xl mx-auto flex items-center justify-center py-20 text-gray-500">
        <p>No actionable summary items were extracted from this meeting.</p>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Decisions Made */}
      {hasDecisions && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
              <Target className="w-5 h-5 text-green-600" />
            </div>
            <h2 className="text-gray-900">Decisions Made</h2>
          </div>

          <div className="space-y-2">
            {summary.decisions.map((decision, index) => (
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
      )}

      {/* Todos / Key Topics */}
      {hasTodos && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
              <TrendingUp className="w-5 h-5 text-purple-600" />
            </div>
            <h2 className="text-gray-900">Action Items / To-Dos</h2>
          </div>

          <div className="space-y-2">
            {summary.todos.map((todo, index) => (
              <div key={index} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg border border-gray-100">
                <div className="w-6 h-6 bg-purple-100 text-purple-600 rounded-full flex items-center justify-center flex-shrink-0 text-xs">
                  {index + 1}
                </div>
                <p className="text-sm text-gray-700 flex-1">{todo}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Risks */}
      {hasRisks && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-red-100 rounded-lg flex items-center justify-center">
              <AlertTriangle className="w-5 h-5 text-red-600" />
            </div>
            <h2 className="text-gray-900">Risks / Blockers</h2>
          </div>

          <div className="space-y-2">
            {summary.risks.map((risk, index) => (
              <div key={index} className="flex items-start gap-3 p-3 bg-red-50 rounded-lg border border-red-100">
                <div className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5">
                  <AlertTriangle className="w-full h-full" />
                </div>
                <p className="text-sm text-gray-700 flex-1">{risk}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
