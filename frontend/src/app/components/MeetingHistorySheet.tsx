import { Archive, Check, CalendarDays, FileClock, Loader2, Pencil, Star, Tags, Trash2, X } from 'lucide-react';
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
  onMetadataUpdate: (
    meetingId: string,
    metadata: { favorite?: boolean; archived?: boolean; tags?: string[] }
  ) => Promise<void> | void;
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

export const normalizeMeetingTags = (value: string): string[] => {
  const tags: string[] = [];
  const seen = new Set<string>();
  for (const rawTag of value.split(',')) {
    const normalized = rawTag.replace(/\s+/g, ' ').trim();
    if (!normalized) {
      continue;
    }
    const tag = normalized.slice(0, 32);
    const key = tag.toLowerCase();
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    tags.push(tag);
    if (tags.length >= 20) {
      break;
    }
  }
  return tags;
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
  onMetadataUpdate,
  onRefresh,
}: MeetingHistorySheetProps) {
  const [editingMeetingId, setEditingMeetingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState('');
  const [renamingMeetingId, setRenamingMeetingId] = useState<string | null>(null);
  const [updatingMetadataMeetingId, setUpdatingMetadataMeetingId] = useState<string | null>(null);
  const [renameError, setRenameError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | MeetingHistoryListItem['status']>('all');
  const [sourceFilter, setSourceFilter] = useState<'all' | MeetingHistoryListItem['source_type']>('all');
  const [favoriteFilter, setFavoriteFilter] = useState<'all' | 'favorite'>('all');
  const [archivedFilter, setArchivedFilter] = useState<'active' | 'archived' | 'all'>('active');

  const filteredMeetings = meetings.filter((meeting) => {
    const query = searchTerm.trim().toLowerCase();
    if (query) {
      const searchable = [
        buildMeetingTitle(meeting),
        meeting.preview_text,
        meeting.source_name ?? '',
        meeting.provider,
        meeting.scene,
        ...meeting.tags,
      ].join(' ').toLowerCase();
      if (!searchable.includes(query)) {
        return false;
      }
    }
    if (statusFilter !== 'all' && meeting.status !== statusFilter) {
      return false;
    }
    if (sourceFilter !== 'all' && meeting.source_type !== sourceFilter) {
      return false;
    }
    if (favoriteFilter === 'favorite' && !meeting.favorite) {
      return false;
    }
    if (archivedFilter === 'active' && meeting.archived) {
      return false;
    }
    if (archivedFilter === 'archived' && !meeting.archived) {
      return false;
    }
    return true;
  });

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

  const updateMetadata = async (
    meetingId: string,
    metadata: { favorite?: boolean; archived?: boolean; tags?: string[] }
  ) => {
    try {
      setUpdatingMetadataMeetingId(meetingId);
      await onMetadataUpdate(meetingId, metadata);
    } finally {
      setUpdatingMetadataMeetingId(null);
    }
  };

  const editTags = (meeting: MeetingHistoryListItem) => {
    const value = window.prompt('Meeting tags, comma separated', meeting.tags.join(', '));
    if (value === null) {
      return;
    }
    const tags = normalizeMeetingTags(value);
    void updateMetadata(meeting.meeting_id, { tags });
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
            {filteredMeetings.length} of {meetings.length} saved meeting{meetings.length === 1 ? '' : 's'}
          </p>
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={isLoading}>
            Refresh
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 pb-4">
          <div className="sticky top-0 z-10 space-y-3 bg-white py-4">
            <input
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Search meetings"
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
            />
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}
                className="rounded-lg border border-gray-200 px-2 py-2 text-sm text-gray-700"
              >
                <option value="all">All statuses</option>
                <option value="draft">Draft</option>
                <option value="processing">Processing</option>
                <option value="failed">Failed</option>
                <option value="finalized">Finalized</option>
              </select>
              <select
                value={sourceFilter}
                onChange={(event) => setSourceFilter(event.target.value as typeof sourceFilter)}
                className="rounded-lg border border-gray-200 px-2 py-2 text-sm text-gray-700"
              >
                <option value="all">All sources</option>
                <option value="live">Live</option>
                <option value="upload">Upload</option>
              </select>
              <select
                value={favoriteFilter}
                onChange={(event) => setFavoriteFilter(event.target.value as typeof favoriteFilter)}
                className="rounded-lg border border-gray-200 px-2 py-2 text-sm text-gray-700"
              >
                <option value="all">All favorites</option>
                <option value="favorite">Favorites</option>
              </select>
              <select
                value={archivedFilter}
                onChange={(event) => setArchivedFilter(event.target.value as typeof archivedFilter)}
                className="rounded-lg border border-gray-200 px-2 py-2 text-sm text-gray-700"
              >
                <option value="active">Active</option>
                <option value="archived">Archived</option>
                <option value="all">All archive</option>
              </select>
            </div>
          </div>

          {isLoading && (
            <div className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-gray-200 py-12 text-sm text-gray-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading meeting history...
            </div>
          )}

          {!isLoading && filteredMeetings.length === 0 && (
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-gray-200 py-12 text-center">
              <FileClock className="mb-3 h-10 w-10 text-gray-300" />
              <p className="text-sm text-gray-600">No meetings match this view.</p>
              <p className="mt-1 text-xs text-gray-500">Live and upload meetings will appear here as they are processed.</p>
            </div>
          )}

          {!isLoading && filteredMeetings.length > 0 && (
            <div className="space-y-3 pt-4">
              {filteredMeetings.map((meeting) => {
                const isSelected = selectedMeetingId === meeting.meeting_id;
                const isOpening = loadingMeetingId === meeting.meeting_id;
                const isDeleting = deletingMeetingId === meeting.meeting_id;
                const isEditing = editingMeetingId === meeting.meeting_id;
                const isRenaming = renamingMeetingId === meeting.meeting_id;
                const isUpdatingMetadata = updatingMetadataMeetingId === meeting.meeting_id;

                return (
                  <div
                    key={meeting.meeting_id}
                    className={`rounded-xl border p-4 transition-colors ${
                      isSelected ? 'border-blue-300 bg-blue-50/60' : 'border-gray-200 bg-white'
                    }`}
                  >
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={`rounded-full border px-2 py-0.5 text-xs ${statusClasses[meeting.status]}`}>
                            {meeting.status}
                          </span>
                          <span className={`rounded-full border px-2 py-0.5 text-xs uppercase ${sourceClasses[meeting.source_type]}`}>
                            {meeting.source_type}
                          </span>
                          {meeting.favorite && (
                            <span className="rounded-full border border-yellow-200 bg-yellow-50 px-2 py-0.5 text-xs text-yellow-700">
                              favorite
                            </span>
                          )}
                          {meeting.archived && (
                            <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-600">
                              archived
                            </span>
                          )}
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
                            <h3 className="break-words text-sm font-medium text-gray-900">
                              {buildMeetingTitle(meeting)}
                            </h3>
                          </button>
                        )}

                        <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-gray-500 sm:gap-4">
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
                          <p className="mt-2 break-all text-xs text-gray-500">File: {meeting.source_name}</p>
                        )}
                        {meeting.tags.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1">
                            {meeting.tags.map((tag) => (
                              <span key={tag} className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                                {tag}
                              </span>
                            ))}
                          </div>
                        )}
                        {meeting.error_message && (
                          <p className="mt-2 text-xs text-red-600">{meeting.error_message}</p>
                        )}
                        {isEditing && renameError && (
                          <p className="mt-2 text-xs text-red-600">{renameError}</p>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center justify-end gap-2 sm:justify-start">
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
                        <button
                          type="button"
                          onClick={() => {
                            void updateMetadata(meeting.meeting_id, { favorite: !meeting.favorite });
                          }}
                          disabled={isDeleting || isUpdatingMetadata}
                          className={`rounded-lg border p-2 transition-colors disabled:cursor-wait disabled:opacity-60 ${
                            meeting.favorite
                              ? 'border-yellow-200 bg-yellow-50 text-yellow-600 hover:bg-yellow-100'
                              : 'border-gray-200 text-gray-400 hover:border-yellow-200 hover:bg-yellow-50 hover:text-yellow-600'
                          }`}
                          aria-label={meeting.favorite ? 'Remove from favorites' : 'Add to favorites'}
                        >
                          <Star className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => editTags(meeting)}
                          disabled={isDeleting || isUpdatingMetadata}
                          className="rounded-lg border border-gray-200 p-2 text-gray-400 transition-colors hover:border-blue-200 hover:bg-blue-50 hover:text-blue-600 disabled:cursor-wait disabled:opacity-60"
                          aria-label="Edit meeting tags"
                        >
                          <Tags className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            void updateMetadata(meeting.meeting_id, { archived: !meeting.archived });
                          }}
                          disabled={isDeleting || isUpdatingMetadata}
                          className={`rounded-lg border p-2 transition-colors disabled:cursor-wait disabled:opacity-60 ${
                            meeting.archived
                              ? 'border-slate-300 bg-slate-100 text-slate-700 hover:bg-slate-200'
                              : 'border-gray-200 text-gray-400 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-700'
                          }`}
                          aria-label={meeting.archived ? 'Restore meeting record' : 'Archive meeting record'}
                        >
                          {isUpdatingMetadata ? <Loader2 className="h-4 w-4 animate-spin" /> : <Archive className="h-4 w-4" />}
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
