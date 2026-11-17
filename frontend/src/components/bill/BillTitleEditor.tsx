'use client';

import { useEffect, useRef, useState } from 'react';
import { Pencil, Check, X, Loader2 } from 'lucide-react';
import { updateBill } from '@/lib/api/bills';
import type { BillDetail, User } from '@/types/api';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { track, AnalyticsEvent } from '@/lib/analytics';

interface Props {
  bill: BillDetail;
  currentUser: User;
  setBill: (b: BillDetail) => void;
  /** Visible only when this is true (i.e. for the bill owner). */
  canEdit: boolean;
}

const MAX_LEN = 100;

export default function BillTitleEditor({
  bill,
  currentUser,
  setBill,
  canEdit,
}: Props) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(bill.title || '');
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) {
      // focus + select-all so a single tap can replace OR a single
      // keystroke can keep typing from the existing value
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  const start = () => {
    setDraft(bill.title || '');
    setEditing(true);
  };

  const cancel = () => {
    setEditing(false);
    setDraft(bill.title || '');
  };

  const save = async () => {
    const next = draft.trim().slice(0, MAX_LEN);
    if (next === (bill.title || '')) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      const updated = await updateBill(bill.id, {
        title: next || null,
        user_id: currentUser.id,
      });
      setBill(updated);
      track(AnalyticsEvent.BillEdited, { bill_id: bill.id, field: 'title' });
      setEditing(false);
    } catch (err) {
      console.error('Failed to rename bill', err);
    } finally {
      setSaving(false);
    }
  };

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      void save();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      cancel();
    }
  };

  if (editing) {
    return (
      <div className="flex items-center gap-1 max-w-[260px]">
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKey}
          maxLength={MAX_LEN}
          disabled={saving}
          className="text-base font-medium text-foreground bg-surface-2 border border-border rounded-lg focus:border-accent outline-none px-2.5 py-1.5 min-w-0 flex-1"
        />
        <button
          type="button"
          onClick={save}
          disabled={saving}
          aria-label={t('bill.renameSave')}
          className="rounded-lg p-1.5 text-accent transition hover:bg-white/10 disabled:opacity-50"
        >
          {saving ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Check className="w-4 h-4" />
          )}
        </button>
        <button
          type="button"
          onClick={cancel}
          disabled={saving}
          aria-label={t('common.cancel')}
          className="rounded-lg p-1.5 text-bar-fg opacity-70 transition hover:bg-white/10 hover:opacity-100"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1 min-w-0">
      <h1 className="max-w-[200px] truncate font-display text-base font-semibold text-bar-fg">
        {bill.title || t('bill.untitled')}
      </h1>
      {canEdit && (
        <button
          type="button"
          onClick={start}
          aria-label={t('bill.renameBill')}
          title={t('bill.renameBill')}
          className="shrink-0 rounded-lg p-1.5 text-bar-fg opacity-60 transition hover:bg-white/10 hover:opacity-100"
        >
          <Pencil className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}
