/**
 * The badge by someone's name, by the server's rule: what they picked, Pro by
 * itself until they pick, Pro only while it lasts, or none at all.
 */
export const PRO_BADGE = 'pro';
export const NO_BADGE = 'none';

export function shownBadge(chosen: string | undefined | null, pro: boolean): string | null {
  if (chosen === NO_BADGE) return null;
  if (!chosen || chosen === PRO_BADGE) return pro ? PRO_BADGE : null;
  return chosen;
}
