import { useRef, useState } from 'react';
import { formatDetails, sameDetails } from '@/lib/utils/paymentDetails';
import type { PaymentMethod } from '@/types/api';
import { useSavedPaymentMethods } from './useSavedPaymentMethods';

interface PaymentChoiceOptions {
  /** The details on the bill now, if any. */
  current?: string | null;
  /** Details to pick up front when the bill has none, such as the last ones used. */
  preferred?: string | null;
}

/**
 * Where the money goes: one of the saved cards, or another one typed in —
 * exactly one of them at a time. A card typed in is kept for next time when
 * `remember` is on, by `keep`.
 */
export function usePaymentChoice({ current, preferred }: PaymentChoiceOptions = {}) {
  const now = current?.trim() ?? '';
  // Details on the bill that are not among the saved ones stay in the field.
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [draft, setDraft] = useState(now);
  const [remember, setRemember] = useState(true);
  const touched = useRef(false);

  const saved = useSavedPaymentMethods((methods) => {
    if (touched.current) return;
    const matching = (details?: string | null) =>
      details ? methods.find((method) => sameDetails(method.value, details)) : undefined;
    const pick = now ? matching(now) : matching(preferred) ?? methods[0];
    if (!pick) return;
    setSelectedId(pick.id);
    setDraft('');
  });

  const selected = saved.methods.find((method) => method.id === selectedId);
  const isNew = !selected;
  const value = selected ? selected.value : draft.trim();

  const touch = () => { touched.current = true; };

  return {
    methods: saved.methods,
    /** The saved cards are in, so what is picked is settled. */
    ready: saved.loaded,
    selectedId: selected?.id ?? null,
    isNew,
    draft,
    remember,
    value,
    select: (method: PaymentMethod) => {
      touch();
      setSelectedId(method.id);
    },
    chooseNew: () => {
      touch();
      setSelectedId(null);
    },
    changeDraft: (input: string) => {
      touch();
      setSelectedId(null);
      setDraft(formatDetails(input));
    },
    setRemember,
    remove: (method: PaymentMethod) => {
      touch();
      if (method.id === selectedId) setSelectedId(null);
      void saved.remove(method.id);
    },
    /** Keeps a card typed in for next time, when asked to. */
    keep: async () => {
      if (isNew && remember && value) await saved.add(value);
    },
  };
}

export type PaymentChoice = ReturnType<typeof usePaymentChoice>;
