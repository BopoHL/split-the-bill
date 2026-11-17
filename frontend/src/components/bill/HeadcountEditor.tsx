'use client';

import { useState } from 'react';
import { Check, Minus, Pencil, Plus, X } from 'lucide-react';
import type { BillDetail } from '@/types/api';
import { updateBill } from '@/lib/api/bills';
import { MAX_PEOPLE } from '@/lib/constants';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { showToast } from '@/lib/toast';
import { translateApiError } from '@/lib/utils/apiError';
import { peopleUnit } from '@/lib/utils/plural';
import NumericKeypad from '@/components/ui/NumericKeypad';
import { track, AnalyticsEvent } from '@/lib/analytics';

const STEP_BUTTON =
  'flex w-9 items-center justify-center bg-surface text-foreground transition-colors hover:bg-accent hover:text-accent-fg active:translate-y-px disabled:opacity-50';

/** The owner's inline editor for how many people the bill expects (STB-182). */
export default function HeadcountEditor({ bill, userId, onBillUpdate }: {
  bill: BillDetail;
  userId: number;
  onBillUpdate: (bill: BillDetail) => void;
}) {
  const { t, language } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [keypadOpen, setKeypadOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const seated = bill.participants.length;
  const minimum = seated || 1;
  const draftCount = parseInt(draft, 10);

  const open = () => {
    setDraft(String(bill.expected_people ?? seated));
    setEditing(true);
  };

  const close = () => {
    setEditing(false);
    setKeypadOpen(false);
  };

  const nudge = (delta: number) => {
    const base = Number.isNaN(draftCount) ? 0 : draftCount;
    setDraft(String(Math.min(MAX_PEOPLE, Math.max(minimum, base + delta))));
  };

  const save = async () => {
    if (!Number.isFinite(draftCount) || draftCount < minimum || draftCount === bill.expected_people) {
      close();
      return;
    }
    setSaving(true);
    try {
      onBillUpdate(await updateBill(bill.id, { expected_people: draftCount, user_id: userId }));
      track(AnalyticsEvent.BillEdited, { bill_id: bill.id, field: 'headcount' });
      close();
    } catch (error: unknown) {
      console.error(error);
      showToast(
        translateApiError((error as { response?: { data?: { detail?: string } } })?.response?.data?.detail, t),
      );
    } finally {
      setSaving(false);
    }
  };

  if (!editing) {
    return (
      <span className="flex items-center gap-1 font-mono text-[12px] tracking-normal text-foreground">
        {seated}
        <button
          type="button"
          onClick={open}
          aria-label={t('bill.editPeople')}
          title={t('bill.editPeople')}
          className="rounded p-0.5 text-muted-2 transition-colors hover:text-accent"
        >
          <Pencil className="h-3 w-3" />
        </button>
      </span>
    );
  }

  return (
    <span className="flex items-center gap-1.5 normal-case tracking-normal">
      <span className="flex h-9 items-stretch overflow-hidden rounded-[6px] border-[1.5px] border-outline">
        <button type="button" onClick={() => nudge(-1)} aria-label="−" disabled={saving} className={`${STEP_BUTTON} border-r-[1.5px] border-outline`}>
          <Minus className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={() => setKeypadOpen(true)}
          aria-label={t('bill.peopleCount')}
          className="flex min-w-[46px] items-center justify-center gap-1 bg-background px-2 font-mono text-[13px] font-bold text-foreground"
        >
          <span>{draft || '0'}</span>
          <span className="font-display text-[9px] font-bold uppercase tracking-[0.06em] text-muted-2">
            {peopleUnit(Number.isNaN(draftCount) ? 0 : draftCount, language)}
          </span>
        </button>
        <button type="button" onClick={() => nudge(1)} aria-label="+" disabled={saving} className={`${STEP_BUTTON} border-l-[1.5px] border-outline`}>
          <Plus className="h-3.5 w-3.5" />
        </button>
      </span>
      <button
        type="button"
        onClick={() => void save()}
        disabled={saving}
        aria-label={t('common.save')}
        className="btn-hard-sm flex h-9 w-9 items-center justify-center rounded-[6px] border-[1.5px] border-outline bg-success text-success-fg disabled:opacity-50"
      >
        <Check className="h-4 w-4" strokeWidth={2.5} />
      </button>
      <button
        type="button"
        onClick={close}
        disabled={saving}
        aria-label={t('common.cancel')}
        className="btn-hard-sm flex h-9 w-9 items-center justify-center rounded-[6px] border-[1.5px] border-outline bg-surface text-muted"
      >
        <X className="h-4 w-4" />
      </button>
      <NumericKeypad
        open={keypadOpen}
        label={t('bill.peopleCount')}
        max={MAX_PEOPLE}
        value={draft}
        onChange={setDraft}
        onClose={() => setKeypadOpen(false)}
      />
    </span>
  );
}
