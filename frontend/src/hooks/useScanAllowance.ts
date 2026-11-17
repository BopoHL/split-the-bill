import { useEffect } from 'react';
import { usePro } from '@/lib/store/usePro';
import { useStore } from '@/lib/store/useStore';

export interface ScanAllowance {
  left: number;
  total: number;
}

/**
 * Today's free scans — photos and Soliq QR codes together — or null with Pro,
 * where there is no limit. Asked for afresh wherever it is shown: a scan that
 * failed gives its turn back.
 */
export function useScanAllowance(): ScanAllowance | null {
  const userId = useStore((state) => state.currentUser?.id);
  const left = usePro((state) => state.overview?.scans_left_today ?? null);
  const total = usePro((state) => state.overview?.free_scans_per_day ?? 0);
  const load = usePro((state) => state.load);

  useEffect(() => {
    if (userId) void load(userId);
  }, [userId, load]);

  return left === null ? null : { left, total };
}
