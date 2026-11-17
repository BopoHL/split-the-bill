import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

const setLanguage = vi.hoisted(() => vi.fn());

vi.mock('@/lib/store/useStore', () => {
  const state = { language: 'en', setLanguage };
  return {
    useStore: (selector?: (s: typeof state) => unknown) =>
      selector ? selector(state) : state,
  };
});

import LanguageStep from './LanguageStep';

describe('LanguageStep', () => {
  it('keeps clear of Telegram’s floating controls in fullscreen', () => {
    render(<LanguageStep onContinue={vi.fn()} />);

    const html = (document.querySelector('.fixed.inset-0') as HTMLElement).innerHTML;
    expect(html).toContain('var(--content-safe-top)');
    expect(html).toContain('var(--content-safe-bottom)');
  });

  it('switches the language on the spot', () => {
    render(<LanguageStep onContinue={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: /русский/i }));

    expect(setLanguage).toHaveBeenCalledWith('ru');
  });

  it('asks only for the language, then goes on to the tour', () => {
    const onContinue = vi.fn();
    render(<LanguageStep onContinue={onContinue} />);

    expect(screen.queryByRole('button', { name: /skip/i })).toBeNull();
    expect(screen.getAllByRole('button')).toHaveLength(4);
    fireEvent.click(screen.getByRole('button', { name: /next/i }));

    expect(onContinue).toHaveBeenCalledOnce();
  });
});
