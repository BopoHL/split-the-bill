'use client';

import { useId, useState } from 'react';
import { Check, Loader2, MapPin, X } from 'lucide-react';
import type { BillDetail } from '@/types/api';
import { getPlaces, setBillPlace } from '@/lib/api/analytics';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { showToast } from '@/lib/toast';
import { track, AnalyticsEvent } from '@/lib/analytics';

/**
 * Where the bill was, under its title. The owner can name it — or change what
 * the receipt said — open or closed, since analytics count visits by it.
 */
export default function BillPlace({ bill, ownerId, canEdit, onChange }: {
  bill: BillDetail;
  ownerId: number;
  canEdit: boolean;
  onChange: (place: string | null) => void;
}) {
  const { t } = useTranslation();
  const listId = useId();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);

  if (!bill.place && !canEdit) return null;

  const start = () => {
    setDraft(bill.place ?? '');
    setEditing(true);
    getPlaces(ownerId).then(setSuggestions).catch(() => setSuggestions([]));
  };

  const save = async () => {
    setSaving(true);
    try {
      onChange(await setBillPlace(bill.id, draft.trim()));
      track(AnalyticsEvent.BillEdited, { bill_id: bill.id, field: 'place' });
      setEditing(false);
    } catch {
      showToast(t('common.error'));
    } finally {
      setSaving(false);
    }
  };

  if (editing) {
    return (
      <div className="mt-2 flex items-center justify-center gap-1.5">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') void save();
            if (event.key === 'Escape') setEditing(false);
          }}
          list={listId}
          maxLength={80}
          autoFocus
          aria-label={t('bill.place')}
          placeholder={t('bill.placePlaceholder')}
          className="min-w-0 max-w-[220px] rounded-md border-[1.5px] border-outline bg-background px-2.5 py-1.5 text-center text-[14px] text-foreground outline-none focus:border-accent"
        />
        <datalist id={listId}>
          {suggestions.map((name) => <option key={name} value={name} />)}
        </datalist>
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving}
          aria-label={t('common.save')}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border-[1.5px] border-success bg-success text-success-fg disabled:opacity-50"
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-[18px] w-[18px]" />}
        </button>
        <button
          type="button"
          onClick={() => setEditing(false)}
          aria-label={t('common.cancel')}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border-[1.5px] border-outline bg-surface text-muted hover:text-danger"
        >
          <X className="h-[18px] w-[18px]" />
        </button>
      </div>
    );
  }

  const label = (
    <>
      <MapPin className="h-3.5 w-3.5 shrink-0" />
      <span className="truncate">{bill.place ?? t('bill.addPlace')}</span>
    </>
  );

  return canEdit ? (
    <button
      type="button"
      onClick={start}
      aria-label={bill.place ? t('bill.changePlace', { place: bill.place }) : t('bill.addPlace')}
      className={`relative mx-auto mt-1.5 flex max-w-full items-center justify-center gap-1 font-mono text-[12px] after:absolute after:inset-x-0 after:top-1/2 after:h-10 after:-translate-y-1/2 ${
        bill.place ? 'text-foreground' : 'text-muted underline decoration-dotted underline-offset-2'
      }`}
    >
      {label}
    </button>
  ) : (
    <div className="mx-auto mt-1.5 flex max-w-full items-center justify-center gap-1 font-mono text-[12px] text-foreground">{label}</div>
  );
}
