import { CalendarDays, FileClock, Loader2, Trash2 } from 'lucide-react';

import type { MeetingHistoryListItem } from '../../types';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from './ui/alert-dialog';
import { Button } from './ui/button';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from './ui/sheet';

interface MeetingHistorySheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  meetings: MeetingHistoryListItem[];
  isLoading: boolean;
  selectedMeetingId: string | null;
  loadingMeetingId: string | null;
  deletingMeetingId: string | null;
  onSelect: (meetingId: string) => void;
  onDelete: (meetingId: string) => void;
  onRefresh: () => void;
}

const statusClasses: Record<MeetingHistoryListItem['status'], string> = {
  draft: 'bg-amber-100 text-amber-700 border-amber-200',
  finalized: 'bg-green-100 text-green-700 border-green-200',
};

const sceneLabels: Record<string, string> = {
  general: 'General Meeting',
  finance: 'Finance Review',
  hr: 'HR / Interview',
};

const formatTimestamp = (value: string) =>
  new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));

export function MeetingHistorySheet({
  open,
  onOpenChange,
  meetings,
  isLoading,
  selectedMeetingId,
  loadingMeetingId,
  deletingMeetingId,
  onSelect,
  onDelete,
  onRefresh,
}: MeetingHistorySheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-xl">
        <SheetHeader className="border-b border-gray-200">
          <SheetTitle>Meeting History</SheetTitle>
          <SheetDescription>
            Review saved live transcripts, summaries, action items, and meeting analysis.
          </SheetDescription>
        </SheetHeader>

        <div className="flex items-center justify-between px-4 pt-4">
          <p className="text-sm text-gray-500">
            {meetings.length} saved meeting{meetings.length === 1 ? '' : 's'}
          </p>
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={isLoading}>
            Refresh
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 pb-4">
          {isLoading && (
            <div className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-gray-200 py-12 text-sm text-gray-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading meeting history...
            </div>
          )}

          {!isLoading && meetings.length === 0 && (
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-gray-200 py-12 text-center">
              <FileClock className="mb-3 h-10 w-10 text-gray-300" />
              <p className="text-sm text-gray-600">No meeting history yet.</p>
              <p className="mt-1 text-xs text-gray-500">Completed and draft meetings will appear here.</p>
            </div>
          )}

          {!isLoading && meetings.length > 0 && (
            <div className="space-y-3 pt-4">
              {meetings.map((meeting) => {
                const isSelected = selectedMeetingId === meeting.meeting_id;
                const isOpening = loadingMeetingId === meeting.meeting_id;
                const isDeleting = deletingMeetingId === meeting.meeting_id;

                return (
                  <div
                    key={meeting.meeting_id}
                    className={`rounded-xl border p-4 transition-colors ${
                      isSelected ? 'border-blue-300 bg-blue-50/60' : 'border-gray-200 bg-white'
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <button
                        type="button"
                        onClick={() => onSelect(meeting.meeting_id)}
                        disabled={isOpening || isDeleting}
                        className="flex-1 text-left"
                      >
                        <div className="flex items-center gap-2">
                          <span className={`rounded-full border px-2 py-0.5 text-xs ${statusClasses[meeting.status]}`}>
                            {meeting.status}
                          </span>
                          <span className="text-xs text-gray-500">{sceneLabels[meeting.scene] || meeting.scene}</span>
                          {meeting.target_lang && (
                            <span className="text-xs text-gray-400">Translate: {meeting.target_lang.toUpperCase()}</span>
                          )}
                        </div>

                        <div className="mt-3 flex items-center gap-4 text-xs text-gray-500">
                          <span className="flex items-center gap-1">
                            <CalendarDays className="h-3.5 w-3.5" />
                            {formatTimestamp(meeting.updated_at)}
                          </span>
                          <span>{meeting.transcript_count} transcript{meeting.transcript_count === 1 ? '' : 's'}</span>
                          <span>{meeting.provider}</span>
                        </div>

                        <p className="mt-3 text-sm text-gray-700">
                          {meeting.preview_text || 'No transcript preview available.'}
                        </p>
                      </button>

                      <div className="flex items-center gap-2">
                        {isOpening && <Loader2 className="h-4 w-4 animate-spin text-gray-400" />}
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <button
                              type="button"
                              disabled={isDeleting}
                              className="rounded-lg border border-gray-200 p-2 text-gray-400 transition-colors hover:border-red-200 hover:bg-red-50 hover:text-red-600"
                              aria-label="Delete meeting record"
                            >
                              {isDeleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                            </button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>Delete this meeting record?</AlertDialogTitle>
                              <AlertDialogDescription>
                                This permanently removes the transcript, summary, action items, and analysis for this meeting.
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>Cancel</AlertDialogCancel>
                              <AlertDialogAction
                                className="bg-red-600 hover:bg-red-700"
                                onClick={() => onDelete(meeting.meeting_id)}
                              >
                                Delete
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
