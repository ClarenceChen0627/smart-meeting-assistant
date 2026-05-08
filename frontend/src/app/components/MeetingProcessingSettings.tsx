import { useEffect, useRef, useState } from 'react';
import { BookOpenText, Check, ChevronDown, Pencil, Plus, Trash2, X } from 'lucide-react';

import type { GlossaryTermCreate, GlossaryTermRecord, GlossaryTermUpdate } from '../../types';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';

interface MeetingProcessingSettingsProps {
  glossaryTerms: string;
  disabled?: boolean;
  onGlossaryTermsChange: (terms: string) => void;
  globalGlossaryTerms?: GlossaryTermRecord[];
  isGlossaryLoading?: boolean;
  glossaryError?: string;
  onCreateGlobalTerm?: (term: GlossaryTermCreate) => Promise<void> | void;
  onUpdateGlobalTerm?: (termId: string, term: GlossaryTermUpdate) => Promise<void> | void;
  onDeleteGlobalTerm?: (termId: string) => Promise<void> | void;
}

interface TermDraft {
  term: string;
  replacement: string;
  note: string;
}

const emptyDraft: TermDraft = {
  term: '',
  replacement: '',
  note: '',
};

const countGlossaryTerms = (value: string) =>
  value
    .split(/[\n;]+/)
    .map((term) => term.trim())
    .filter(Boolean).length;

