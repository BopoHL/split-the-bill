/**
 * Validate a scanned QR string is an Uzbek fiscal (Soliq) check link and
 * normalise it to the https URL the backend will import from.
 *
 * The scanner can return any text, so this rejects anything that isn't an
 * ofd.soliq.uz check/epi link carrying the four receipt params (t, r, c, s).
 * Returns the canonical URL, or null when it isn't a Soliq receipt.
 */
const SOLIQ_HOST = 'ofd.soliq.uz';
const ALLOWED_PATHS = ['/check', '/epi'];
const REQUIRED_PARAMS = ['t', 'r', 'c', 's'];

export function parseSoliqUrl(raw: string): string | null {
  if (!raw || typeof raw !== 'string') return null;

  let url: URL;
  try {
    url = new URL(raw.trim());
  } catch {
    return null;
  }

  if (url.protocol !== 'https:' && url.protocol !== 'http:') return null;
  if (url.hostname.toLowerCase() !== SOLIQ_HOST) return null;
  const path = url.pathname || '/';
  if (!ALLOWED_PATHS.some((p) => path === p || path.startsWith(`${p}/`))) return null;
  if (!REQUIRED_PARAMS.every((k) => url.searchParams.has(k))) return null;

  url.protocol = 'https:';
  url.hash = '';
  return url.toString();
}

export function isSoliqUrl(raw: string): boolean {
  return parseSoliqUrl(raw) !== null;
}
