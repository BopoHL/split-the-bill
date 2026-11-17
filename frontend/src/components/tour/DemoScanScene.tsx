'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import Button from '@/components/ui/Button';
import ProcessingScreen from '@/components/bill/create/ProcessingScreen';
import type { ScanPhase } from '@/components/bill/create/useReceiptScan';
import type { BillDetail } from '@/types/api';
import { createDemoBill, eraseDemoBill } from '@/lib/api/demoBills';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { EASE_OUT } from '@/lib/motion';
import { DEMO_CARD } from '@/lib/tour/script';
import { useTour } from '@/lib/tour/useTour';

/** When each phase of the pretend scan lights up, and how long the whole of
 *  it lasts at the least — long enough to read, far shorter than a real one. */
const OCR_AT_MS = 900;
const LLM_AT_MS = 2100;
const SHORTEST_MS = 3400;

/**
 * The tour's scan: the same progress the real one shows, over a prepared
 * receipt the server turns into the demo bill. Leaves for that bill once both
 * the bill and the show are done.
 */
export default function DemoScanScene({ onSkip }: { onSkip: () => void }) {
  const { t, language } = useTranslation();
  const router = useRouter();
  const [phase, setPhase] = useState<ScanPhase>('creating');
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  // One bill per attempt, even when the effect runs twice for the same one.
  const request = useRef<{ attempt: number; bill: Promise<BillDetail> } | null>(null);

  useEffect(() => {
    let wanted = true;
    const timers = [
      setTimeout(() => setPhase('ocr'), OCR_AT_MS),
      setTimeout(() => setPhase('llm'), LLM_AT_MS),
    ];
    const shortest = new Promise((resolve) => setTimeout(resolve, SHORTEST_MS));
    if (request.current?.attempt !== attempt) {
      const card = useTour.getState().cardStaged ? DEMO_CARD : undefined;
      request.current = { attempt, bill: createDemoBill(language, card) };
    }

    Promise.all([request.current.bill, shortest])
      .then(([bill]) => {
        const { active, setDemoBill, advance } = useTour.getState();
        // The tour was left while the bill was on its way.
        if (!active) {
          void eraseDemoBill(bill.id).catch(() => {});
          return;
        }
        setDemoBill(bill.id);
        if (!wanted) return;
        router.push(`/bill/${bill.id}`);
        advance('scanning');
      })
      .catch(() => {
        if (wanted) setFailed(true);
      });

    return () => {
      wanted = false;
      timers.forEach(clearTimeout);
    };
  }, [attempt, language, router]);

  const retry = () => {
    setFailed(false);
    setPhase('creating');
    setAttempt((n) => n + 1);
  };

  return (
    <div className="pointer-events-auto fixed inset-0 flex touch-none items-center justify-center bg-black/60 pl-[calc(1rem+var(--content-safe-left))] pr-[calc(1rem+var(--content-safe-right))]">
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.24, ease: EASE_OUT }}
        className="w-full max-w-sm rounded-[12px] border-[1.5px] border-outline bg-surface p-5 text-foreground shadow-[var(--shadow-hard)]"
      >
        <h2 className="mb-4 text-center font-display text-[17px] font-bold">{t('tour.scanning.title')}</h2>
        {failed ? (
          <div className="space-y-3">
            <p className="text-center text-sm text-danger">{t('tour.scanning.failed')}</p>
            <Button type="button" onClick={retry} className="w-full">
              {t('receipt.tryAgain')}
            </Button>
            <Button type="button" variant="outline" onClick={onSkip} className="w-full">
              {t('tour.skip')}
            </Button>
          </div>
        ) : (
          <ProcessingScreen mode="photo" phase={phase} failed={false} onRetry={retry} onFallbackToManual={onSkip} />
        )}
      </motion.div>
    </div>
  );
}
