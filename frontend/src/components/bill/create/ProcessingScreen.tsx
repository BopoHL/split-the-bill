'use client';

import Button from '@/components/ui/Button';
import PipelineSteps from '@/components/ui/PipelineSteps';
import { useTranslation } from '@/lib/i18n/useTranslation';
import ScanAnimation from './ScanAnimation';
import type { ScanMode, ScanPhase } from './useReceiptScan';

interface ProcessingScreenProps {
  mode: ScanMode;
  phase: ScanPhase;
  failed: boolean;
  /** The scan has been running long enough to be worth offering an out. */
  abortable?: boolean;
  onRetry: () => void;
  onFallbackToManual: () => void;
  /** Leave a scan that is still running. Omitted where the caller has already
   *  moved on and there is no screen left to hand back. */
  onAbort?: () => void;
}

export default function ProcessingScreen({
  mode,
  phase,
  failed,
  abortable = false,
  onRetry,
  onFallbackToManual,
  onAbort,
}: ProcessingScreenProps) {
  const { t } = useTranslation();

  if (failed) {
    return (
      <div className="space-y-4 py-2">
        <p className="text-center text-sm text-danger">{t('receipt.scanFailed')}</p>
        <div className="flex flex-col gap-2.5">
          <Button type="button" onClick={onRetry} className="w-full">
            {t('receipt.tryAgain')}
          </Button>
          <Button type="button" variant="outline" onClick={onFallbackToManual} className="w-full">
            {t('bill.createManually')}
          </Button>
        </div>
      </div>
    );
  }

  const steps = [
    {
      key: 'creating',
      label: mode === 'qr' ? t('receipt.stepCreatingBill') : t('receipt.stepCreating'),
    },
    { key: 'ocr', label: mode === 'qr' ? t('receipt.stepReadingQr') : t('receipt.stepOcr') },
    { key: 'llm', label: t('receipt.stepLlm') },
    { key: 'done', label: t('receipt.stepDone') },
  ] as const;

  const current = phase === 'llm' ? 2 : phase === 'ocr' ? 1 : 0;

  return (
    <div>
      <ScanAnimation />
      <PipelineSteps steps={steps} current={current} />
      <p className="mt-4 text-center font-mono text-[11px] tracking-[0.04em] text-muted-2">
        {t('receipt.scanDuration')}
      </p>
      {/* A slow scan is not a failed one, so the pipeline keeps running — but
          past a point the person needs a way back rather than a spinner. */}
      {abortable && onAbort && (
        <Button type="button" variant="outline" onClick={onAbort} className="mt-4 w-full">
          {t('receipt.abortScan')}
        </Button>
      )}
    </div>
  );
}
