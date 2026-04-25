import { FileAudio, Loader2, Upload } from 'lucide-react';

import { Button } from './ui/button';
import { Input } from './ui/input';

interface UploadMeetingControlsProps {
  inputKey: number;
  selectedFileName: string | null;
  isUploading: boolean;
  disabled: boolean;
  onFileChange: (file: File | null) => void;
  onUpload: () => void;
}

export function UploadMeetingControls({
  inputKey,
  selectedFileName,
  isUploading,
  disabled,
  onFileChange,
  onUpload,
}: UploadMeetingControlsProps) {
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-gray-200 bg-gray-50 p-3 sm:min-w-[380px]">
      <div className="flex items-center gap-2 text-sm text-gray-600">
        <FileAudio className="h-4 w-4" />
        <span>{selectedFileName ?? 'Select one meeting audio file to process'}</span>
      </div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          key={inputKey}
          type="file"
          accept="audio/*,.wav,.mp3,.ogg,.opus,.m4a,.webm"
          disabled={disabled || isUploading}
          onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
          className="bg-white"
        />
        <Button
          type="button"
          onClick={onUpload}
          disabled={disabled || isUploading || !selectedFileName}
          className="sm:min-w-[160px]"
        >
          {isUploading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Uploading...</span>
            </>
          ) : (
            <>
              <Upload className="h-4 w-4" />
              <span>Process Upload</span>
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
