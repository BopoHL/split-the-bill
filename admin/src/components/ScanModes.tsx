'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, type ScanMode, type ScanModeStat, type Settings } from '@/lib/api';
import Select from './Select';

export const MODES = [
  { value: 'ocr_llm', label: 'OCR → модель' },
  { value: 'vision', label: 'Только фото' },
  { value: 'hybrid', label: 'Фото + текст OCR' },
];

export const MODE_LABELS: Record<string, string> = Object.fromEntries(
  MODES.map((mode) => [mode.value, mode.label]),
);

/** Models known to read receipts; any other one OpenAI has can be typed in. */
export const SUGGESTED_MODELS = ['gpt-6-luna', 'gpt-6-sol', 'gpt-5.6-luna'];

const EXPLANATION: Record<string, string> = {
  ocr_llm: 'Google Vision читает текст, модель раскладывает его по позициям. Так было всегда.',
  vision: 'Фото уходит в модель напрямую. Она видит вёрстку чека, но может ошибиться в цифре.',
  hybrid: 'И то и другое: фото как документ, текст OCR — второе мнение о символах.',
};

/**
 * Which reader is on, and how each one has been doing.
 *
 * The switch takes effect on the next scan — the worker asks per task rather
 * than at startup, so nothing has to be restarted.
 */
export default function ScanModes() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [stats, setStats] = useState<ScanModeStat[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modelDraft, setModelDraft] = useState<string | null>(null);

  const load = useCallback(() => {
    api.settings().then(setSettings).catch(console.error);
    api.scanModes().then(setStats).catch(console.error);
  }, []);

  useEffect(load, [load]);

  const save = async (change: Partial<Settings>) => {
    setBusy(true);
    setError(null);
    try {
      setSettings(await api.saveSettings(change));
      setModelDraft(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не сохранилось');
    } finally {
      setBusy(false);
    }
  };

  const model = modelDraft ?? settings?.receipt_model ?? '';
  const modelChanged = !!settings && model.trim() !== '' && model.trim() !== settings.receipt_model;

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-border bg-surface p-4">
        <h2 className="mb-1 font-bold">Распознавание чеков</h2>
        <p className="mb-3 text-sm text-muted">
          Применяется со следующего скана — перезапускать ничего не нужно.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <Select
            options={MODES}
            value={settings?.scan_mode ?? 'ocr_llm'}
            onChange={(next) => void save({ scan_mode: next as ScanMode })}
          />
          {busy && <span className="text-sm text-muted">Сохраняем…</span>}
        </div>
        {settings && (
          <p className="mt-3 text-[13px] leading-relaxed text-muted-2">
            {EXPLANATION[settings.scan_mode]}
          </p>
        )}

        <form
          className="mt-5 flex flex-wrap items-center gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (modelChanged) void save({ receipt_model: model.trim() });
          }}
        >
          <label htmlFor="receipt-model" className="text-sm font-medium">
            Модель
          </label>
          <input
            id="receipt-model"
            list="receipt-models"
            value={model}
            onChange={(event) => setModelDraft(event.target.value)}
            spellCheck={false}
            className="w-56 rounded-md border border-border bg-background px-3 py-1.5 font-mono text-sm"
          />
          <datalist id="receipt-models">
            {SUGGESTED_MODELS.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
          <button
            type="submit"
            disabled={!modelChanged || busy}
            className="rounded-md border border-border px-3 py-1.5 text-sm transition-colors hover:bg-surface disabled:opacity-50"
          >
            Сохранить
          </button>
        </form>
        <p className="mt-2 text-[13px] leading-relaxed text-muted-2">
          Любая модель OpenAI с картинками на входе. Перед сохранением проверяем, что она есть
          у нашего ключа.
        </p>
        {error && <p className="mt-2 text-sm text-danger">{error}</p>}
      </section>

      <section>
        <h2 className="mb-1 font-bold">Как режимы себя показывают</h2>
        <p className="mb-3 text-sm text-muted">
          Расхождение — печатный итог чека не сошёлся с суммой распознанных позиций. Это
          единственная мера, которой не нужен человек; оценка — то, что ставят пользователи.
        </p>
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-surface text-left text-xs uppercase tracking-wider text-muted">
              <tr>
                <th className="px-3 py-2">Режим</th>
                <th className="px-3 py-2 text-right">Сканов</th>
                <th className="px-3 py-2 text-right">Ошибок</th>
                <th className="px-3 py-2 text-right">Расхождений</th>
                <th className="px-3 py-2 text-right">Оценка</th>
              </tr>
            </thead>
            <tbody>
              {stats.map((row) => (
                <tr key={row.mode} className="border-t border-border">
                  <td className="px-3 py-2">{MODE_LABELS[row.mode] ?? row.mode}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{row.scans}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{row.failed}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {row.mismatch_rate === null ? '—' : `${Math.round(row.mismatch_rate * 100)}%`}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {row.avg_quality === null ? '—' : `${row.avg_quality.toFixed(1)} (${row.rated})`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {stats.length === 0 && (
            <p className="px-3 py-6 text-center text-muted">Сканов ещё не было</p>
          )}
        </div>
      </section>
    </div>
  );
}
