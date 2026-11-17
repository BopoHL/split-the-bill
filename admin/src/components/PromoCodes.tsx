'use client';

import { useEffect, useState } from 'react';
import { api, type PromoCode, type PromoCodeDraft } from '@/lib/api';
import { formatTashkent, parseUtc, tashkentToUtcIso } from '@/lib/time';
import Select from './Select';

const DURATIONS = [
  { value: '7', label: '7 дней' },
  { value: '30', label: '1 месяц' },
  { value: '90', label: '3 месяца' },
  { value: '182', label: '6 месяцев' },
  { value: '365', label: '1 год' },
  { value: 'custom', label: 'Своё число дней' },
];

interface Form {
  code: string;
  duration: string;
  customDays: string;
  maxUses: string;
  expiresAt: string;
  note: string;
}

const EMPTY_FORM: Form = { code: '', duration: '30', customDays: '', maxUses: '', expiresAt: '', note: '' };

function draftOf(form: Form): PromoCodeDraft {
  const draft: PromoCodeDraft = {
    days: Number(form.duration === 'custom' ? form.customDays : form.duration),
  };
  if (form.code.trim()) draft.code = form.code.trim();
  if (form.maxUses) draft.max_uses = Number(form.maxUses);
  if (form.expiresAt) draft.expires_at = tashkentToUtcIso(form.expiresAt);
  if (form.note.trim()) draft.note = form.note.trim();
  return draft;
}

function daysLabel(days: number): string {
  return DURATIONS.find((duration) => duration.value === String(days))?.label ?? `${days} дн.`;
}

/** What stands in the way of a code being redeemed now, if anything. */
function stateOf(promo: PromoCode, now: Date): { label: string; tone: string } {
  if (!promo.is_active) return { label: 'выключен', tone: 'text-muted' };
  if (promo.expires_at && parseUtc(promo.expires_at) <= now) return { label: 'истёк', tone: 'text-muted' };
  if (promo.max_uses !== null && promo.uses >= promo.max_uses) return { label: 'израсходован', tone: 'text-muted' };
  return { label: 'действует', tone: 'text-success' };
}

/**
 * Codes that give Pro for a while. Each person can use a code once; one left
 * without a limit works for anyone who has it. Switching a code off stops it
 * giving more — what it already gave stays.
 */
export default function PromoCodes() {
  const [codes, setCodes] = useState<PromoCode[]>([]);
  const [form, setForm] = useState<Form>(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);

  useEffect(() => {
    api.promoCodes().then(setCodes).catch(console.error);
  }, []);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const promo = await api.createPromoCode(draftOf(form));
      setCodes((list) => [promo, ...list]);
      setCreated(promo.code);
      setForm(EMPTY_FORM);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не создался');
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (promo: PromoCode) => {
    try {
      const next = await api.setPromoCodeActive(promo.id, !promo.is_active);
      setCodes((list) => list.map((item) => (item.id === next.id ? next : item)));
    } catch (e) {
      console.error(e);
    }
  };

  const now = new Date();
  const field = 'rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none';

  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-1 font-bold">Промокоды</h2>
      <p className="mb-1 text-sm text-muted">
        Код даёт Pro на выбранное число дней — после того, что у человека уже есть. Один человек применяет код один раз.
      </p>
      <p className="mb-4 text-[13px] leading-relaxed text-muted-2">
        Два срока — о разном: «Даёт Pro» — сколько Pro получит тот, кто ввёл код; «Ввести до» — до какого
        момента код вообще принимается. Код на 30 дней, который можно ввести до 31.10, введённый 30.10, даст
        Pro до 29.11.
      </p>

      <form
        className="mb-4 flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          void create();
        }}
      >
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Код</span>
          <input
            value={form.code}
            onChange={(event) => setForm({ ...form, code: event.target.value.toUpperCase() })}
            placeholder="придумается сам"
            spellCheck={false}
            className={`${field} w-44 font-mono uppercase`}
          />
        </label>
        <div className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Даёт Pro</span>
          <Select options={DURATIONS} value={form.duration} onChange={(duration) => setForm({ ...form, duration })} />
        </div>
        {form.duration === 'custom' && (
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium">Дней</span>
            <input
              type="number"
              min={1}
              required
              value={form.customDays}
              onChange={(event) => setForm({ ...form, customDays: event.target.value })}
              className={`${field} w-24 font-mono`}
            />
          </label>
        )}
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Сколько человек</span>
          <input
            type="number"
            min={1}
            value={form.maxUses}
            onChange={(event) => setForm({ ...form, maxUses: event.target.value })}
            placeholder="без лимита"
            className={`${field} w-32 font-mono`}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Ввести до (Ташкент)</span>
          <input
            type="datetime-local"
            value={form.expiresAt}
            onChange={(event) => setForm({ ...form, expiresAt: event.target.value })}
            className={field}
          />
        </label>
        <label className="flex min-w-48 flex-1 flex-col gap-1 text-sm">
          <span className="font-medium">Заметка</span>
          <input
            value={form.note}
            onChange={(event) => setForm({ ...form, note: event.target.value })}
            placeholder="для кого или зачем"
            className={field}
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-foreground px-3 py-1.5 text-sm font-medium text-background transition-opacity disabled:opacity-50"
        >
          {busy ? 'Создаём…' : 'Создать'}
        </button>
      </form>
      {error && <p className="mb-3 text-sm text-danger">{error}</p>}
      {created && (
        <p className="mb-3 text-sm">
          Создан код <span className="font-mono font-bold">{created}</span>
        </p>
      )}

      <div className="overflow-x-auto rounded-lg border border-border bg-background">
        <table className="w-full text-sm">
          <thead className="bg-surface text-left text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-3 py-2">Код</th>
              <th className="px-3 py-2">Даёт Pro</th>
              <th className="px-3 py-2 text-right">Применён</th>
              <th className="px-3 py-2">Ввести до</th>
              <th className="px-3 py-2">Состояние</th>
              <th className="px-3 py-2">Заметка</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {codes.map((promo) => {
              const state = stateOf(promo, now);
              return (
                <tr key={promo.id} className="border-t border-border">
                  <td className="px-3 py-2 font-mono font-bold">{promo.code}</td>
                  <td className="px-3 py-2">{daysLabel(promo.days)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {promo.uses}
                    {promo.max_uses !== null && <span className="text-muted"> / {promo.max_uses}</span>}
                  </td>
                  <td className="px-3 py-2 text-muted-2">{promo.expires_at ? formatTashkent(promo.expires_at) : 'когда угодно'}</td>
                  <td className={`px-3 py-2 ${state.tone}`}>{state.label}</td>
                  <td className="px-3 py-2 text-muted">{promo.note}</td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => void toggle(promo)}
                      className="rounded-md border border-border px-2.5 py-1 text-xs transition-colors hover:border-foreground"
                    >
                      {promo.is_active ? 'Выключить' : 'Включить'}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {codes.length === 0 && <p className="px-3 py-6 text-center text-muted">Промокодов пока нет</p>}
      </div>
    </section>
  );
}
