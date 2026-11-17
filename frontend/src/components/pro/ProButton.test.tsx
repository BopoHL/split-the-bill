import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/i18n/useTranslation', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import { usePro } from '@/lib/store/usePro';
import ProButton from './ProButton';

describe('ProButton', () => {
  it('opens the paywall', () => {
    usePro.setState({ overview: null, paywall: null });
    render(<ProButton />);

    fireEvent.click(screen.getByRole('button', { name: 'pro.getPro' }));

    expect(usePro.getState().paywall).toBe('general');
  });
});
