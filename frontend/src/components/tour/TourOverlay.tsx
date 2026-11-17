'use client';

import { useEffect, useEffectEvent, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { seatDemoFriends } from '@/lib/api/demoBills';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { holdBackButton } from '@/lib/telegram/init';
import { showToast } from '@/lib/toast';
import { findTarget } from '@/lib/tour/anchors';
import { inspectTarget } from '@/lib/tour/visibility';
import type { TourStage, TourStep } from '@/lib/tour/script';
import { useTour, useTourStep } from '@/lib/tour/useTour';
import DemoScanScene from './DemoScanScene';
import StagedCard from './StagedCard';
import Spotlight, { type HoleMode } from './Spotlight';
import TourBubble from './TourBubble';
import TourFinale from './TourFinale';
import { useTourExit } from './useTourExit';
import { useTourTarget } from './useTourTarget';

/** How long to wait for a step's element before deciding the press that was
 *  meant to bring it on went nowhere — a request failed, a sheet was closed. */
const REWIND_AFTER_MS = 6000;
/** How often a `use` step looks whether its part of the screen has gone. */
const GONE_POLL_MS = 200;

const HOLE_MODE: Record<Exclude<TourStep['kind'], 'scene'>, HoleMode> = {
  tap: 'pass',
  look: 'block',
  use: 'pass',
  stage: 'catch',
};

/** The guided tour, over whatever screen it has reached. Mounted once for the
 *  whole app; draws nothing while no tour runs. */
export default function TourOverlay() {
  const step = useTourStep();
  const running = step != null;

  useEffect(() => {
    if (running) return holdBackButton();
  }, [running]);

  // Escape would close the sheet a step is pointing into.
  useEffect(() => {
    if (!running) return;
    const swallowEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') event.stopImmediatePropagation();
    };
    window.addEventListener('keydown', swallowEscape, true);
    return () => window.removeEventListener('keydown', swallowEscape, true);
  }, [running]);

  if (!step || typeof document === 'undefined') return null;
  return createPortal(<TourLayer step={step} />, document.body);
}

