import { useEffect, useRef, useState } from 'react';
import { BookOpenText, ChevronDown } from 'lucide-react';

import { Textarea } from './ui/textarea';

interface MeetingProcessingSettingsProps {
  glossaryTerms: string;
  disabled?: boolean;
  onGlossaryTermsChange: (terms: string) => void;
}

const countGlossaryTerms = (value: string) =>
  value
    .split(/[\n;]+/)
    .map((term) => term.trim())
    .filter(Boolean).length;

export function MeetingProcessingSettings({
  glossaryTerms,
  disabled = false,
  onGlossaryTermsChange,
}: MeetingProcessingSettingsProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const glossaryTermCount = countGlossaryTerms(glossaryTerms);

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
        <div className="absolute right-0 z-50 mt-2 w-80 rounded-lg border border-gray-200 bg-white p-3 shadow-lg">
          <label className="mb-2 block text-xs text-gray-500" htmlFor="glossary-terms">
            Terminology
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
