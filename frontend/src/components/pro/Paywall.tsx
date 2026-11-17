'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion, useReducedMotion, type Transition } from 'framer-motion';
import { Check, Clock, Loader2, Minus, Star, X } from 'lucide-react';
import Button from '@/components/ui/Button';
import type { PaywallReason, ProOffer, ProOverview, ProPlan, ProPlanOffer } from '@/types/pro';
import { createProInvoice, getPro, redeemPromo, startProOffer } from '@/lib/api/pro';
import { usePro } from '@/lib/store/usePro';
import { useStore } from '@/lib/store/useStore';
import { canOpenInvoice, openInvoice, type InvoiceStatus } from '@/lib/telegram/invoice';
import { track, AnalyticsEvent } from '@/lib/analytics';
import { showBackButton } from '@/lib/telegram/init';
import EdgeSwipeBack from '@/components/layout/EdgeSwipeBack';
import { useScrollLock } from '@/hooks/useScrollLock';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { showToast } from '@/lib/toast';
import { useNow } from '@/hooks/useNow';
import { countdown } from '@/lib/utils/reminders';
import OwedNote from './OwedNote';
import ProPreview from './ProPreview';

const FEATURES = ['analytics', 'scans', 'voice', 'reminders', 'themes', 'previews', 'photos', 'badge'] as const;
type Feature = (typeof FEATURES)[number];
/** Rows that are there or not, rather than how much. */
const CHECKED = new Set<Feature>(['voice', 'badge']);
/** Rows whose Pro value has a line under it: what only Pro does there. */
const NOTED = new Set<Feature>(['reminders']);
const SWAP: Transition = { type: 'spring', duration: 0.3, bounce: 0 };
/** The row a reason is about, lit up in the table. */
const ROW_OF: Partial<Record<PaywallReason, Feature>> = {
  analytics: 'analytics',
  scans: 'scans',
  reminders: 'reminders',
  themes: 'themes',
  voice: 'voice',
};
const PAYMENT_CHECKS = 8;
const PAYMENT_CHECK_MS = 1500;
const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
// Where the price goes in a sentence like «Get for {stars}», in any language's word order.
const STARS_SLOT = '\u2063';

/** A sentence with a price in Stars in it, the price drawn with its star. */
function WithStars({ text, stars }: { text: string; stars: number }) {
  const [before, after = ''] = text.split(STARS_SLOT);
  return (
    <>
      {before}
      <Stars value={stars} />
      {after}
    </>
  );
}

