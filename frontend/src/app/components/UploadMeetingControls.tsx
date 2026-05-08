import { useState } from 'react';
import { FileAudio, Loader2, RefreshCw, Settings2, Upload } from 'lucide-react';

import { Button } from './ui/button';
import { Input } from './ui/input';

interface UploadMeetingControlsProps {
  inputKey: number;
  selectedFileName: string | null;
  isUploading: boolean;
  disabled: boolean;
  isRetryAvailable?: boolean;
  retainRawAudio?: boolean;
  onRetainRawAudioChange?: (enabled: boolean) => void;
  onFileChange: (file: File | null) => void;
  onUpload: () => void;
}

export function UploadMeetingControls({
  inputKey,
  selectedFileName,
  isUploading,
  disabled,
  isRetryAvailable = false,
  retainRawAudio = false,
  onRetainRawAudioChange = () => undefined,
  onFileChange,
  onUpload,
}: UploadMeetingControlsProps) {
  const canSubmit = Boolean(selectedFileName || isRetryAvailable);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const activeOptions = [
    retainRawAudio ? 'audio retained' : null,
  ].filter((item): item is string => Boolean(item));

  return (
    <div className="w-full max-w-[560px] rounded-lg border border-gray-200 bg-white p-2 shadow-sm">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-center gap-2 text-xs text-gray-500">
            <FileAudio className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{selectedFileName ?? 'Select meeting audio'}</span>
            {activeOptions.length > 0 && (
              <span className="hidden shrink-0 text-gray-400 sm:inline">
                {activeOptions.join(' / ')}
              </span>
            )}
          </div>
          <Input
            key={inputKey}
            type="file"
            aria-label="Select one meeting audio file"
            accept="audio/*,.wav,.mp3,.ogg,.opus,.m4a,.webm"
            disabled={disabled || isUploading}
            onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
            className="h-8 bg-gray-50 text-xs file:h-6 file:text-xs"
          />
        </div>

        <div className="flex items-center gap-2 lg:self-end">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setIsSettingsOpen((value) => !value)}
            disabled={disabled || isUploading}
            aria-expanded={isSettingsOpen}
            aria-label="Upload settings"
            className="h-8 w-8 p-0"
          >
            <Settings2 className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            onClick={onUpload}
            disabled={disabled || isUploading || !canSubmit}
            size="sm"
            aria-label={isRetryAvailable ? 'Retry Upload' : 'Process Upload'}
            className="h-8 min-w-[132px]"
          >
            {isUploading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Uploading</span>
              </>
            ) : isRetryAvailable ? (
              <>
                <RefreshCw className="h-4 w-4" />
                <span>Retry</span>
              </>
            ) : (
              <>
                <Upload className="h-4 w-4" />
                <span>Process</span>
              </>
            )}
          </Button>
        </div>
      </div>

      {isSettingsOpen && (
        <div className="mt-2 border-t border-gray-100 pt-2">
          <label className="flex items-center gap-2 text-xs text-gray-600" htmlFor="retain-raw-audio">
            <input
              id="retain-raw-audio"
              type="checkbox"
              checked={retainRawAudio}
              disabled={disabled || isUploading}
              onChange={(event) => onRetainRawAudioChange(event.target.checked)}
              className="h-4 w-4 rounded border-gray-300"
            />
            <span>Retain original audio</span>
          </label>
        </div>
      )}
    </div>
  );
}