function TourLayer({ step }: { step: TourStep }) {
  const { t, language } = useTranslation();
  const rootRef = useRef<HTMLDivElement>(null);
  const { skip, complete } = useTourExit();
  const steps = useTour((state) => state.tour.steps);
  const stepIndex = useTour((state) => state.stepIndex);
  const friends = useTour((state) => state.friends);
  const cardStaged = useTour((state) => state.cardStaged);
  const [staging, setStaging] = useState(false);

  const target = step.kind === 'scene' ? step.waitFor : step.target;
  const box = useTourTarget(step.id, target, rootRef);

  // The last step's «Got it» ends the tour; there is no scene after it.
  const moveOn = () => {
    if (stepIndex < steps.length - 1) {
      useTour.getState().advance(step.id);
      return;
    }
    complete();
    useTour.getState().stop();
  };

  // A real press on the lit element is what moves a `tap` step on.
  useEffect(() => {
    if (step.kind !== 'tap') return;
    const onClick = (event: MouseEvent) => {
      const element = findTarget(step.target);
      if (element && event.target instanceof Node && element.contains(event.target)) {
        useTour.getState().advance(step.id);
      }
    };
    document.addEventListener('click', onClick, true);
    return () => document.removeEventListener('click', onClick, true);
  }, [step]);

  // A `use` step lasts as long as its part of the screen: once the sheet it
  // lit has closed, whatever was to be done there is done.
  useEffect(() => {
    if (step.kind !== 'use') return;
    let seen = findTarget(step.target) != null;
    const timer = setInterval(() => {
      if (findTarget(step.target)) seen = true;
      else if (seen) useTour.getState().advance(step.id);
    }, GONE_POLL_MS);
    return () => clearInterval(timer);
  }, [step]);

  // An optional step whose element is not on the page — nothing to pay before
  // anything was picked — is passed over at once, not waited on under the dim.
  const passOver = useEffectEvent(moveOn);
  useEffect(() => {
    if (step.optional && step.kind !== 'scene' && !findTarget(step.target)) passOver();
  }, [step]);

  // Still nothing to light a while after a press, and that press can be made
  // again: it went nowhere, so offer it once more instead of waiting forever.
  useEffect(() => {
    const previous = steps[stepIndex - 1];
    if (box || previous?.kind !== 'tap') return;
    const timer = setTimeout(() => {
      const element = findTarget(previous.target);
      if (element && !element.matches(':disabled') && inspectTarget(element, rootRef.current).kind === 'ready') {
        useTour.getState().rewind(step.id);
      }
    }, REWIND_AFTER_MS);
    return () => clearTimeout(timer);
  }, [box, steps, stepIndex, step.id]);

  const stages: Record<TourStage, () => Promise<void>> = {
    fillCard: async () => {
      const { stageCard, advance } = useTour.getState();
      stageCard();
      advance(step.id);
    },
    startScan: async () => useTour.getState().advance(step.id),
    // The whole row opens the seat, but its name renames it and its face seats
    // somebody — so the press is the tour's, and it lands on the row itself.
    openSeat: async () => {
      const row = target && findTarget(target);
      if (row?.getAttribute('aria-expanded') === 'false') row.click();
      useTour.getState().advance(step.id);
    },
    inviteFriends: async () => {
      const { demoBillId, setFriends, advance } = useTour.getState();
      if (demoBillId == null) return;
      const bill = await seatDemoFriends(demoBillId, language);
      setFriends(
        bill.participants
          .filter((seat) => seat.is_guest && seat.guest_name)
          .sort((a, b) => a.seat_index - b.seat_index)
          .map((seat) => seat.guest_name as string),
      );
      advance(step.id);
    },
  };

  const runStage = async (stage: TourStage) => {
    if (staging) return;
    setStaging(true);
    try {
      await stages[stage]();
    } catch {
      showToast(t('common.error'));
    } finally {
      setStaging(false);
    }
  };

  // Once the last words are up there is nothing left to skip; until then, even
  // on the way to them, there must always be a way out.
  const finaleShown = step.kind === 'scene' && step.scene === 'finale' && box != null;
  const copy = (key: string) =>
    t(`tour.${step.id}.${key}`, {
      first: friends[0] ?? '',
      second: friends[1] ?? '',
      next: t('common.next'),
      confirm: t('common.confirm'),
      assign: t('bill.assign'),
      receipt: t('bill.receipt'),
      participants: t('bill.participants'),
      close: t('bill.closeBill'),
      split: t('bill.splitRemainderAmongAll'),
      choose: t('bill.chooseItems'),
      paid: t('bill.iPaidShort'),
    });

  return (
    <div ref={rootRef} className="pointer-events-none fixed inset-0 z-[65]" data-testid="tour">
      {step.kind === 'scene' ? (
        step.scene === 'scan' ? (
          <DemoScanScene onSkip={skip} />
        ) : box ? (
          <TourFinale />
        ) : (
          <Spotlight box={null} mode="block" />
        )
      ) : (
        <>
          <Spotlight
            box={box}
            mode={HOLE_MODE[step.kind]}
            catchLabel={copy('title')}
            onCatch={step.kind === 'stage' ? () => void runStage(step.stage) : undefined}
          />
          {cardStaged && <StagedCard ignore={rootRef} />}
          {box && (
            <TourBubble
              key={step.id}
              hole={box}
              title={copy('title')}
              text={copy('text')}
              progress={`${String(stepIndex + 1).padStart(2, '0')} / ${String(steps.length).padStart(2, '0')}`}
              action={step.kind === 'look' ? { label: t('tour.gotIt'), onClick: moveOn } : undefined}
            />
          )}
        </>
      )}

      {!finaleShown && (
        <button
          type="button"
          onClick={skip}
          className="pointer-events-auto fixed right-[calc(1rem+var(--content-safe-right))] top-[calc(0.75rem+var(--content-safe-top))] rounded-full border-[1.5px] border-outline bg-surface px-3 py-1.5 font-display text-[12px] font-bold text-foreground shadow-[var(--shadow-hard-sm)]"
        >
          {t('tour.skip')}
        </button>
      )}
    </div>
  );
}
