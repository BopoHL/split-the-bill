import { useEffect, useEffectEvent, useState } from 'react';
import { useStore } from '@/lib/store/useStore';
import { sameDetails } from '@/lib/utils/paymentDetails';
import { createPaymentMethod, deletePaymentMethod, listPaymentMethods } from '@/lib/api/paymentMethods';
import { track, AnalyticsEvent } from '@/lib/analytics';
import type { PaymentMethod } from '@/types/api';

/**
 * The signed-in person's saved payment details, loaded once and kept in step
 * with what they add and remove. `onLoad` hears the list as it arrives, for a
 * caller that preselects from it.
 */
export function useSavedPaymentMethods(onLoad?: (methods: PaymentMethod[]) => void) {
  const userId = useStore((s) => s.currentUser?.id);
  const [methods, setMethods] = useState<PaymentMethod[]>([]);
  // Until the list is in, nothing can be said about which card is picked —
  // showing the empty field first and then swapping it for the list flickered.
  const [loaded, setLoaded] = useState(false);
  const heard = useEffectEvent((list: PaymentMethod[]) => onLoad?.(list));

  useEffect(() => {
    if (!userId) return;
    let cancelled = false;
    listPaymentMethods(userId)
      .then((list) => {
        if (cancelled) return;
        setMethods(list);
        heard(list);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [userId]);

  /** Keeps details for next time; ones already kept are not kept twice. */
  const add = async (value: string) => {
    if (!userId || methods.some((method) => sameDetails(method.value, value))) return;
    try {
      const created = await createPaymentMethod(userId, { value });
      setMethods((previous) => [...previous, created]);
      track(AnalyticsEvent.PaymentMethodSaved, {});
    } catch {
      // The details still go on the bill; they are only not remembered.
    }
  };

  const remove = async (id: number) => {
    if (!userId) return;
    setMethods((previous) => previous.filter((method) => method.id !== id));
    try {
      await deletePaymentMethod(userId, id);
      track(AnalyticsEvent.PaymentMethodDeleted, {});
    } catch {
      listPaymentMethods(userId).then(setMethods).catch(() => {});
    }
  };

  return { methods, loaded, add, remove };
}
