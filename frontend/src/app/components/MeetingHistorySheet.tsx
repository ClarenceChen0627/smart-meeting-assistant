import { Check, CalendarDays, FileClock, Loader2, Pencil, Trash2, X } from 'lucide-react';
import { useState } from 'react';

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
  onRename: (meetingId: string, title: string) => Promise<void> | void;
  onRefresh: () => void;
}

const statusClasses: Record<MeetingHistoryListItem['status'], string> = {
  draft: 'bg-amber-100 text-amber-700 border-amber-200',
  processing: 'bg-blue-100 text-blue-700 border-blue-200',
  failed: 'bg-red-100 text-red-700 border-red-200',
  finalized: 'bg-green-100 text-green-700 border-green-200',
};

const sourceClasses: Record<MeetingHistoryListItem['source_type'], string> = {
  live: 'bg-slate-100 text-slate-700 border-slate-200',
  upload: 'bg-violet-100 text-violet-700 border-violet-200',
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

const buildMeetingTitle = (meeting: MeetingHistoryListItem) => {
  const title = meeting.title.trim();
  if (title) {
    return title;
  }

  if (meeting.source_name) {
    return meeting.source_name.replace(/\.[^/.]+$/, '');
  }

  return `${sceneLabels[meeting.scene] || meeting.scene} ${formatTimestamp(meeting.created_at)}`;
};

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
  onRename,
  onRefresh,
}: MeetingHistorySheetProps) {
  const [editingMeetingId, setEditingMeetingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState('');
  const [renamingMeetingId, setRenamingMeetingId] = useState<string | null>(null);
  const [renameError, setRenameError] = useState<string | null>(null);

  const startRename = (meeting: MeetingHistoryListItem) => {
    setEditingMeetingId(meeting.meeting_id);
    setDraftTitle(buildMeetingTitle(meeting));
    setRenameError(null);
  };

  const cancelRename = () => {
    setEditingMeetingId(null);
    setDraftTitle('');
    setRenameError(null);
  };

  const saveRename = async (meetingId: string) => {
    const normalizedTitle = draftTitle.trim();
    if (!normalizedTitle) {
      setRenameError('Meeting title cannot be empty.');
      return;
    }

    try {
      setRenamingMeetingId(meetingId);
      setRenameError(null);
      await onRename(meetingId, normalizedTitle);
      cancelRename();
    } catch (error) {
      setRenameError(error instanceof Error ? error.message : 'Failed to rename meeting.');
    } finally {
      setRenamingMeetingId(null);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-xl">
        <SheetHeader className="border-b border-gray-200">
          <SheetTitle>Meeting History</SheetTitle>
          <SheetDescription>
            Review saved live and uploaded meeting transcripts, summaries, action items, and analysis.
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
              <p className="mt-1 text-xs text-gray-500">Live and upload meetings will appear here as they are processed.</p>
            </div>
          )}

          {!isLoading && meetings.length > 0 && (
            <div className="space-y-3 pt-4">
              {meetings.map((meeting) => {
                const isSelected = selectedMeetingId === meeting.meeting_id;
                const isOpening = loadingMeetingId === meeting.meeting_id;
                const isDeleting = deletingMeetingId === meeting.meeting_id;
                const isEditing = editingMeetingId === meeting.meeting_id;
                const isRenaming = renamingMeetingId === meeting.meeting_id;

                return (
                  <div
                    key={meeting.meeting_id}
                    className={`rounded-xl border p-4 transition-colors ${
                      isSelected ? 'border-blue-300 bg-blue-50/60' : 'border-gray-200 bg-white'
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className={`rounded-full border px-2 py-0.5 text-xs ${statusClasses[meeting.status]}`}>
                            {meeting.status}
                          </span>
                          <span className={`rounded-full border px-2 py-0.5 text-xs uppercase ${sourceClasses[meeting.source_type]}`}>
                            {meeting.source_type}
                          </span>
                          <span className="text-xs text-gray-500">{sceneLabels[meeting.scene] || meeting.scene}</span>
                          {meeting.target_lang && (
                            <span className="text-xs text-gray-400">Translate: {meeting.target_lang.toUpperCase()}</span>
                          )}
                        </div>

                        {isEditing ? (
                          <form
                            className="mt-3 flex items-center gap-2"
                            onSubmit={(event) => {
                              event.preventDefault();
                              void saveRename(meeting.meeting_id);
                            }}
                          >
                            <input
                              autoFocus
                              value={draftTitle}
                              maxLength={80}
                              onChange={(event) => setDraftTitle(event.target.value)}
                              onKeyDown={(event) => {
                                if (event.key === 'Escape') {
                                  event.preventDefault();
                                  cancelRename();
                                }
                              }}
                              disabled={isRenaming}
                              className="min-w-0 flex-1 rounded-lg border border-blue-200 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                            />
                            <button
                              type="submit"
                              disabled={isRenaming}
                              className="rounded-lg border border-green-200 p-2 text-green-600 transition-colors hover:bg-green-50 disabled:cursor-wait disabled:opacity-60"
                              aria-label="Save meeting title"
                            >
                              {isRenaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                            </button>
                            <button
                              type="button"
                              onClick={cancelRename}
                              disabled={isRenaming}
                              className="rounded-lg border border-gray-200 p-2 text-gray-500 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
                              aria-label="Cancel meeting title edit"
                            >
                              <X className="h-4 w-4" />
                            </button>
                          </form>
                        ) : (
                          <button
                            type="button"
                            onClick={() => onSelect(meeting.meeting_id)}
                            disabled={isOpening || isDeleting}
                            className="mt-3 block w-full text-left disabled:cursor-wait"
                          >
                            <h3 className="text-sm font-medium text-gray-900">
                              {buildMeetingTitle(meeting)}
                            </h3>
                          </button>
                        )}

                        <div className="mt-2 flex items-center gap-4 text-xs text-gray-500">
                          <span className="flex items-center gap-1">
                            <CalendarDays className="h-3.5 w-3.5" />
                            {formatTimestamp(meeting.updated_at)}
                          </span>
                          <span>{meeting.transcript_count} transcript{meeting.transcript_count === 1 ? '' : 's'}</span>
                          <span>{meeting.provider}</span>
                          {meeting.processing_stage && (
                            <span>Stage: {meeting.processing_stage}</span>
                          )}
                        </div>

                        <p className="mt-3 line-clamp-2 text-sm text-gray-600">
                          {meeting.preview_text || 'No summary preview available yet.'}
                        </p>
                        {meeting.source_name && (
                          <p className="mt-2 text-xs text-gray-500">File: {meeting.source_name}</p>
                        )}
                        {meeting.error_message && (
                          <p className="mt-2 text-xs text-red-600">{meeting.error_message}</p>
                        )}
                        {isEditing && renameError && (
                          <p className="mt-2 text-xs text-red-600">{renameError}</p>
                        )}
                      </div>

                      <div className="flex items-center gap-2">
                        {isOpening && <Loader2 className="h-4 w-4 animate-spin text-gray-400" />}
                        <button
                          type="button"
                          onClick={() => startRename(meeting)}
                          disabled={isDeleting || isRenaming}
                          className="rounded-lg border border-gray-200 p-2 text-gray-400 transition-colors hover:border-blue-200 hover:bg-blue-50 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-60"
                          aria-label="Rename meeting record"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
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
