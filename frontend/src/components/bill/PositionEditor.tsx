'use client';

import { useId, useState } from 'react';
import { Check, Trash2, X } from 'lucide-react';
import CountStepper from '@/components/ui/CountStepper';
import NumericKeypad from '@/components/ui/NumericKeypad';
import { evaluate } from '@/lib/utils/calc';
import { currencyLabel, formatCurrency, type Currency } from '@/lib/utils/currency';
import { translateApiError } from '@/lib/utils/apiError';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { showToast } from '@/lib/toast';

const CAPTION = 'mb-1 block font-display text-[10px] font-bold uppercase tracking-[0.12em] text-muted';

/**
 * Name, unit price and quantity of a receipt line. With several dishes the
 * total previews as price × quantity — or the line's actual `total` while
 * neither is touched, since a stored unit price is rounded down. A line being
 * edited can also be deleted from here — the only place it can be.
 *
 * Only a new line puts the cursor in its name: it has nothing to show yet.
 * One being edited opens as it is, keyboard down, until a field is tapped.
 */
export default function PositionEditor({ name = '', price, count = 1, total, currency, focusName = false, onSave, onCancel, onDelete }: {
  name?: string;
  price?: number;
  count?: number;
  total?: number;
  currency?: Currency;
  focusName?: boolean;
  onSave: (name: string, price: number, count: number) => void | Promise<void>;
  onCancel: () => void;
  onDelete?: () => void;
}) {
  const { t } = useTranslation();
  const id = useId();
  const [nameDraft, setNameDraft] = useState(name);
  const [priceDraft, setPriceDraft] = useState(price == null ? '' : String(price));
  const [countDraft, setCountDraft] = useState(String(count));
  const [keypad, setKeypad] = useState(false);
  const [busy, setBusy] = useState(false);
  const amount = evaluate(priceDraft);
  const quantity = Math.max(1, parseInt(countDraft, 10) || 1);
  const lineTotal = amount == null ? null : total != null && amount === price && quantity === count ? total : amount * quantity;
  const save = async () => {
    if (busy || !nameDraft.trim() || amount == null) return;
    setBusy(true);
    try { await onSave(nameDraft.trim(), amount, quantity); } catch (error) {
      showToast(translateApiError((error as { response?: { data?: { detail?: string } } }).response?.data?.detail, t));
    } finally { setBusy(false); }
  };
  return (
    <form onSubmit={(event) => { event.preventDefault(); void save(); }} className="space-y-2.5" data-no-swipe>
      <label htmlFor={`${id}-name`} className="sr-only">{t('bill.itemName')}</label>
      <input id={`${id}-name`} value={nameDraft} onChange={(event) => setNameDraft(event.target.value)} maxLength={200} autoFocus={focusName} disabled={busy} placeholder={t('bill.itemName')} className="min-h-11 w-full rounded-[6px] border-[1.5px] border-outline bg-background px-3 font-display text-[14px] outline-none focus:border-accent" />
      <div className="flex items-end gap-2">
        <div className="min-w-0 flex-1">
          <label htmlFor={`${id}-price`} className={CAPTION}>{quantity > 1 ? t('bill.pricePerUnit') : t('bill.price')}</label>
          <input id={`${id}-price`} value={priceDraft} onChange={(event) => { if (/^[-+×÷*/0-9.,\s]*$/.test(event.target.value)) setPriceDraft(event.target.value); }} inputMode="none" onFocus={() => setKeypad(true)} placeholder="0" disabled={busy} className="min-h-11 w-full rounded-[6px] border-[1.5px] border-outline bg-background px-3 font-mono text-[14px] outline-none focus:border-accent" />
        </div>
        <div role="group" aria-labelledby={`${id}-count`} className="shrink-0">
          <span id={`${id}-count`} className={CAPTION}>{t('bill.quantity')}</span>
          <CountStepper value={countDraft} onChange={setCountDraft} />
        </div>
      </div>
      <div className="flex items-center gap-2">
        {onDelete && <button type="button" aria-label={t('common.delete')} title={t('common.delete')} disabled={busy} onClick={onDelete} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[6px] border-[1.5px] border-danger bg-surface text-danger btn-hard-sm disabled:opacity-40"><Trash2 className="h-5 w-5" /></button>}
        <p aria-live="polite" className="min-w-0 flex-1 font-mono text-[12px] text-muted [overflow-wrap:anywhere]">
          {quantity > 1 && lineTotal != null && `${t('bill.lineTotal')}: ${formatCurrency(lineTotal, currency)}`}
        </p>
        <button type="submit" aria-label={t('common.save')} title={t('common.save')} disabled={busy || !nameDraft.trim() || amount == null} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[6px] border-[1.5px] border-outline bg-success text-success-fg btn-hard-sm disabled:opacity-40"><Check className="h-5 w-5" /></button>
        <button type="button" aria-label={t('common.cancel')} title={t('common.cancel')} disabled={busy} onClick={onCancel} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[6px] border-[1.5px] border-outline bg-surface text-muted btn-hard-sm"><X className="h-5 w-5" /></button>
      </div>
      <NumericKeypad open={keypad} label={t('bill.price')} value={priceDraft} onChange={setPriceDraft} onClose={() => setKeypad(false)} unit={currencyLabel(currency)} calculator />
    </form>
  );
}
