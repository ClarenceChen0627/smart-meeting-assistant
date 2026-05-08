import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { TranscriptPanel } from '../src/app/components/TranscriptPanel';

const transcripts = [
  {
    id: 't-0',
    transcript_index: 0,
    speaker: 'Speaker 1',
    speaker_is_final: true,
    transcript_is_final: true,
    text: 'Hello.',
    start: 0,
    end: 1,
  },
  {
    id: 't-1',
    transcript_index: 1,
    speaker: 'Speaker 2',
    speaker_is_final: true,
    transcript_is_final: true,
    text: 'I will send the notes.',
    start: 1,
    end: 3,
  },
  {
    id: 't-2',
    transcript_index: 2,
    speaker: 'Speaker 3',
    speaker_is_final: true,
    transcript_is_final: true,
    text: 'Agreed.',
    start: 3,
    end: 4,
  },
];

describe('TranscriptPanel', () => {
  it('submits speaker rename and merge updates', async () => {
    const user = userEvent.setup();
    const onSaveSpeakerUpdates = vi.fn().mockResolvedValue(undefined);

    render(
      <TranscriptPanel
        isRecording={false}
        currentLanguage="en"
        transcripts={transcripts}
        canEditSpeakers
        onSaveSpeakerUpdates={onSaveSpeakerUpdates}
      />
    );

    await user.click(screen.getByRole('button', { name: /edit speakers/i }));
    await user.clear(screen.getByLabelText(/speaker label for speaker 1/i));
    await user.type(screen.getByLabelText(/speaker label for speaker 1/i), 'Alice');
    await user.clear(screen.getByLabelText(/speaker label for speaker 3/i));
    await user.type(screen.getByLabelText(/speaker label for speaker 3/i), 'Alice');
    await user.click(screen.getByRole('button', { name: /save speakers/i }));

    await waitFor(() => {
      expect(onSaveSpeakerUpdates).toHaveBeenCalledWith([
        { from: 'Speaker 1', to: 'Alice' },
        { from: 'Speaker 3', to: 'Alice' },
      ]);
    });
  });

  it('rejects empty speaker labels before saving', async () => {
    const user = userEvent.setup();
    const onSaveSpeakerUpdates = vi.fn();

    render(
      <TranscriptPanel
        isRecording={false}
        currentLanguage="en"
        transcripts={transcripts}
        canEditSpeakers
        onSaveSpeakerUpdates={onSaveSpeakerUpdates}
      />
    );

    await user.click(screen.getByRole('button', { name: /edit speakers/i }));
    await user.clear(screen.getByLabelText(/speaker label for speaker 2/i));
    await user.click(screen.getByRole('button', { name: /save speakers/i }));

    expect(screen.getByText(/speaker names cannot be empty/i)).toBeInTheDocument();
    expect(onSaveSpeakerUpdates).not.toHaveBeenCalled();
  });
});
