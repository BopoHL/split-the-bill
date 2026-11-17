'use client';

import { useMemo, useState, type ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { AnimatePresence, motion, useReducedMotion, type Transition, type Variants } from 'framer-motion';
import { ChevronLeft, X } from 'lucide-react';

import Modal from '@/components/ui/Modal';
import Button from '@/components/ui/Button';
import NumericKeypad from '@/components/ui/NumericKeypad';
import StepPeople from './StepPeople';
import StepPayment from './StepPayment';
import StepSource from './StepSource';
import ProcessingScreen from './ProcessingScreen';
import { useReceiptScan } from './useReceiptScan';

import { usePaymentChoice } from '@/hooks/usePaymentChoice';
import { MAX_PEOPLE } from '@/lib/constants';
import { buildDefaultBillTitle } from '@/lib/utils/billTitle';
import { scanQrCode, closeQrScanner, hapticFeedback } from '@/lib/telegram/init';
import { parseSoliqUrl } from '@/lib/utils/soliq';
import { showToast } from '@/lib/toast';
import { useStore } from '@/lib/store/useStore';
import { DEFAULT_CURRENCY, isCurrency, type Currency } from '@/lib/utils/currency';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { track, AnalyticsEvent } from '@/lib/analytics';
import { EASE_SLIDE } from '@/lib/motion';
import { TourAnchor } from '@/lib/tour/anchors';
import type { Bill } from '@/types/api';
import { useTour } from '@/lib/tour/useTour';
import { useInvitePrompt } from '@/lib/store/useInvitePrompt';

export interface BillCreateSubmit {
  title: string;
  total_sum: number;
  payment_details?: string;
  expected_people?: number;
  /** What the amounts on this bill will mean. Chosen on the first step. */
  currency: Currency;
  /** The items will be said out loud: the bill opens on the voice sheet. */
  voice?: boolean;
}

interface CreateBillWizardProps {
  isOpen: boolean;
  onClose: () => void;
  /** No-scan path: the parent creates an empty bill and navigates to it. */
  onSubmit: (data: BillCreateSubmit) => void;
  existingBills?: Bill[];
}

const STEPS = ['people', 'payment', 'source'] as const;
type Step = (typeof STEPS)[number];
/** Forward is 1, back is -1. */
type Direction = 1 | -1;

/** How long a step takes to move over; the progress fill keeps the same pace. */
const STEP_MOVE: Transition = { duration: 0.45, ease: EASE_SLIDE };
const SLIDE_TRANSITION: Transition = { x: STEP_MOVE, opacity: { duration: 0.24, ease: 'easeOut' } };

/** A step comes in from the side it lies on and the one before it leaves the
 *  other way, so going through the steps reads as moving along a strip.
 *  Without motion they only cross-fade. */
/** The sheet's own keys — close and back — in the «Bold» dress. */
const SHEET_KEY =
  'btn-hard-sm flex flex-shrink-0 items-center justify-center rounded-lg border-[1.5px] border-outline bg-surface text-foreground';

const slide = (moves: boolean): Variants => ({
  enter: (direction: Direction) => ({ x: moves ? `${direction * 100}%` : 0, opacity: 0 }),
  center: { x: 0, opacity: 1 },
  exit: (direction: Direction) => ({ x: moves ? `${direction * -100}%` : 0, opacity: 0 }),
});

/** A step, slid in and out the way the wizard goes. */
function StepSlide({ id, direction, variants, children }: {
  id: string;
  direction: Direction;
  variants: Variants;
  children: ReactNode;
}) {
  return (
    <AnimatePresence mode="popLayout" initial={false} custom={direction}>
      <motion.div
        key={id}
        className="flex flex-1 flex-col"
        custom={direction}
        variants={variants}
        initial="enter"
        animate="center"
        exit="exit"
        transition={SLIDE_TRANSITION}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}

/**
 * Creating a bill in three steps: how many people, where to pay, where the items
 * come from.
 *
 * Previously all three sat on one screen with the scan hidden behind a link,
 * which buried the headcount — the field that decides how the bill is laid out.
 * One decision per screen also leaves room to explain each one.
 */
export default function CreateBillWizard({
  isOpen,
  onClose,
  onSubmit,
  existingBills = [],
}: CreateBillWizardProps) {
  const { t, language } = useTranslation();
  const router = useRouter();
  const userId = useStore((s) => s.currentUser?.id);
  const savedCurrency = useStore((s) => s.currentUser?.settings?.currency);
  // What the person picked in settings before, or the money this app defaults to.
  const [currency, setCurrency] = useState<Currency>(
    isCurrency(savedCurrency) ? savedCurrency : DEFAULT_CURRENCY,
  );

  // The draft lives in local state and the parent remounts the wizard on every
  // open, so an abandoned half-filled form never comes back.
  const [{ step, direction }, setPosition] = useState<{ step: Step; direction: Direction }>({
    step: 'people',
    direction: 1,
  });
  const goTo = (next: Step) =>
    setPosition({ step: next, direction: STEPS.indexOf(next) > STEPS.indexOf(step) ? 1 : -1 });
  const variants = slide(!useReducedMotion());
  const [people, setPeople] = useState('3');
  const [peopleError, setPeopleError] = useState(false);
  // The card of the person's latest bill is the one to offer first.
  const lastDetails = useMemo(
    () => existingBills
      .filter((bill) => bill.owner_id === userId && bill.payment_details)
      .reduce<Bill | undefined>((latest, bill) => (!latest || bill.created_at > latest.created_at ? bill : latest), undefined)
      ?.payment_details,
    [existingBills, userId],
  );
  const payment = usePaymentChoice({ preferred: lastDetails });
  // Skip means «no card on this bill», whatever was chosen on the step.
  const [paymentSkipped, setPaymentSkipped] = useState(false);
  const paymentDetails = paymentSkipped ? undefined : payment.value || undefined;
  const [keypadOpen, setKeypadOpen] = useState(false);

  const peopleInt = parseInt(people, 10);
  const peopleValid = !isNaN(peopleInt) && peopleInt >= 1 && peopleInt <= MAX_PEOPLE;

  const defaultTitle = useMemo(
    () => buildDefaultBillTitle(existingBills, language, t, { ownerId: userId }),
    [existingBills, language, t, userId],
  );

  const scan = useReceiptScan({
    userId,
    expectedPeople: peopleValid ? peopleInt : undefined,
    paymentDetails,
    currency,
    onScanned: (billId) => {
      if (!useTour.getState().active) useInvitePrompt.getState().offer(billId);
      onClose();
      router.push(`/bill/${billId}`);
    },
  });

  const create = (voice: boolean) => {
    onSubmit({
      title: defaultTitle,
      total_sum: 0,
      payment_details: paymentDetails,
      expected_people: peopleValid ? peopleInt : undefined,
      currency,
      voice,
    });
    onClose();
  };
  const createEmpty = () => create(false);

  // Walking out of a scan that is taking too long: the scan is cancelled (which
  // takes the still-empty provisional bill with it) and the sheet closes, so the
  // person is back on their bills rather than stuck on a pipeline.
  const abandonScan = () => {
    scan.abort();
    onClose();
  };

  const handleScanQr = () => {
    const started = scanQrCode((text) => {
      const url = parseSoliqUrl(text);
      if (url) {
        closeQrScanner();
        scan.scanQr(url);
        return true; // valid receipt — close the scanner
      }
      hapticFeedback('error'); // not a Soliq receipt — keep scanning
      return false;
    }, t('receipt.scanQrHint'));
    // Desktop/web clients can't scan — tell the user to use a photo instead.
    if (!started) showToast(t('receipt.qrUnsupported'));
  };

  const skipPayment = () => {
    setPaymentSkipped(true);
    track(AnalyticsEvent.BillCreateStep, { step: 'source', payment_skipped: true });
    goTo('source');
  };

  const goNext = () => {
    if (step === 'people') {
      // Headcount is required: highlight the stepper instead of silently doing
      // nothing (STB-95).
      if (!peopleValid) {
        setPeopleError(true);
        return;
      }
      track(AnalyticsEvent.BillCreateStep, { step: 'payment' });
      goTo('payment');
    } else if (step === 'payment') {
      setPaymentSkipped(false);
      void payment.keep();
      track(AnalyticsEvent.BillCreateStep, { step: 'source', payment_skipped: false });
      goTo('source');
    }
  };

  const goBack = () => {
    if (step === 'payment') goTo('people');
    else if (step === 'source') goTo('payment');
  };

  const stepIndex = STEPS.indexOf(step);

  // Closing the sheet over a running scan means the same as the Abort button:
  // nobody is waiting for that receipt any more, so the task — and the empty
  // bill it was about to fill — must not finish behind the person's back.
  const closeSheet = scan.running ? abandonScan : onClose;

  return (
    <>
      {/* No title over the steps: what each asks is on its own face, and the
          sheet opens straight onto it. */}
      <Modal isOpen={isOpen} onClose={closeSheet} ariaLabel={t('bill.createTitle')} size="sm">
        <div className="space-y-4">
          <div className="-mr-1 -mt-1 flex justify-end">
            <button
              type="button"
              onClick={closeSheet}
              aria-label={t('common.close')}
              className={`${SHEET_KEY} h-10 w-10`}
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Progress — three segments across the sheet, filled up to the
              current one; the fill runs on into the next segment as the step
              slides in. */}
          {!scan.running && (
            <div className="flex gap-1.5">
              {STEPS.map((s, i) => (
                <span key={s} className="h-1 flex-1 overflow-hidden rounded-full bg-border">
                  <motion.span
                    className="block h-full origin-left rounded-full bg-accent"
                    initial={false}
                    animate={{ scaleX: i <= stepIndex ? 1 : 0 }}
                    transition={STEP_MOVE}
                  />
                </span>
              ))}
            </div>
          )}

          {scan.running ? (
            <ProcessingScreen
              mode={scan.mode}
              phase={scan.phase}
              failed={scan.failed}
              abortable={scan.abortable}
              onRetry={scan.retry}
              onFallbackToManual={createEmpty}
              onAbort={abandonScan}
            />
          ) : (
            <>
              {/* The body is as tall as the tallest step — the three sources
                  on a phone — so the sheet keeps its height from step to step.
                  The body reaches out to the sheet's edges and is clipped
                  across only, so a step slides all the way off them while
                  shadows under it and a list dropping from it stay whole. */}
              <div className="relative -mx-5 flex min-h-[310px] flex-col overflow-x-clip px-5">
                <StepSlide id={step} direction={direction} variants={variants}>
                  {step === 'people' && (
                    <div className="my-auto">
                      <StepPeople
                        value={people}
                        onChange={(next) => {
                          setPeople(next);
                          if (peopleError) setPeopleError(false);
                        }}
                        onOpenKeypad={() => setKeypadOpen(true)}
                        invalid={peopleError}
                        currency={currency}
                        onCurrencyChange={(next) => {
                          setCurrency(next);
                        }}
                      />
                    </div>
                  )}

                  {step === 'payment' && (
                    <div className="my-auto">
                      <StepPayment choice={payment} />
                    </div>
                  )}

                  {step === 'source' && (
                    <StepSource
                      qrAvailable={currency === 'uzs'}
                      onPhoto={scan.scanPhoto}
                      onScanQr={handleScanQr}
                      onManual={createEmpty}
                      onVoice={() => create(true)}
                    />
                  )}
                </StepSlide>
              </div>

              <div className="flex items-center gap-2.5">
                {stepIndex > 0 ? (
                  <button
                    type="button"
                    onClick={goBack}
                    aria-label={t('common.back')}
                    title={t('common.back')}
                    className={`${SHEET_KEY} h-[50px] w-[50px]`}
                  >
                    <ChevronLeft className="h-5 w-5" />
                  </button>
                ) : (
                  <Button type="button" variant="secondary" onClick={onClose}>
                    {t('common.cancel')}
                  </Button>
                )}

                <div className="ml-auto flex items-center gap-2">
                  {/* The card can be added later from the bill itself, and a step
                      with only a Next button doesn't say so. */}
                  {step === 'payment' && (
                    <Button type="button" variant="secondary" onClick={skipPayment}>
                      {t('bill.skipStep')}
                    </Button>
                  )}
                  {step !== 'source' && (
                    <Button type="button" onClick={goNext} data-tour={TourAnchor.WizardNext}>
                      {t('common.next')}
                    </Button>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </Modal>

      <NumericKeypad
        open={keypadOpen}
        label={t('bill.peopleCount')}
        max={MAX_PEOPLE}
        value={people}
        onChange={(v) => {
          setPeople(v);
          if (peopleError) setPeopleError(false);
        }}
        onClose={() => setKeypadOpen(false)}
      />
    </>
  );
}
