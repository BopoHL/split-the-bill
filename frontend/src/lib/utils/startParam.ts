export interface SeatInviteStartParam {
  participantId: number;
  token: string;
  confirmPayment: boolean;
}

function parsedSeatInvite(
  match: RegExpMatchArray | null,
  confirmPayment: boolean,
): SeatInviteStartParam | null {
  if (!match) return null;

  const participantId = Number(match[1]);
  const token = match[2];
  if (!Number.isSafeInteger(participantId) || participantId <= 0 || !token) {
    return null;
  }

  return { participantId, token, confirmPayment };
}

export interface InviteStartParam {
  code: string;
  confirmPayment: boolean;
}

/**
 * `inv_<code>` — a minted invite, optionally suffixed `_pay` for the personal
 * seat invite whose button also confirms payment.
 */
export function parseInviteStartParam(
  startParam: string | null | undefined,
): InviteStartParam | null {
  const match = startParam?.match(/^inv_([A-Za-z0-9_-]+?)(_pay)?$/);
  if (!match) return null;
  return { code: match[1], confirmPayment: !!match[2] };
}

export function parseSeatInviteStartParam(
  startParam: string | null | undefined,
): SeatInviteStartParam | null {
  return (
    parsedSeatInvite(startParam?.match(/^seat_open_(\d+)_(.+)$/) ?? null, false) ??
    parsedSeatInvite(startParam?.match(/^seat_(\d+)_(.+)$/) ?? null, true)
  );
}

export interface BillStartParam {
  token: string;
  /** Land on the receipt sheet with the QR scanner ready, not just the bill. */
  scan: boolean;
}

/**
 * Links the bot sends for a bill the user already owns: `bill_<token>` opens it,
 * `scan_<token>` opens it on the scanner. Distinct from `join_`, which enrols
 * the opener as a participant — the owner is already in.
 */
export function parseBillStartParam(
  startParam: string | null | undefined,
): BillStartParam | null {
  const scanning = startParam?.match(/^scan_(.+)$/);
  if (scanning) return { token: scanning[1], scan: true };

  const opening = startParam?.match(/^bill_(.+)$/);
  if (opening) return { token: opening[1], scan: false };

  return null;
}

/** The start parameter that opens the app straight on the paywall. */
export const PRO_START = 'pro';

export type StartKind = 'none' | 'invite' | 'seat' | 'join' | 'bill' | 'scan' | 'pro' | 'source' | 'other';

/** `src_<channel>` on a link we hand out — a post, an ad, a broadcast — to
 *  tell which brought someone in. */
const SOURCE_PREFIX = 'src_';
const SOURCE_MAX = 64;

const START_KINDS: ReadonlyArray<[prefix: string, kind: StartKind]> = [
  [SOURCE_PREFIX, 'source'],
  ['inv_', 'invite'],
  ['seat_', 'seat'],
  ['join_', 'join'],
  ['bill_', 'bill'],
  ['scan_', 'scan'],
];

/** The channel a `src_` link names, kept to what an analytics label can be. */
export function startSource(startParam: string | null | undefined): string | null {
  if (!startParam?.startsWith(SOURCE_PREFIX)) return null;
  const source = startParam.slice(SOURCE_PREFIX.length).toLowerCase().replace(/[^a-z0-9_-]/g, '').slice(0, SOURCE_MAX);
  return source || null;
}

/** Which way into the app a start parameter is, without the token it carries. */
export function startParamKind(startParam: string | null | undefined): StartKind {
  if (!startParam) return 'none';
  if (startParam === PRO_START) return 'pro';
  return START_KINDS.find(([prefix]) => startParam.startsWith(prefix))?.[1] ?? 'other';
}
