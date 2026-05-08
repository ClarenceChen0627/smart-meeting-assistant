import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { UploadMeetingControls } from '../src/app/components/UploadMeetingControls';

describe('UploadMeetingControls', () => {
  it('enables processing after a file is selected', async () => {
    const user = userEvent.setup();
    const onUpload = vi.fn();

    function ControlledUpload() {
      const [selectedFileName, setSelectedFileName] = useState<string | null>(null);

      return (
        <UploadMeetingControls
          inputKey={0}
          selectedFileName={selectedFileName}
          isUploading={false}
          disabled={false}
          onFileChange={(file) => setSelectedFileName(file?.name ?? null)}
          onUpload={onUpload}
        />
      );
    }

    render(<ControlledUpload />);

    expect(screen.getByRole('button', { name: /process upload/i })).toBeDisabled();

    const file = new File(['audio'], 'meeting.wav', { type: 'audio/wav' });
    await user.upload(screen.getByLabelText(/select one meeting audio file/i), file);

    expect(screen.getByText('meeting.wav')).toBeInTheDocument();
    const processButton = screen.getByRole('button', { name: /process upload/i });
    expect(processButton).toBeEnabled();
    await user.click(processButton);
    expect(onUpload).toHaveBeenCalledTimes(1);
  });

  it('shows a retry action for retained failed uploads', async () => {
    const user = userEvent.setup();
    const onUpload = vi.fn();

    render(
      <UploadMeetingControls
        inputKey={0}
        selectedFileName="meeting.wav"
        isUploading={false}
        disabled={false}
        isRetryAvailable
        onFileChange={vi.fn()}
        onUpload={onUpload}
      />
    );

    const retryButton = screen.getByRole('button', { name: /retry upload/i });
    expect(retryButton).toBeEnabled();
    await user.click(retryButton);
    expect(onUpload).toHaveBeenCalledTimes(1);
  });
});
