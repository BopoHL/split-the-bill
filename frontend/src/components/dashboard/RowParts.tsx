'use client';

import { useState, type ReactNode } from 'react';
import { Trash2 } from 'lucide-react';
import { useTranslation } from '@/lib/i18n/useTranslation';

/** A list's title, how many it holds or what it adds up to, and a dashed rule. */
export function SectionHeading({ title, count, total }: { title: string; count?: number; total?: string }) {
  return (
    <div className="mb-3 flex items-center gap-2.5">
      <h2 className="font-display text-[12px] font-bold uppercase tracking-[0.14em] text-muted">{title}</h2>
      {count !== undefined && (
        <span className="font-mono text-[12px] font-bold text-foreground">{String(count).padStart(2, '0')}</span>
      )}
      <span className="h-0 flex-1 border-t-[1.5px] border-dashed border-border" aria-hidden />
      {total && <span className="shrink-0 font-mono text-[12px] font-bold text-foreground">{total}</span>}
    </div>
  );
}

/** The rows of one list on a card, a dashed rule between them. */
export function RowsCard({ children, quiet = false }: { children: ReactNode; quiet?: boolean }) {
  return (
    <div
      className={`divide-y-[1.5px] divide-dashed divide-border rounded-lg border-[1.5px] bg-surface ${
        quiet ? 'border-border' : 'border-outline'
      }`}
    >
      {children}
    </div>
  );
}

/** The bin: asks right in the row whether to delete the bill. */
export function DeleteButton({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={t('home.deleteBill')}
      aria-expanded={open}
      className={`relative flex h-8 w-7 shrink-0 items-center justify-center rounded-md transition-colors after:absolute after:left-1/2 after:top-1/2 after:size-11 after:-translate-x-1/2 after:-translate-y-1/2 hover:bg-surface-2 hover:text-danger ${
        open ? 'text-danger' : 'text-muted'
      }`}
    >
      <Trash2 className="h-[18px] w-[18px]" />
    </button>
  );
}

/** «Delete this bill?» asked right in the row, as the old cards did. */
export function DeleteConfirm({ onCancel, onConfirm }: { onCancel: () => void; onConfirm: () => Promise<void> }) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);

  const confirm = async () => {
    setBusy(true);
    try {
      await onConfirm();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-2 border-t-[1.5px] border-dashed border-border px-3.5 py-2">
      <span className="mr-auto text-[13px] font-medium text-foreground">{t('home.deleteQuestion')}</span>
      <button
        type="button"
        onClick={onCancel}
        className="min-h-10 rounded-md px-3 font-mono text-[11px] font-medium uppercase tracking-wide text-muted transition-colors hover:bg-surface-2"
      >
        {t('common.cancel')}
      </button>
      <button
        type="button"
        onClick={() => void confirm()}
        disabled={busy}
        className="min-h-10 rounded-md border-[1.5px] border-danger px-3 font-mono text-[11px] font-bold uppercase tracking-wide text-danger transition-colors hover:bg-danger/10 disabled:opacity-60"
      >
        {t('common.delete')}
      </button>
    </div>
  );
}

/** The owner's face, or the first letter of their name. */
export function OwnerFace({ name, avatarUrl }: { name: string | null | undefined; avatarUrl: string | null | undefined }) {
  return (
    <span className="flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-md border-[1.5px] border-outline bg-surface font-display text-[13px] font-bold text-foreground">
      {avatarUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={avatarUrl} alt="" className="h-full w-full object-cover" />
      ) : (
        (name || '?').charAt(0).toUpperCase()
      )}
    </span>
  );
}
