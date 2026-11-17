/**
 * The app's themes. Light and dark are everyone's; the rest come with Pro, and
 * without it each gives way to the free one of its own lightness — the server
 * draws the pictures by the same rule. The choice itself is kept.
 */
export const THEMES = [
  { id: 'light', scheme: 'light', pro: false },
  { id: 'dark', scheme: 'dark', pro: false },
  { id: 'nord', scheme: 'dark', pro: true },
  { id: 'nord_frost', scheme: 'light', pro: true },
  { id: 'sakura', scheme: 'light', pro: true },
  { id: 'midnight', scheme: 'dark', pro: true },
] as const;

export type Theme = (typeof THEMES)[number]['id'];
export type ColorScheme = 'light' | 'dark';

const byId = new Map<string, (typeof THEMES)[number]>(THEMES.map((theme) => [theme.id, theme]));

export function isTheme(value: unknown): value is Theme {
  return typeof value === 'string' && byId.has(value);
}

export function schemeOf(theme: Theme): ColorScheme {
  return byId.get(theme)!.scheme;
}

export function isProTheme(theme: Theme): boolean {
  return byId.get(theme)!.pro;
}

/** The theme the app is drawn in: the chosen one, unless it is Pro's and Pro is locked. */
export function shownTheme(chosen: Theme, proLocked: boolean): Theme {
  return isProTheme(chosen) && proLocked ? schemeOf(chosen) : chosen;
}
