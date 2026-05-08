import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { MeetingProcessingSettings } from '../src/app/components/MeetingProcessingSettings';

describe('MeetingProcessingSettings', () => {
  it('shows glossary term count and updates terms', async () => {
    const user = userEvent.setup();
    const onGlossaryTermsChange = vi.fn();

    render(
      <MeetingProcessingSettings
        glossaryTerms={'Qwen => Tongyi Qianwen\nOKR'}
        onGlossaryTermsChange={onGlossaryTermsChange}
      />
    );

    expect(screen.getByText('2')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /terms/i }));
    await user.type(screen.getByLabelText(/terminology/i), ';SMA');

    expect(onGlossaryTermsChange).toHaveBeenCalled();
  });

  it('creates, edits, and deletes saved glossary terms', async () => {
    const user = userEvent.setup();
    const onCreateGlobalTerm = vi.fn().mockResolvedValue(undefined);
    const onUpdateGlobalTerm = vi.fn().mockResolvedValue(undefined);
    const onDeleteGlobalTerm = vi.fn().mockResolvedValue(undefined);

    render(
      <MeetingProcessingSettings
        glossaryTerms=""
        globalGlossaryTerms={[
          {
            id: 'term-1',
            term: 'Qwen',
            replacement: 'Tongyi Qianwen',
            note: null,
            created_at: '2026-05-09T00:00:00Z',
            updated_at: '2026-05-09T00:00:00Z',
          },
        ]}
        onGlossaryTermsChange={vi.fn()}
        onCreateGlobalTerm={onCreateGlobalTerm}
        onUpdateGlobalTerm={onUpdateGlobalTerm}
        onDeleteGlobalTerm={onDeleteGlobalTerm}
      />
    );

    await user.click(screen.getByRole('button', { name: /terms/i }));
    expect(screen.getByText('1 saved terms')).toBeInTheDocument();

    await user.type(screen.getByLabelText(/new glossary term/i), 'OKR');
    await user.type(screen.getByLabelText(/new glossary note/i), 'Objectives and key results');
    await user.click(screen.getByRole('button', { name: /add term/i }));
    await waitFor(() => {
      expect(onCreateGlobalTerm).toHaveBeenCalledWith({
        term: 'OKR',
        replacement: null,
        note: 'Objectives and key results',
      });
    });

    await user.click(screen.getByRole('button', { name: /edit glossary term qwen/i }));
    await user.clear(screen.getByLabelText(/edit glossary replacement/i));
    await user.type(screen.getByLabelText(/edit glossary replacement/i), 'Qwen model');
    await user.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => {
      expect(onUpdateGlobalTerm).toHaveBeenCalledWith('term-1', {
        term: 'Qwen',
        replacement: 'Qwen model',
        note: null,
      });
    });

    await user.click(screen.getByRole('button', { name: /delete glossary term qwen/i }));
    await waitFor(() => {
      expect(onDeleteGlobalTerm).toHaveBeenCalledWith('term-1');
    });
  });
});
