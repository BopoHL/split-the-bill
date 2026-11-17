import { describe, expect, it } from 'vitest';
import { isTheme, shownTheme, schemeOf, THEMES } from './themes';

describe('themes', () => {
  it('knows its themes and nothing else', () => {
    expect(THEMES.map((theme) => theme.id)).toEqual(['light', 'dark', 'nord', 'nord_frost', 'sakura', 'midnight']);
    expect(isTheme('nord_frost')).toBe(true);
    expect(isTheme('neon')).toBe(false);
    expect(isTheme(undefined)).toBe(false);
  });

  it('shows a Pro theme only while Pro is not locked, else its own lightness', () => {
    expect(shownTheme('nord', false)).toBe('nord');
    expect(['nord', 'nord_frost', 'sakura', 'midnight'].map((theme) => shownTheme(theme as never, true)))
      .toEqual(['dark', 'light', 'light', 'dark']);
    expect(shownTheme('dark', true)).toBe('dark');
    expect(schemeOf('midnight')).toBe('dark');
  });
});
