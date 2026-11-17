'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, type Labeling as LabelingStatus, type LabelingHistory } from '@/lib/api';
import { formatTashkent } from '@/lib/time';
import { SUGGESTED_MODELS } from './ScanModes';

const POLL_MS = 5000;

const BUTTON =
  'rounded-md border border-border px-3 py-1.5 text-sm transition-colors hover:bg-background disabled:opacity-50';

/**
 * The model that labels receipt lines and names places, how the job is doing,
 * and the run through the history — which starts only from here.
 */
export default function Labeling() {
  const [status, setStatus] = useState<LabelingStatus | null>(null);
  const [modelDraft, setModelDraft] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.labeling().then(setStatus).catch(console.error);
  }, []);

  useEffect(load, [load]);

  const running = status?.history?.state === 'running';
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [running, load]);

  const act = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      setModelDraft(null);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не получилось');
    } finally {
      setBusy(false);
    }
  };

  const model = modelDraft ?? status?.model ?? '';
  const modelChanged = !!status && model.trim() !== '' && model.trim() !== status.model;

  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-1 font-bold">Разметка блюд и мест</h2>
      <p className="mb-3 text-sm text-muted">
        Модель решает, что за позиция в чеке и где был счёт, — по этому считается аналитика.
      </p>

      {status && <JobLine status={status} />}

      <form
        className="mt-4 flex flex-wrap items-center gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (modelChanged) void act(() => api.saveSettings({ label_model: model.trim() }));
        }}
      >
        <label htmlFor="label-model" className="text-sm font-medium">
          Модель
        </label>
        <input
          id="label-model"
          list="label-models"
          value={model}
          onChange={(event) => setModelDraft(event.target.value)}
          spellCheck={false}
          className="w-56 rounded-md border border-border bg-background px-3 py-1.5 font-mono text-sm"
        />
        <datalist id="label-models">
          {SUGGESTED_MODELS.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
        <button type="submit" disabled={!modelChanged || busy} className={BUTTON}>
          Сохранить
        </button>
      </form>
      <p className="mt-2 text-[13px] leading-relaxed text-muted-2">
        Своя, отдельно от распознавания чеков. Перед сохранением проверяем, что она есть у нашего ключа.
      </p>

      <h3 className="mb-1 mt-5 font-semibold">История</h3>
      <p className="mb-3 text-[13px] leading-relaxed text-muted-2">
        Всё, что было до начала разметки. Идёт пачками раз в минуту, пока не кончится; можно
        остановить и продолжить с того же места.
      </p>
      {status?.history && <HistoryProgress history={status.history} />}
      {status && (
        <HistoryButton
          history={status.history}
          disabled={busy || !status.key_set}
          onStart={() => void act(api.startLabelingHistory)}
          onPause={() => void act(api.pauseLabelingHistory)}
        />
      )}
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
    </section>
  );
}

function JobLine({ status }: { status: LabelingStatus }) {
  if (!status.key_set) {
    return <p className="text-sm text-danger">OPENAI_API_KEY не задан — разметка стоит.</p>;
  }
  return (
    <div className="space-y-1 text-sm">
      <p>
        Новое размечается само раз в минуту
        {status.since ? `, начиная с ${formatTashkent(status.since)}` : ' — начнёт с первой минуты после запуска'}.
        {status.last_labeled_at && (
          <span className="text-muted"> Последний раз: {formatTashkent(status.last_labeled_at)}.</span>
        )}
      </p>
      {status.last_error && (
        <p className="text-danger">
          Ошибка{status.last_error_at ? ` ${formatTashkent(status.last_error_at)}` : ''}: {status.last_error}
        </p>
      )}
    </div>
  );
}

const STATE_LABELS: Record<LabelingHistory['state'], string> = {
  running: 'идёт',
  paused: 'остановлена',
  done: 'готово',
};

function HistoryProgress({ history }: { history: LabelingHistory }) {
  return (
    <div className="mb-3 max-w-md space-y-2 text-sm">
      <p>
        <span className={history.state === 'done' ? 'text-success' : ''}>{STATE_LABELS[history.state]}</span>
        <span className="text-muted">
          {history.finished_at
            ? ` · ${formatTashkent(history.finished_at)}`
            : ` · с ${formatTashkent(history.started_at)}`}
        </span>
      </p>
      <Progress label="Позиции" done={history.lines_done} total={history.lines_total} />
      <Progress label="Счета" done={history.bills_done} total={history.bills_total} />
    </div>
  );
}

function Progress({ label, done, total }: { label: string; done: number; total: number }) {
  const share = total ? Math.min(1, done / total) : 1;
  return (
    <div>
      <div className="flex justify-between text-xs text-muted">
        <span>{label}</span>
        <span className="tabular-nums">
          {done.toLocaleString('ru-RU')} / {total.toLocaleString('ru-RU')}
        </span>
      </div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuenow={done}
        aria-valuemax={total}
        className="mt-1 h-1.5 overflow-hidden rounded-full bg-border"
      >
        <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${share * 100}%` }} />
      </div>
    </div>
  );
}

function HistoryButton({
  history,
  disabled,
  onStart,
  onPause,
}: {
  history: LabelingHistory | null;
  disabled: boolean;
  onStart: () => void;
  onPause: () => void;
}) {
  if (history?.state === 'running') {
    return (
      <button type="button" disabled={disabled} onClick={onPause} className={BUTTON}>
        Остановить
      </button>
    );
  }
  const label = history?.state === 'paused' ? 'Продолжить' : history ? 'Пройти ещё раз' : 'Разметить историю';
  return (
    <button type="button" disabled={disabled} onClick={onStart} className={BUTTON}>
      {label}
    </button>
  );
}