/** Stars, with the star. */
function Stars({ value, className = '' }: { value: number; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-0.5 whitespace-nowrap font-mono font-bold tabular-nums ${className}`}>
      {value}
      <Star aria-hidden="true" className="h-[0.9em] w-[0.9em] fill-star text-star" />
    </span>
  );
}

/**
 * What Pro gives against Free, the plans with what each comes to a month, and
 * the way to pay in Telegram Stars or redeem a code — opened over whatever
 * needed Pro. Pro itself comes with the payment the server hears about, so
 * after the sheet says «paid» it waits until the server agrees.
 */
export default function Paywall() {
  const reason = usePro((state) => state.paywall);
  const resume = usePro((state) => state.resume);
  const close = usePro((state) => state.closePaywall);
  useScrollLock(reason !== null);
  if (reason === null || typeof document === 'undefined') return null;
  return createPortal(<PaywallSheet reason={reason} resume={resume} onClose={close} />, document.body);
}

function PaywallSheet({ reason, resume, onClose }: {
  reason: PaywallReason;
  /** What the paywall stopped, to carry on with after the purchase. */
  resume: (() => void) | null;
  onClose: () => void;
}) {
  const { t, language } = useTranslation();
  const userId = useStore((state) => state.currentUser?.id);
  const overview = usePro((state) => state.overview);
  const setOverview = usePro((state) => state.set);
  // The smallest step in comes chosen: a year up front put people off.
  const [plan, setPlan] = useState<ProPlan>('month');
  const [paying, setPaying] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [succeeded, setSucceeded] = useState<ProOverview | null>(null);
  const [promoOpen, setPromoOpen] = useState(false);
  const [code, setCode] = useState('');
  const [promoError, setPromoError] = useState<string | null>(null);
  const [redeeming, setRedeeming] = useState(false);
  const openedAt = useRef(Date.now());

  const plans = overview?.plans ?? [];
  // A running subscription renews by itself; a second one would charge twice.
  const available = plans.filter((offer) => !(offer.recurring && overview?.subscription));
  const chosen = available.find((offer) => offer.plan === plan) ?? shortest(available);
  const shown = chosen?.plan;

  // Left without buying: how, after how long, and on the plan on screen —
  // where the funnel loses people. Leaving once paid — Pro arrived or on its
  // way — is not that.
  const dismiss = useCallback((via: 'close' | 'back' | 'not_now') => {
    if (!succeeded && !waiting) {
      track(AnalyticsEvent.PaywallClosed, {
        reason, via, ...(shown ? { plan: shown } : {}), seconds: Math.round((Date.now() - openedAt.current) / 1000),
      });
    }
    onClose();
  }, [succeeded, waiting, reason, shown, onClose]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') dismiss('close');
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [dismiss]);

  // Telegram's back goes back to the bill or the list the paywall was opened
  // over, rather than leaving the app with «Close».
  useEffect(() => showBackButton(() => dismiss('back')), [dismiss]);

  // The server makes the one-off offer the first time it is asked, if this
  // person may have one; the plans come back priced with it.
  useEffect(() => {
    if (!userId) return;
    startProOffer(userId).then(setOverview).catch(() => {});
  }, [userId, setOverview]);

  const refresh = useCallback(() => {
    if (userId) getPro(userId).then(setOverview).catch(() => {});
  }, [userId, setOverview]);

  const date = (iso: string | null) =>
    iso ? new Intl.DateTimeFormat(language, { day: 'numeric', month: 'long', year: 'numeric' }).format(new Date(iso)) : '';
  const scansPerDay = String(overview?.free_scans_per_day ?? 3);
  const monthly = plans.find((offer) => offer.plan === 'month');
  const lit = ROW_OF[reason];

  const choosePlan = (next: ProPlan) => {
    setPlan(next);
    track(AnalyticsEvent.PaywallPlanSelected, { plan: next });
  };

  const pay = async () => {
    if (!userId || !chosen || paying) return;
    track(AnalyticsEvent.ProCheckoutStarted, {
      plan: chosen.plan,
      stars: chosen.stars,
      reason,
      ...(overview?.offer && chosen.was_stars ? { offer_percent: overview.offer.percent } : {}),
    });
    if (!canOpenInvoice()) {
      track(AnalyticsEvent.ProCheckoutResult, { plan: chosen.plan, status: 'unsupported' });
      showToast(t('pro.unsupported'));
      return;
    }
    setPaying(true);
    let status: InvoiceStatus | null = null;
    try {
      status = await openInvoice(await createProInvoice(userId, chosen.plan));
      track(AnalyticsEvent.ProCheckoutResult, { plan: chosen.plan, status });
      if (status === 'failed') showToast(t('pro.invoiceFailed'));
      if (status !== 'paid') return;
      setWaiting(true);
      for (let check = 0; check < PAYMENT_CHECKS; check += 1) {
        // Paid already: a check lost to the network is only a check, not a failure.
        const fresh = await getPro(userId).catch(() => null);
        if (fresh?.active && fresh.until !== overview?.until) {
          setOverview(fresh);
          setSucceeded(fresh);
          track(AnalyticsEvent.ProActivated, { via: 'stars', plan: chosen.plan });
          return;
        }
        await wait(PAYMENT_CHECK_MS);
      }
      // The payment is on its way; the bot says so when it lands.
      onClose();
    } catch (error) {
      console.error('Error paying for Pro:', error);
      if (status === null) track(AnalyticsEvent.ProCheckoutResult, { plan: chosen.plan, status: 'error' });
      if (status !== 'paid') showToast(t('pro.invoiceFailed'));
    } finally {
      setPaying(false);
      setWaiting(false);
    }
  };

  const redeem = async () => {
    if (!userId || !code.trim() || redeeming) return;
    setRedeeming(true);
    setPromoError(null);
    try {
      const fresh = await redeemPromo(userId, code.trim());
      setOverview(fresh);
      setSucceeded(fresh);
      track(AnalyticsEvent.PromoRedeemed, { ok: true });
      track(AnalyticsEvent.ProActivated, { via: 'promo' });
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: { code?: string } } } })?.response?.data?.detail;
      track(AnalyticsEvent.PromoRedeemed, { ok: false, error: detail?.code ?? 'unknown' });
      setPromoError(detail?.code ? t(`pro.promoErrors.${detail.code}`) : t('common.error'));
    } finally {
      setRedeeming(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="paywall-title"
      data-back-swipe-layer="paywall"
      className="fixed inset-0 z-[70] flex flex-col bg-background pt-[var(--content-safe-top)] text-foreground shadow-[-12px_0_28px_rgba(0,0,0,0.18)]"
    >
      <EdgeSwipeBack onBack={() => dismiss('back')} layer="paywall" />
      <div className="flex items-center justify-end px-3 pt-2">
        <button
          type="button"
          onClick={() => dismiss('close')}
          aria-label={t('common.close')}
          className="flex h-11 w-11 items-center justify-center rounded-lg text-muted hover:text-foreground"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {succeeded ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 pb-[calc(24px+var(--content-safe-bottom))] text-center">
          <motion.span
            initial={{ scale: 0.4, rotate: -12, opacity: 0 }}
            animate={{ scale: 1, rotate: 0, opacity: 1 }}
            transition={{ type: 'spring', duration: 0.6, bounce: 0.5 }}
          >
            <ProMedal />
          </motion.span>
          <p className="font-display text-[22px] font-extrabold [text-wrap:balance]">{t('pro.success', { date: date(succeeded.until) })}</p>
          <Button
            className="w-full max-w-xs"
            onClick={() => {
              onClose();
              resume?.();
            }}
          >
            {t(resume ? 'pro.continue' : 'pro.done')}
          </Button>
        </div>
      ) : (
        <>
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 pb-4">
            <Rise order={0}>
              <ProPreview reason={reason} />
            </Rise>
            <Rise order={0} className="flex items-start gap-3.5">
              {reason === 'general' && <ProMedal />}
              <div className="min-w-0 flex-1 pt-0.5">
                <div className="font-display text-[12px] font-extrabold uppercase tracking-[0.16em] text-accent">{t('pro.title')}</div>
                <h2 id="paywall-title" className="mt-1 font-display text-[22px] font-extrabold leading-[1.1] [text-wrap:balance]">
                  {t(`pro.headline.${reason}`)}
                </h2>
              </div>
            </Rise>
            <Rise order={1}>
              <p className="mt-2.5 text-[14px] text-muted [text-wrap:pretty]">{t(`pro.subtitle.${reason}`, { count: scansPerDay })}</p>
              {reason === 'reminders' && userId && <OwedNote userId={userId} />}
              {overview?.active && (
                <p className="mt-3 inline-flex rounded-full border-[1.5px] border-outline bg-surface px-3 py-1 font-mono text-[12px] font-bold">
                  {t(overview.trial ? 'pro.trialUntil' : 'pro.activeUntil', { date: date(overview.until) })}
                </p>
              )}
            </Rise>

            <Rise order={2}>
              <Comparison lit={lit} scansPerDay={scansPerDay} />
            </Rise>

            <div className="mt-4">
              {promoOpen ? (
                <PromoForm
                  code={code}
                  onCode={(next) => {
                    setCode(next);
                    setPromoError(null);
                  }}
                  error={promoError}
                  redeeming={redeeming}
                  onRedeem={() => void redeem()}
                  onCancel={() => {
                    setPromoOpen(false);
                    setPromoError(null);
                  }}
                />
              ) : (
                <button type="button" onClick={() => setPromoOpen(true)} className="min-h-11 text-[14px] font-semibold text-accent underline decoration-dotted underline-offset-4">
                  {t('pro.promoToggle')}
                </button>
              )}
            </div>

          </div>

          {/* The plans ride with the button, so whatever the phone's height
              they are on screen from the start — the comparison scrolls above. */}
          {!promoOpen && (
            <div className="border-t-[1.5px] border-border bg-background px-4 pb-[calc(12px+var(--content-safe-bottom))] pt-3">
              {overview?.offer && <OfferBanner offer={overview.offer} onEnd={refresh} />}
              <Rise order={2} className="@container">
                <div role="radiogroup" aria-label={t('pro.title')} className="grid gap-2 pt-2.5 @min-[300px]:grid-cols-3">
                  {plans.map((offer) => (
                    <PlanOption
                      key={offer.plan}
                      offer={offer}
                      monthly={monthly}
                      chosen={offer.plan === chosen?.plan}
                      subscribed={offer.recurring && !!overview?.subscription}
                      onChoose={() => choosePlan(offer.plan)}
                    />
                  ))}
                </div>
              </Rise>
              <Button className="mt-3 w-full overflow-hidden" onClick={() => void pay()} disabled={!chosen || paying}>
                {waiting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {t('pro.waiting')}
                  </>
                ) : chosen ? (
                  <AnimatePresence mode="popLayout" initial={false}>
                    <motion.span
                      key={chosen.plan}
                      initial={{ opacity: 0, y: 10, filter: 'blur(4px)' }}
                      animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
                      exit={{ opacity: 0, y: -10, filter: 'blur(4px)' }}
                      transition={SWAP}
                      className="inline-flex items-center gap-1.5"
                    >
                      <WithStars text={t(buyLabel(chosen, !!overview?.active), { stars: STARS_SLOT })} stars={chosen.stars} />
                    </motion.span>
                  </AnimatePresence>
                ) : (
                  <Loader2 className="h-4 w-4 animate-spin" />
                )}
              </Button>
              <p className="mt-2 text-center text-[11px] leading-snug text-muted">{t('pro.payNote')}</p>
              <button
                type="button"
                onClick={() => dismiss('not_now')}
                className="mx-auto mt-1 flex min-h-10 items-center px-4 text-[13px] font-semibold text-muted-2 hover:text-foreground"
              >
                {t('pro.notNow')}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/** The star on its medal — what Pro looks like wherever it is offered. */
function ProMedal() {
  return (
    <span className="relative flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border-[1.5px] border-outline bg-[linear-gradient(145deg,var(--accent),var(--accent-hover))] text-accent-fg shadow-[var(--shadow-hard)]">
      <span aria-hidden="true" className="absolute inset-1 rounded-[12px] bg-[radial-gradient(circle_at_30%_25%,rgba(255,255,255,0.35),transparent_60%)]" />
      <Star aria-hidden="true" className="relative h-7 w-7 fill-star text-star drop-shadow-[0_1px_0_rgba(0,0,0,0.25)]" />
    </span>
  );
}

/** The sheet comes in in parts, each a beat after the one above it. */
function Rise({ order, className = '', children }: { order: number; className?: string; children: React.ReactNode }) {
  const reduceMotion = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduceMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', duration: 0.45, bounce: 0, delay: order * 0.07 }}
    >
      {children}
    </motion.div>
  );
}

/** Free against Pro, row by row: Free in grey, Pro in the accent, lit where it was asked for. */
function Comparison({ lit, scansPerDay }: { lit: Feature | undefined; scansPerDay: string }) {
  const { t } = useTranslation();
  const cell = 'border-t-[1.5px] border-dashed border-border px-2 py-2 text-center';
  // What the paywall was opened over comes first, on screen whatever the phone.
  const rows = lit ? [lit, ...FEATURES.filter((feature) => feature !== lit)] : FEATURES;
  return (
    <div className="mt-4 overflow-hidden rounded-xl border-[1.5px] border-outline bg-surface shadow-[var(--shadow-hard-sm)]">
      <table className="w-full border-separate border-spacing-0 text-[13px]">
        <thead>
          <tr className="font-display text-[11px] font-bold uppercase tracking-[0.1em]">
            <th className="px-3 py-2.5 text-left font-bold" />
            <th className="w-[26%] px-2 py-2.5 text-center font-bold text-muted">{t('pro.free')}</th>
            <th className="w-[30%] bg-[linear-gradient(160deg,var(--accent),var(--accent-hover))] px-2 py-2.5 text-center font-extrabold text-accent-fg">
              <span className="inline-flex items-center gap-1">
                <Star aria-hidden="true" className="h-3.5 w-3.5 fill-star text-star" />
                Pro
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((feature) => (
            <tr key={feature} className={feature === lit ? 'bg-accent-weak' : ''}>
              <th scope="row" className={`${cell} relative px-3 text-left font-semibold leading-snug`}>
                {feature === lit && <span aria-hidden="true" className="absolute inset-y-1.5 left-0 w-[3px] rounded-r bg-accent" />}
                {t(`pro.rows.${feature}`)}
              </th>
              <td className={`${cell} leading-snug text-muted`}>
                <Value feature={feature} pro={false} count={scansPerDay} />
              </td>
              <td className={`${cell} bg-accent/15 shadow-[inset_1.5px_0_0_var(--accent),inset_-1.5px_0_0_var(--accent)] font-bold leading-snug text-foreground`}>
                <Value feature={feature} pro count={scansPerDay} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Value({ feature, pro, count }: { feature: Feature; pro: boolean; count: string }) {
  const { t } = useTranslation();
  if (CHECKED.has(feature)) {
    return pro ? (
      <span aria-label="✓" className="mx-auto flex h-5 w-5 items-center justify-center rounded-full bg-accent text-accent-fg">
        <Check aria-hidden="true" className="h-3 w-3" strokeWidth={3.5} />
      </span>
    ) : (
      <Minus aria-label="—" className="mx-auto h-4 w-4 text-muted-2" />
    );
  }
  return (
    <>
      {t(`pro.${pro ? 'proValues' : 'freeValues'}.${feature}`, { count })}
      {pro && NOTED.has(feature) && (
        <span className="mt-0.5 block text-[11px] font-medium leading-snug text-muted">{t(`pro.proNotes.${feature}`)}</span>
      )}
    </>
  );
}

function buyLabel(offer: ProPlanOffer, active: boolean): string {
  if (active) return 'pro.extend';
  return offer.recurring ? 'pro.subscribe' : 'pro.buy';
}

/** The one-off discount and the time left on it, to the second. Once it is
 *  over the plans are asked for again, back at their price. */
function OfferBanner({ offer, onEnd }: { offer: ProOffer; onEnd: () => void }) {
  const { t } = useTranslation();
  const endsAt = Date.parse(offer.ends_at);
  const now = useNow(endsAt);
  const left = endsAt - now.getTime();
  const over = left <= 0;

  useEffect(() => {
    if (over) onEnd();
  }, [over, onEnd]);

  if (over) return null;
  return (
    <div className="mb-2.5 flex items-center justify-between gap-2 rounded-lg bg-emphasis px-3 py-1.5 text-emphasis-fg">
      <span className="min-w-0 text-[12px] font-bold leading-tight [text-wrap:balance]">
        {t('pro.offer', { percent: String(offer.percent) })}
      </span>
      <span className="flex shrink-0 items-center gap-1 font-mono text-[13px] font-bold tabular-nums" role="timer" aria-label={t('pro.offerEnds')}>
        <Clock aria-hidden="true" className="h-3.5 w-3.5" />
        {countdown(left)}
      </span>
    </div>
  );
}

function shortest(offers: ProPlanOffer[]): ProPlanOffer | undefined {
  return offers.reduce<ProPlanOffer | undefined>((min, offer) => (!min || offer.months < min.months ? offer : min), undefined);
}

/** What is off: from the struck-out price when there is one, else against paying monthly. */
function percentOff(offer: ProPlanOffer, monthly: ProPlanOffer | undefined): number {
  if (offer.was_stars) return Math.round((1 - offer.stars / offer.was_stars) * 100);
  if (monthly && offer.months > 1) return Math.round((1 - offer.stars / (monthly.stars * offer.months)) * 100);
  return 0;
}

function PlanOption({ offer, monthly, chosen, subscribed, onChoose }: {
  offer: ProPlanOffer;
  monthly: ProPlanOffer | undefined;
  chosen: boolean;
  /** The viewer already pays for this one every month. */
  subscribed: boolean;
  onChoose: () => void;
}) {
  const { t } = useTranslation();
  const reduceMotion = useReducedMotion();
  const off = percentOff(offer, monthly);
  const best = offer.plan === 'year';
  return (
    <motion.button
      type="button"
      role="radio"
      aria-checked={chosen}
      disabled={subscribed}
      onClick={onChoose}
      whileTap={reduceMotion || subscribed ? undefined : { scale: 0.96 }}
      transition={SWAP}
      className="relative isolate flex min-h-[96px] flex-col items-start rounded-xl border-[1.5px] border-border bg-surface/60 px-3 pb-2.5 pt-3 text-left disabled:opacity-55"
    >
      {chosen && (
        <motion.span
          layoutId="paywall-chosen-plan"
          aria-hidden="true"
          transition={reduceMotion ? { duration: 0 } : SWAP}
          className="absolute -inset-[1.5px] -z-10 rounded-xl border-2 border-accent bg-accent-weak shadow-[var(--shadow-hard-sm)]"
        />
      )}
      {best && (
        <span className="absolute -top-2.5 left-3 rounded-full border-[1.5px] border-outline bg-accent px-2 py-px font-display text-[9px] font-extrabold uppercase leading-[14px] tracking-[0.08em] text-accent-fg">
          {t('pro.best')}
        </span>
      )}
      <AnimatePresence initial={false}>
        {chosen && (
          <motion.span
            key="check"
            aria-hidden="true"
            initial={{ scale: 0.4, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.4, opacity: 0 }}
            transition={SWAP}
            className="absolute -right-2 -top-2 flex h-[22px] w-[22px] items-center justify-center rounded-full border-[1.5px] border-outline bg-accent text-accent-fg"
          >
            <Check className="h-3 w-3" strokeWidth={3.5} />
          </motion.span>
        )}
      </AnimatePresence>

      <span className="font-display text-[14px] font-bold leading-tight">{t(`pro.plans.${offer.plan}`)}</span>
      <span className="mt-1.5 flex flex-wrap items-baseline gap-x-1.5">
        <Stars value={offer.stars} className="text-[19px] leading-none" />
        {offer.was_stars && <WasStars value={offer.was_stars} />}
      </span>
      <span className="mt-auto flex w-full flex-wrap items-center gap-x-1.5 gap-y-1 pt-2 text-[11px] leading-tight text-muted">
        {subscribed && t('pro.subscribed')}
        {!subscribed && offer.recurring && (
          <span>
            <WithStars text={t('pro.perDay', { stars: STARS_SLOT })} stars={Math.round(offer.stars / 30)} />
          </span>
        )}
        {!subscribed && offer.months > 1 && (
          <span>
            <WithStars text={t('pro.perMonth', { stars: STARS_SLOT })} stars={Math.round(offer.stars / offer.months)} />
          </span>
        )}
        {off > 0 && !subscribed && <Saving percent={off} />}
      </span>
    </motion.button>
  );
}

/** The price it is down from, struck through, with its star. */
function WasStars({ value }: { value: number }) {
  return (
    <s className="inline-flex items-center gap-0.5 font-mono text-[12px] tabular-nums text-muted decoration-danger decoration-[1.5px]">
      {value}
      <Star aria-hidden="true" className="h-[0.85em] w-[0.85em] fill-current opacity-70" />
    </s>
  );
}

/** A code typed into room enough for it, and why it did not work. */
function PromoForm({ code, onCode, error, redeeming, onRedeem, onCancel }: {
  code: string;
  onCode: (code: string) => void;
  error: string | null;
  redeeming: boolean;
  onRedeem: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  return (
    <form
      className="rounded-xl border-[1.5px] border-outline bg-surface p-3.5 shadow-[var(--shadow-hard-sm)]"
      onSubmit={(event) => {
        event.preventDefault();
        onRedeem();
      }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-display text-[13px] font-extrabold uppercase tracking-[0.1em]">{t('pro.promoPlaceholder')}</span>
        <button
          type="button"
          onClick={onCancel}
          aria-label={t('common.cancel')}
          className="-mr-1.5 flex h-9 w-9 items-center justify-center rounded-lg text-muted hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <p className="text-[12px] leading-snug text-muted">{t('pro.promoHint')}</p>
      <input
        value={code}
        onChange={(event) => onCode(event.target.value)}
        onFocus={(event) => event.currentTarget.scrollIntoView({ block: 'center', behavior: 'smooth' })}
        placeholder={t('pro.promoPlaceholder')}
        aria-label={t('pro.promoPlaceholder')}
        aria-invalid={!!error}
        autoFocus
        autoCapitalize="characters"
        autoComplete="off"
        spellCheck={false}
        className={`mt-3 h-12 w-full rounded-lg border-[1.5px] bg-background px-3 text-center font-mono text-[18px] font-bold uppercase tracking-[0.12em] outline-none placeholder:font-normal placeholder:normal-case placeholder:tracking-normal placeholder:text-muted-2 focus:border-accent ${
          error ? 'border-danger' : 'border-outline'
        }`}
      />
      {error && <p role="alert" className="mt-1.5 text-[13px] text-danger">{error}</p>}
      <Button variant="outline" className="mt-3 w-full" type="submit" isLoading={redeeming} disabled={!code.trim()}>
        {t('pro.promoApply')}
      </Button>
    </form>
  );
}

function Saving({ percent }: { percent: number }) {
  const { t } = useTranslation();
  return (
    <span className="rounded-full bg-success px-1.5 py-px font-mono text-[11px] font-bold tabular-nums text-success-fg">
      {t('pro.save', { percent: String(percent) })}
    </span>
  );
}
