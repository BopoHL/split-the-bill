'use client';

import { useEffect, useState } from 'react';
import { api, type ProPlan, type ProSettings } from '@/lib/api';

const PLANS: { plan: ProPlan; label: string; months: number }[] = [
  { plan: 'month', label: 'Месяц (автоподписка)', months: 1 },
  { plan: 'half_year', label: '6 месяцев', months: 6 },
  { plan: 'year', label: 'Год', months: 12 },
];

type Field = ProPlan | `was_${ProPlan}` | 'free_scans_per_day' | 'offer_percent' | 'offer_hours';
type Draft = Record<Field, string>;

function draftOf(settings: ProSettings): Draft {
  const draft = {
    free_scans_per_day: String(settings.free_scans_per_day),
    offer_percent: String(settings.offer_percent),
    offer_hours: String(settings.offer_hours),
  } as Draft;
  for (const { plan } of PLANS) {
    draft[plan] = String(settings.prices[plan]);
    draft[`was_${plan}`] = settings.was_prices[plan] === null ? '' : String(settings.was_prices[plan]);
  }
  return draft;
}

const percentOff = (stars: number, was: number) => Math.round((1 - stars / was) * 100);

function Metric({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="text-xs font-semibold uppercase tracking-wider text-muted">{label}</div>
      <div className="mt-1.5 text-2xl font-bold tabular-nums">{value.toLocaleString('ru-RU')}</div>
      {hint && <div className="mt-0.5 text-xs text-muted-2">{hint}</div>}
    </div>
  );
}

/**
 * Who has Pro and what it costs. A new price holds for invoices made from now
 * on: one opened before the change is refused at checkout and the app asks for
 * a fresh one.
 */
