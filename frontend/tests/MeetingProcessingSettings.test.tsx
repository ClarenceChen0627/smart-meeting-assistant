import { render, screen } from '@testing-library/react';
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
});