export function MeetingProcessingSettings({
  glossaryTerms,
  disabled = false,
  onGlossaryTermsChange,
  globalGlossaryTerms = [],
  isGlossaryLoading = false,
  glossaryError,
  onCreateGlobalTerm,
  onUpdateGlobalTerm,
  onDeleteGlobalTerm,
}: MeetingProcessingSettingsProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [newTerm, setNewTerm] = useState<TermDraft>(emptyDraft);
  const [editingTermId, setEditingTermId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<TermDraft>(emptyDraft);
  const [localError, setLocalError] = useState<string | null>(null);
  const [savingTermId, setSavingTermId] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const glossaryTermCount = countGlossaryTerms(glossaryTerms) + globalGlossaryTerms.length;

  const normalizeDraft = (draft: TermDraft): GlossaryTermCreate => ({
    term: draft.term.trim(),
    replacement: draft.replacement.trim() || null,
    note: draft.note.trim() || null,
  });

  const handleCreateTerm = async () => {
    if (!onCreateGlobalTerm) {
      return;
    }
    const payload = normalizeDraft(newTerm);
    if (!payload.term) {
      setLocalError('Term is required.');
      return;
    }
    try {
      setLocalError(null);
      setSavingTermId('new');
      await onCreateGlobalTerm(payload);
      setNewTerm(emptyDraft);
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : 'Failed to save term.');
    } finally {
      setSavingTermId(null);
    }
  };

  const startEditing = (term: GlossaryTermRecord) => {
    setEditingTermId(term.id);
    setEditDraft({
      term: term.term,
      replacement: term.replacement ?? '',
      note: term.note ?? '',
    });
    setLocalError(null);
  };

  const handleUpdateTerm = async (termId: string) => {
    if (!onUpdateGlobalTerm) {
      return;
    }
    const payload = normalizeDraft(editDraft);
    if (!payload.term) {
      setLocalError('Term is required.');
      return;
    }
    try {
      setLocalError(null);
      setSavingTermId(termId);
      await onUpdateGlobalTerm(termId, payload);
      setEditingTermId(null);
      setEditDraft(emptyDraft);
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : 'Failed to update term.');
    } finally {
      setSavingTermId(null);
    }
  };

  const handleDeleteTerm = async (termId: string) => {
    if (!onDeleteGlobalTerm) {
      return;
    }
    try {
      setLocalError(null);
      setSavingTermId(termId);
      await onDeleteGlobalTerm(termId);
      if (editingTermId === termId) {
        setEditingTermId(null);
        setEditDraft(emptyDraft);
      }
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : 'Failed to delete term.');
    } finally {
      setSavingTermId(null);
    }
  };

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setIsOpen((value) => !value)}
        disabled={disabled}
        aria-expanded={isOpen}
        className={`flex items-center gap-2 rounded-lg bg-gray-100 px-4 py-2 text-sm text-gray-700 transition-colors ${
          disabled ? 'cursor-not-allowed opacity-50' : 'hover:bg-gray-200'
        }`}
      >
        <BookOpenText className="h-4 w-4" />
        <span>Terms</span>
        {glossaryTermCount > 0 && (
          <span className="rounded-full border border-blue-100 bg-blue-50 px-1.5 py-0.5 text-[10px] leading-none text-blue-700">
            {glossaryTermCount}
          </span>
        )}
        <ChevronDown className={`h-4 w-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className="absolute right-0 z-50 mt-2 w-[28rem] max-w-[calc(100vw-2rem)] rounded-lg border border-gray-200 bg-white p-3 shadow-lg">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-gray-900">Saved glossary</p>
              <p className="text-xs text-gray-500">{isGlossaryLoading ? 'Loading terms...' : `${globalGlossaryTerms.length} saved terms`}</p>
            </div>
          </div>

          {(glossaryError || localError) && (
            <p className="mb-3 rounded-md border border-red-200 bg-red-50 px-2 py-1 text-xs text-red-700">
              {localError || glossaryError}
            </p>
          )}

          <div className="mb-3 max-h-56 space-y-2 overflow-auto">
            {globalGlossaryTerms.map((term) => {
              const isEditing = editingTermId === term.id;
              const isSaving = savingTermId === term.id;
              return (
                <div key={term.id} className="rounded-md border border-gray-200 p-2">
                  {isEditing ? (
                    <div className="space-y-2">
                      <Input
                        value={editDraft.term}
                        disabled={disabled || isSaving}
                        aria-label="Edit glossary term"
                        onChange={(event) => setEditDraft((draft) => ({ ...draft, term: event.target.value }))}
                        className="h-8 text-xs"
                      />
                      <Input
                        value={editDraft.replacement}
                        disabled={disabled || isSaving}
                        aria-label="Edit glossary replacement"
                        onChange={(event) => setEditDraft((draft) => ({ ...draft, replacement: event.target.value }))}
                        className="h-8 text-xs"
                      />
                      <Input
                        value={editDraft.note}
                        disabled={disabled || isSaving}
                        aria-label="Edit glossary note"
                        onChange={(event) => setEditDraft((draft) => ({ ...draft, note: event.target.value }))}
                        className="h-8 text-xs"
                      />
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          disabled={disabled || isSaving}
                          onClick={() => {
                            setEditingTermId(null);
                            setEditDraft(emptyDraft);
                          }}
                          className="inline-flex items-center gap-1 rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <X className="h-3.5 w-3.5" />
                          <span>Cancel</span>
                        </button>
                        <button
                          type="button"
                          disabled={disabled || isSaving}
                          onClick={() => {
                            void handleUpdateTerm(term.id);
                          }}
                          className="inline-flex items-center gap-1 rounded-md bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <Check className="h-3.5 w-3.5" />
                          <span>Save</span>
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-xs font-medium text-gray-900">{term.term}</p>
                        {(term.replacement || term.note) && (
                          <p className="mt-0.5 truncate text-xs text-gray-500">
                            {[term.replacement ? `=> ${term.replacement}` : null, term.note].filter(Boolean).join(' · ')}
                          </p>
                        )}
                      </div>
                      <div className="flex shrink-0 gap-1">
                        <button
                          type="button"
                          disabled={disabled || isSaving}
                          onClick={() => startEditing(term)}
                          className="rounded-md p-1 text-gray-500 hover:bg-gray-100 hover:text-gray-700 disabled:cursor-not-allowed disabled:opacity-50"
                          aria-label={`Edit glossary term ${term.term}`}
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          disabled={disabled || isSaving}
                          onClick={() => {
                            void handleDeleteTerm(term.id);
                          }}
                          className="rounded-md p-1 text-gray-500 hover:bg-red-50 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-50"
                          aria-label={`Delete glossary term ${term.term}`}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="mb-3 rounded-md border border-gray-200 p-2">
            <p className="mb-2 text-xs font-medium text-gray-900">Add saved term</p>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <Input
                value={newTerm.term}
                disabled={disabled || savingTermId === 'new'}
                placeholder="Term"
                aria-label="New glossary term"
                onChange={(event) => setNewTerm((draft) => ({ ...draft, term: event.target.value }))}
                className="h-8 text-xs"
              />
              <Input
                value={newTerm.replacement}
                disabled={disabled || savingTermId === 'new'}
                placeholder="Replacement"
                aria-label="New glossary replacement"
                onChange={(event) => setNewTerm((draft) => ({ ...draft, replacement: event.target.value }))}
                className="h-8 text-xs"
              />
              <Input
                value={newTerm.note}
                disabled={disabled || savingTermId === 'new'}
                placeholder="Note"
                aria-label="New glossary note"
                onChange={(event) => setNewTerm((draft) => ({ ...draft, note: event.target.value }))}
                className="h-8 text-xs"
              />
            </div>
            <button
              type="button"
              disabled={disabled || savingTermId === 'new'}
              onClick={() => {
                void handleCreateTerm();
              }}
              className="mt-2 inline-flex items-center gap-1 rounded-md bg-gray-900 px-2 py-1 text-xs text-white hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>Add term</span>
            </button>
          </div>

          <label className="mb-2 block text-xs text-gray-500" htmlFor="glossary-terms">
            Meeting terminology
          </label>
          <Textarea
            id="glossary-terms"
            value={glossaryTerms}
            disabled={disabled}
            onChange={(event) => onGlossaryTermsChange(event.target.value)}
            placeholder="Qwen => Tongyi Qianwen; OKR: objectives and key results"
            className="min-h-24 bg-gray-50 text-xs"
          />
        </div>
      )}
    </div>
  );
}