export default function ProPricing() {
  const [settings, setSettings] = useState<ProSettings | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .pro()
      .then((loaded) => {
        setSettings(loaded);
        setDraft(draftOf(loaded));
      })
      .catch(console.error);
  }, []);

  if (!settings || !draft) return <p className="text-muted">Загрузка…</p>;

  const saved = draftOf(settings);
  const changed = (Object.keys(draft) as (keyof Draft)[]).some((key) => draft[key] !== saved[key]);
  const monthly = Number(draft.month);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const next = await api.savePro({
        prices: Object.fromEntries(PLANS.map(({ plan }) => [plan, Number(draft[plan])])),
        was_prices: Object.fromEntries(PLANS.map(({ plan }) => [plan, draft[`was_${plan}`] ? Number(draft[`was_${plan}`]) : null])),
        free_scans_per_day: Number(draft.free_scans_per_day),
        offer_percent: Number(draft.offer_percent),
        offer_hours: Number(draft.offer_hours),
      });
      setSettings(next);
      setDraft(draftOf(next));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не сохранилось');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Metric label="Pro сейчас" value={settings.stats.active} />
        <Metric label="Платят" value={settings.stats.paying} hint="покупка или подписка" />
        <Metric label="На пробной неделе" value={settings.stats.trial} />
        <Metric label="Звёзд за 30 дней" value={settings.stats.stars_last_30_days} />
        <Metric label="Звёзд всего" value={settings.stats.stars_total} />
      </div>

      <section className="rounded-lg border border-border bg-surface p-4">
        <h2 className="mb-1 font-bold">Цены и лимиты</h2>
        <p className="mb-4 text-sm text-muted">
          Цены в звёздах Telegram. Счёт, открытый до изменения цены, оплатить не получится — приложение попросит новый.
          «Старая цена» показывается в приложении зачёркнутой рядом с ценой — как скидка; пустое поле — без скидки.
        </p>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (changed) void save();
          }}
        >
          <div className="grid gap-3 md:grid-cols-4">
            {PLANS.map(({ plan, label, months }) => {
              const stars = Number(draft[plan]);
              const was = Number(draft[`was_${plan}`]);
              const saving = months > 1 && monthly > 0 && stars > 0 ? Math.round((1 - stars / (monthly * months)) * 100) : null;
              return (
                <div key={plan} className="flex flex-col gap-1 text-sm">
                  <label className="flex flex-col gap-1">
                    <span className="font-medium">{label}</span>
                    <span className="flex items-center rounded-md border border-border bg-background">
                      <input
                        type="number"
                        min={1}
                        max={10000}
                        required
                        value={draft[plan]}
                        onChange={(event) => setDraft({ ...draft, [plan]: event.target.value })}
                        className="w-full bg-transparent px-3 py-1.5 font-mono tabular-nums outline-none"
                      />
                      <span className="pr-3 text-muted">★</span>
                    </span>
                  </label>
                  <span className="text-xs text-muted-2">
                    {months > 1 && stars > 0 ? `≈${Math.round(stars / months)} ★ в месяц` : 'продлевается каждые 30 дней'}
                    {saving !== null && saving > 0 && ` · выгода ${saving}%`}
                  </span>
                  <label className="mt-1 flex items-center gap-2 text-xs text-muted">
                    <span className="shrink-0">Старая цена</span>
                    <input
                      type="number"
                      min={stars + 1}
                      max={10000}
                      value={draft[`was_${plan}`]}
                      onChange={(event) => setDraft({ ...draft, [`was_${plan}`]: event.target.value })}
                      placeholder="нет"
                      aria-label={`Старая цена: ${label}`}
                      className={`w-full min-w-0 rounded-md border border-border bg-background px-2 py-1 font-mono text-sm tabular-nums outline-none ${draft[`was_${plan}`] ? 'line-through' : ''}`}
                    />
                    {was > stars && stars > 0 && <span className="shrink-0 font-medium text-success">−{percentOff(stars, was)}%</span>}
                  </label>
                </div>
              );
            })}
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium">Бесплатных сканов в день</span>
              <input
                type="number"
                min={0}
                required
                value={draft.free_scans_per_day}
                onChange={(event) => setDraft({ ...draft, free_scans_per_day: event.target.value })}
                className="rounded-md border border-border bg-background px-3 py-1.5 font-mono tabular-nums outline-none"
              />
              <span className="text-xs text-muted-2">фото и Soliq QR вместе, без Pro</span>
            </label>
          </div>
          <fieldset className="grid gap-3 border-t border-border pt-4 md:grid-cols-4">
            <legend className="sr-only">Скидка на первую покупку</legend>
            <p className="text-sm text-muted md:col-span-4">
              <span className="font-medium text-foreground">Скидка на первую покупку.</span> Тому, кто ещё ни разу не платил,
              при первом открытии пейвола даётся скидка на 6 месяцев и год с обратным отсчётом. Один раз на человека, после срока
              не возвращается. Месяц без скидки: подписка Telegram продлевается по цене первого платежа. 0% — не предлагать.
            </p>
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium">Скидка</span>
              <span className="flex items-center rounded-md border border-border bg-background">
                <input
                  type="number"
                  min={0}
                  max={90}
                  required
                  value={draft.offer_percent}
                  onChange={(event) => setDraft({ ...draft, offer_percent: event.target.value })}
                  className="w-full bg-transparent px-3 py-1.5 font-mono tabular-nums outline-none"
                />
                <span className="pr-3 text-muted">%</span>
              </span>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium">Действует</span>
              <span className="flex items-center rounded-md border border-border bg-background">
                <input
                  type="number"
                  min={1}
                  max={336}
                  required
                  value={draft.offer_hours}
                  onChange={(event) => setDraft({ ...draft, offer_hours: event.target.value })}
                  className="w-full bg-transparent px-3 py-1.5 font-mono tabular-nums outline-none"
                />
                <span className="pr-3 text-muted">ч</span>
              </span>
            </label>
          </fieldset>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={!changed || busy}
              className="rounded-md border border-border px-3 py-1.5 text-sm transition-colors hover:bg-background disabled:opacity-50"
            >
              {busy ? 'Сохраняем…' : 'Сохранить'}
            </button>
            {error && <p className="text-sm text-danger">{error}</p>}
          </div>
        </form>
      </section>
    </div>
  );
}
