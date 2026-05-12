import { describe, expect, it } from 'vitest';

import { normalizeMeetingTags } from '../src/app/components/MeetingHistorySheet';

describe('normalizeMeetingTags', () => {
  it('deduplicates, trims, limits, and truncates prompted meeting tags', () => {
    const tags = normalizeMeetingTags(
      [
        ' Customer  Success ',
        'customer success',
        'Launch    Review',
        'This tag name is intentionally longer than thirty two characters',
        ...Array.from({ length: 25 }, (_, index) => `Tag ${index}`),
      ].join(',')
    );

    expect(tags).toHaveLength(20);
    expect(tags[0]).toBe('Customer Success');
    expect(tags[1]).toBe('Launch Review');
    expect(tags[2]).toBe('This tag name is intentionally l');
    expect(tags.every((tag) => tag.length <= 32)).toBe(true);
  });
});
