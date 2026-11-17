'use client';

import { Check, DollarSign, Share2, UsersRound } from 'lucide-react';
import ProBadge from '@/components/pro/ProBadge';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { formatCurrency } from '@/lib/utils/currency';
import { isProTheme, type Theme } from '@/lib/utils/themes';

export type PreviewView = 'bill' | 'chat';

// A made-up dinner, the same in every theme so only the colours change.
const SUM = (amount: number) => formatCurrency(amount, 'uzs');
const SHARES = { you: 96_000, aziz: 74_000, dilya: 58_000 } as const;
const TOTAL = SHARES.you + SHARES.aziz + SHARES.dilya;
const LEFT = SHARES.dilya;

/**
 * The app as a theme would draw it: a bill's screen, or the bill's post in a
 * chat — made-up numbers, real colours. Drawn in the theme it is given,
 * whatever theme the app itself is in.
 */
export default function ThemePreview({ theme, view }: { theme: Theme; view: PreviewView }) {
  return view === 'bill' ? <BillScreen theme={theme} /> : <ChatPost theme={theme} />;
}

function Face({ letter, photo = false }: { letter: string; photo?: boolean }) {
  return (
    <span
      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] border-[1.5px] border-outline font-display text-[11px] font-bold shadow-[var(--shadow-hard-sm)] ${
        photo ? 'bg-accent text-accent-fg' : 'bg-surface text-foreground'
      }`}
    >
      {letter}
    </span>
  );
}

function Dish({ name, amount, shared = false }: { name: string; amount: number; shared?: boolean }) {
  const { t } = useTranslation();
  return (
    <span className="flex items-baseline gap-1.5 text-[11px] leading-tight">
      <span className="shrink-0">{name}</span>
      {shared && (
        <span className="inline-flex shrink-0 items-center gap-0.5 rounded-[4px] bg-accent-weak px-1 text-[9px] font-bold">
          <UsersRound className="h-2.5 w-2.5 text-accent" strokeWidth={2.5} />
          {t('bill.sharedSection')}
        </span>
      )}
      <span className="min-w-2 flex-1 translate-y-[-2px] border-b-[1.5px] border-dotted border-border" />
      <span className="shrink-0 font-mono text-[10.5px] font-bold tabular-nums">{SUM(amount)}</span>
    </span>
  );
}

function BillScreen({ theme }: { theme: Theme }) {
  const { t } = useTranslation();
  return (
    <div
      data-theme={theme}
      aria-hidden="true"
      className="flex h-[360px] flex-col overflow-hidden rounded-[20px] border-[1.5px] border-outline bg-background text-foreground shadow-[var(--shadow-hard)]"
    >
      <div className="flex items-center gap-2 bg-bar px-3.5 py-2.5 text-bar-fg">
        <span className="min-w-0 flex-1 truncate font-display text-[14px] font-bold">{t('settings.preview.title')}</span>
        <span className="flex h-7 w-7 items-center justify-center rounded-[6px] bg-accent text-accent-fg">
          <Share2 className="h-3.5 w-3.5" strokeWidth={2.5} />
        </span>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-2.5 p-3">
        <div className="grid grid-cols-2 rounded-lg border-[1.5px] border-outline bg-surface p-[3px] font-display text-[11px] font-bold shadow-[var(--shadow-hard-sm)]">
          <span className="rounded-[5px] bg-emphasis py-1.5 text-center text-emphasis-fg">{t('bill.participants')}</span>
          <span className="py-1.5 text-center text-muted">{t('bill.receipt')}</span>
        </div>

        <div className="divide-y-[1.5px] divide-dashed divide-border rounded-lg border-[1.5px] border-outline bg-surface shadow-[var(--shadow-hard)]">
          <div className="px-2.5 py-2">
            <div className="flex items-center gap-2">
              <Face letter={t('settings.preview.you').charAt(0)} photo />
              <span className="flex-1 font-display text-[13px] font-bold">{t('settings.preview.you')}</span>
              <span className="font-mono text-[12px] font-bold tabular-nums">{SUM(SHARES.you)}</span>
            </div>
            <div className="mt-1.5 flex flex-col gap-1 pl-9">
              <Dish name={`${t('settings.preview.plov')} ×2`} amount={84_000} />
              <Dish name={t('settings.preview.tea')} amount={12_000} shared />
            </div>
          </div>
          <div className="flex items-center gap-2 px-2.5 py-2">
            <Face letter={t('settings.preview.aziz').charAt(0)} />
            <span className="font-display text-[13px] font-bold">{t('settings.preview.aziz')}</span>
            <ProBadge />
            <span className="flex-1" />
            <span className="flex h-5 w-5 items-center justify-center rounded-[4px] border-[1.5px] border-outline bg-success text-success-fg">
              <DollarSign className="h-3 w-3" strokeWidth={3} />
            </span>
            <span className="font-mono text-[12px] font-bold tabular-nums text-success">{SUM(SHARES.aziz)}</span>
          </div>
          <div className="flex items-center gap-2 px-2.5 py-2">
            <Face letter={t('settings.preview.dilya').charAt(0)} />
            <span className="flex-1 font-display text-[13px] font-bold">{t('settings.preview.dilya')}</span>
            <span className="font-mono text-[12px] font-bold tabular-nums">{SUM(SHARES.dilya)}</span>
          </div>
        </div>
      </div>

      <div className="flex items-end gap-2 border-t-[1.5px] border-outline bg-background px-3 py-2.5">
        <span className="min-w-0 flex-1">
          <span className="block font-display text-[9px] font-bold uppercase tracking-[0.12em] text-muted">{t('bill.leftToCollect')}</span>
          <span className="block font-mono text-[18px] font-bold leading-tight tabular-nums">{SUM(LEFT)}</span>
          <span className="block font-mono text-[9.5px] text-muted">{t('bill.ownShare', { amount: SUM(SHARES.you) })}</span>
        </span>
        <span className="shrink-0 rounded-lg border-[1.5px] border-outline bg-success px-3 py-2 font-display text-[11px] font-bold text-success-fg shadow-[var(--shadow-hard-sm)]">
          {t('bill.closeBill')}
        </span>
      </div>
    </div>
  );
}

function ChatPost({ theme }: { theme: Theme }) {
  const { t } = useTranslation();
  const paid = SHARES.aziz;
  const people = [
    { key: 'you', dishes: `${t('settings.preview.plov')} ×2, ${t('settings.preview.tea')}`, amount: SHARES.you, paid: false },
    { key: 'aziz', dishes: `${t('settings.preview.samsa')} ×3, ${t('settings.preview.tea')}`, amount: SHARES.aziz, paid: true },
    { key: 'dilya', dishes: `${t('settings.preview.samsa')}, ${t('settings.preview.tea')}`, amount: SHARES.dilya, paid: false },
  ] as const;

  return (
    // Telegram's own chat, the same whatever the app's theme: only the card changes.
    <div aria-hidden="true" className="flex h-[360px] flex-col justify-end gap-1.5 overflow-hidden rounded-[20px] bg-[#9cb5c8] p-3 text-[#0f1419]">
      <div className="w-[94%] rounded-2xl rounded-bl-[6px] bg-white p-1.5 shadow-[0_1px_1px_rgba(0,0,0,0.15)]">
        <div data-theme={theme} className="rounded-xl bg-background p-2.5 text-foreground">
          <div className="rounded-lg border-[1.5px] border-outline bg-surface px-2.5 py-2 shadow-[var(--shadow-hard-sm)]">
            <div className="flex items-center gap-1.5">
              <span className="min-w-0 flex-1 truncate font-display text-[12px] font-extrabold">{t('settings.preview.title')}</span>
              <span className="shrink-0 font-mono text-[8.5px] text-muted">04.10 · 20:15</span>
              {isProTheme(theme) && <ProBadge className="h-[14px] px-[3px] text-[7px]" />}
            </div>
            <div className="mt-1.5 flex flex-col gap-1 border-t-[1.5px] border-dashed border-border pt-1.5">
              {people.map((person) => (
                <span key={person.key} className="flex items-center gap-1.5 text-[10px] leading-tight">
                  <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-[3px] border border-outline font-display text-[8px] font-bold">
                    {t(`settings.preview.${person.key}`).charAt(0)}
                  </span>
                  <span className="shrink-0 font-display font-bold">{t(`settings.preview.${person.key}`)}</span>
                  {person.paid && (
                    <span className="flex h-3 w-3 shrink-0 items-center justify-center rounded-[2px] bg-success text-success-fg">
                      <Check className="h-2 w-2" strokeWidth={4} />
                    </span>
                  )}
                  <span className="min-w-0 flex-1 truncate text-muted">{person.dishes}</span>
                  <span className="shrink-0 font-mono font-bold tabular-nums">{SUM(person.amount)}</span>
                </span>
              ))}
            </div>
            <div className="mt-1.5 border-t-[1.5px] border-dashed border-border pt-1.5">
              <span className="flex justify-between font-mono text-[8.5px] text-muted">
                <span className="font-display font-bold uppercase tracking-[0.1em]">{t('bill.paidProgress')}</span>
                <span className="tabular-nums">{SUM(paid)} / {SUM(TOTAL)}</span>
              </span>
              <span className="mt-1 block h-1.5 overflow-hidden rounded-full border border-outline bg-surface-2">
                <span className="block h-full bg-success" style={{ width: `${Math.round((paid / TOTAL) * 100)}%` }} />
              </span>
            </div>
            <div className="mt-1.5 flex items-baseline justify-between border-t-[1.5px] border-dashed border-border pt-1.5">
              <span className="font-display text-[10px] font-extrabold uppercase">{t('bill.totalBill')}</span>
              <span className="font-mono text-[12px] font-bold tabular-nums">{SUM(TOTAL)}</span>
            </div>
          </div>
        </div>
        <p className="px-1.5 pb-0.5 pt-1.5 text-[11.5px] leading-snug">
          {t('settings.preview.message', { title: t('settings.preview.title'), amount: SUM(SHARES.you) })}
        </p>
      </div>
      <div className="grid w-[94%] grid-cols-2 gap-1">
        {(['open', 'paid'] as const).map((button) => (
          <span key={button} className="rounded-lg bg-[rgba(0,0,0,0.22)] py-1.5 text-center text-[11px] font-semibold text-white">
            {t(`settings.preview.${button}`)}
          </span>
        ))}
      </div>
    </div>
  );
}
