import { useCallback, useEffect, useRef, useState } from 'react';
import type { Bill, BillCounts } from '@/types/api';
import { getBillCounts, getUserBills, type BillRoleFilter } from '@/lib/api/bills';
import { createSessionCache } from '@/lib/cache/sessionCache';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { showToast } from '@/lib/toast';
import { useDebouncedValue } from './useDebouncedValue';

const PAGE_SIZE = 15;
const SEARCH_DELAY_MS = 300;

export interface Archive {
  query: string;
  setQuery: (query: string) => void;
  role: BillRoleFilter | undefined;
  setRole: (role: BillRoleFilter | undefined) => void;
  /** Whether a search or a role narrows what is shown. */
  narrowed: boolean;
  bills: Bill[];
  hasMore: boolean;
  loading: boolean;
  loadingMore: boolean;
  /** The search could not be loaded; `retry` asks again. */
  failed: boolean;
  retry: () => void;
  /** How many the current search finds, by role. */
  counts: BillCounts | null;
  /** How many closed bills there are in all, whatever is searched. */
  total: number;
  /** The newest closed bills, unfiltered — what the create wizard learns from. */
  recent: Bill[];
  loadMore: () => Promise<void>;
  /** Forget a bill the person deleted. */
  remove: (billId: number) => void;
}

/** What a search and a role find: its first page, whether that page came
 *  full — there may be more — and how many there are by role. */
interface Found {
  bills: Bill[];
  full: boolean;
  counts: BillCounts;
}

/** The pages past the first, for the search they were loaded for. */
interface More {
  key: string;
  bills: Bill[];
  hasMore: boolean;
}

// Every search and role looked at this session: going back to one shows it at
// once, and it is asked for again quietly in case anything changed since.
const seenFound = createSessionCache<Found>();
const foundKey = (userId: number | undefined, search: string, role: BillRoleFilter | undefined) =>
  `${userId}:${role ?? 'all'}:${search}`;

/** A deleted bill gone from what a search found — from its count too, when it
 *  was among the bills shown, on the first page or one loaded after. */
const withoutBill = (billId: number, shownFurther = false) => (found: Found): Found => {
  if (!shownFurther && !found.bills.some((bill) => bill.id === billId)) return found;
  // Only the owner deletes, so it was one of theirs.
  return {
    ...found,
    bills: found.bills.filter((bill) => bill.id !== billId),
    counts: { ...found.counts, all: found.counts.all - 1, owned: found.counts.owned - 1 },
  };
};

/** The closed bills, searched on the server and paged in as the person scrolls. */
export function useArchive(userId: number | undefined): Archive {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const search = useDebouncedValue(query.trim(), SEARCH_DELAY_MS);
  const [attempt, setAttempt] = useState(0);
  const [role, setRole] = useState<BillRoleFilter | undefined>();
  const [found, setFound] = useState(() => new Map(seenFound.entries()));
  const [more, setMore] = useState<More | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [failedKey, setFailedKey] = useState<string | null>(null);
  // While another search is on its way the last one stays up.
  const [shownKey, setShownKey] = useState<string | null>(null);
  // Only the answer to the newest search may land in «more»; an older one is dropped.
  const latestRequest = useRef(0);

  const key = foundKey(userId, search, role);
  if (found.has(key) && shownKey !== key) setShownKey(key);

  useEffect(() => {
    if (!userId) return;
    const request = ++latestRequest.current;
    const asked = foundKey(userId, search, role);
    const forgetFailure = () => setFailedKey((failed) => (failed === asked ? null : failed));
    forgetFailure();
    Promise.all([
      getUserBills(userId, 0, PAGE_SIZE, 'closed', { query: search, role }),
      getBillCounts(userId, 'closed', search),
    ])
      .then(([bills, counts]) => {
        const loaded = { bills, full: bills.length === PAGE_SIZE, counts };
        seenFound.set(asked, loaded);
        setFound((known) => new Map(known).set(asked, loaded));
        forgetFailure();
      })
      .catch((error) => {
        console.error('Error loading the archive:', error);
        if (request === latestRequest.current) setFailedKey(asked);
      });
  }, [userId, search, role, attempt]);

  const current = found.get(key) ?? (shownKey ? found.get(shownKey) : undefined);
  const extra = more?.key === key ? more : null;
  const bills = current ? [...current.bills, ...(extra?.bills ?? [])] : [];
  const hasMore = extra ? extra.hasMore : (found.get(key)?.full ?? false);
  const unfiltered = found.get(foundKey(userId, '', undefined));
  const unsearched = found.get(foundKey(userId, '', role));

  const loadMore = useCallback(async () => {
    if (!userId || loadingMore || !hasMore) return;
    const request = latestRequest.current;
    setLoadingMore(true);
    try {
      // From what is shown, not from a page number: a bill deleted meanwhile
      // would otherwise shift the next one out of reach.
      const next = await getUserBills(userId, bills.length, PAGE_SIZE, 'closed', { query: search, role });
      if (request !== latestRequest.current) return;
      setMore({ key, bills: [...(extra?.bills ?? []), ...next], hasMore: next.length === PAGE_SIZE });
    } catch (error) {
      // The button stays, to be pressed again.
      console.error('Error loading more of the archive:', error);
      showToast(t('common.error'));
    } finally {
      setLoadingMore(false);
    }
  }, [userId, loadingMore, hasMore, extra, bills.length, search, role, key, t]);

  const retry = useCallback(() => setAttempt((count) => count + 1), []);

  const remove = useCallback((billId: number) => {
    const furtherIn = more?.bills.some((bill) => bill.id === billId) ? more.key : null;
    const forget = (kept: string, value: Found) => withoutBill(billId, kept === furtherIn)(value);
    seenFound.update((value, kept) => forget(kept, value));
    setFound((known) => new Map([...known].map(([kept, value]) => [kept, forget(kept, value)])));
    setMore((loaded) => loaded && { ...loaded, bills: loaded.bills.filter((bill) => bill.id !== billId) });
  }, [more]);

  return {
    query,
    setQuery,
    role,
    setRole,
    narrowed: search !== '' || role !== undefined,
    bills,
    hasMore,
    loading: !found.has(key) && failedKey !== key,
    loadingMore,
    failed: !found.has(key) && failedKey === key,
    retry,
    counts: current?.counts ?? null,
    total: (unsearched ?? unfiltered)?.counts.all ?? 0,
    recent: unfiltered?.bills ?? [],
    loadMore,
    remove,
  };
}
