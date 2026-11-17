'use client';

import { useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { flushSync } from 'react-dom';
import { useReducedMotion } from 'framer-motion';
import type { LucideIcon } from 'lucide-react';
import { useHorizontalSwipe } from '@/hooks/useHorizontalSwipe';
import { settleTiming } from '@/lib/motion';
import type { TourAnchorId } from '@/lib/tour/anchors';

export interface SwipeTab<T extends string> {
  value: T;
  label: string;
  icon: LucideIcon;
  /** A short figure after the label, such as how many things the tab holds. */
  badge?: string;
  content: ReactNode;
  tourAnchor?: TourAnchorId;
}

const COMMIT_SHARE = 0.22;
const COMMIT_VELOCITY = 0.35;
const EDGE_RESISTANCE = 0.25;

// Panels sit a gutter apart so a neighbour stays out of sight until it moves.
// At rest the track is shifted with `left`, not a transform, so nothing fixed
// inside a panel ends up positioned against the track; while it moves, the
// transform carries the offset from that resting place.
const restingLeft = (index: number) => `calc(${-index} * (100% + 2rem))`;
const trackTransform = (offset: number) => `translate3d(${offset}px, 0, 0)`;
const indicatorTransform = (progress: number) => `translate3d(${progress * 100}%, 0, 0)`;
const indicatorLabelsTransform = (progress: number, count: number) => `translate3d(${(progress * -100) / count}%, 0, 0)`;
const TAB_FACE = 'flex min-h-10 min-w-0 items-center justify-center gap-1.5 px-2 py-1.5 font-display text-[13px] font-bold';
const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));


/** How far the page is scrolled into the panels, measured from the point where
 *  the tabs stick under the header. */
interface ScrollOrigin {
  anchor: number;
  offset: number;
  scrollY: number;
}

function measureScrollOrigin(sticky: HTMLElement | null, pager: HTMLElement | null): ScrollOrigin {
  const { scrollY } = window;
  if (!sticky || !pager) return { anchor: 0, offset: 0, scrollY };
  const stuckAt = parseFloat(getComputedStyle(sticky).top) || 0;
  const anchor = pager.getBoundingClientRect().top + scrollY - stuckAt - sticky.offsetHeight;
  return { anchor, offset: Math.max(0, scrollY - anchor), scrollY };
}

function TabFace<T extends string>({ tab: { icon: Icon, label, badge } }: { tab: SwipeTab<T> }) {
  return (
    <>
      <Icon className="h-4 w-4 shrink-0" />
      <span className="break-words">{label}</span>
      {badge && <span className="shrink-0 font-mono text-[11px] tabular-nums opacity-70">{badge}</span>}
    </>
  );
}

/**
 * One segmented control over panels that page with the finger, sticking under
 * the screen's 4rem header row. Each panel stays mounted and keeps its own
 * place in the page, so paging back returns to where the reader left it.
 */
export default function SwipeTabs<T extends string>({ tabs, value, onChange, label, leftEdgeReserved, tourAnchor }: {
  tabs: readonly SwipeTab<T>[];
  value: T;
  onChange: (tab: T) => void;
  /** The tab list's accessible name. */
  label: string;
  /** A strip at the screen's left edge, in px, left to another swipe such as going back. */
  leftEdgeReserved?: number;
  tourAnchor?: TourAnchorId;
}) {
  const id = useId();
  const reduceMotion = useReducedMotion();
  const order = tabs.map((tab) => tab.value);
  const lastIndex = tabs.length - 1;
  const index = order.indexOf(value);
  const stickyRef = useRef<HTMLDivElement>(null);
  const pagerRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const indicatorRef = useRef<HTMLSpanElement>(null);
  const indicatorLabelsRef = useRef<HTMLSpanElement>(null);
  const dragX = useRef(0);
  const step = useRef(1);
  const dragging = useRef(false);
  const origin = useRef<ScrollOrigin | null>(null);
  const animations = useRef<Animation[]>([]);
  const scrollMemory = useRef<Partial<Record<T, number>>>({});
  const pendingScroll = useRef<number | null>(null);
  const shownTab = useRef(value);
  // While set, every panel is laid out side by side so a neighbour can slide in.
  // Each inactive panel is lifted to show the part the reader last saw there.
  const [moving, setMoving] = useState<Partial<Record<T, number>> | null>(null);

  const remembered = (tab: T) => scrollMemory.current[tab] ?? 0;

  useLayoutEffect(() => {
    const track = trackRef.current;
    if (!track) return;
    if (moving) {
      track.style.transform = trackTransform(dragX.current);
      return;
    }
    animations.current.forEach((animation) => animation.cancel());
    animations.current = [];
    for (const element of [track, indicatorRef.current, indicatorLabelsRef.current]) {
      if (element) element.style.transform = '';
    }
    if (pendingScroll.current != null) {
      window.scrollTo(0, pendingScroll.current);
      pendingScroll.current = null;
    }
  }, [moving, index]);

  // Switched from outside the pager, e.g. «Choose items»: no slide, but the
  // panel still opens where the reader left it.
  useLayoutEffect(() => {
    const previous = shownTab.current;
    if (previous === value) return;
    shownTab.current = value;
    const from = measureScrollOrigin(stickyRef.current, pagerRef.current);
    if (from.offset === 0) return;
    scrollMemory.current[previous] = from.offset;
    window.scrollTo(0, from.anchor + (scrollMemory.current[value] ?? 0));
  }, [value]);

  useEffect(() => {
    const running = animations;
    return () => running.current.forEach((animation) => animation.cancel());
  }, []);

  // Measured once per move, before the neighbour panel opens: reading layout
  // on every touchmove would force it again mid-gesture.
  const measureStep = () => {
    const track = trackRef.current;
    step.current = track ? track.clientWidth + (parseFloat(getComputedStyle(track).columnGap) || 0) || 1 : 1;
  };

  const progressAt = (dx: number) => clamp(index - dx / step.current, 0, lastIndex);

  const canAnimate = () => !reduceMotion && typeof trackRef.current?.animate === 'function';

  const commit = (target: number) => {
    const from = origin.current ?? measureScrollOrigin(stickyRef.current, pagerRef.current);
    if (target !== index) {
      const next = order[target];
      // The page may have been scrolled while the panels slid.
      const drift = window.scrollY - from.scrollY;
      scrollMemory.current[value] = Math.max(0, window.scrollY - from.anchor);
      pendingScroll.current = from.offset > 0
        ? from.anchor + Math.max(0, remembered(next) + drift)
        : null;
      shownTab.current = next;
      onChange(next);
    }
    origin.current = null;
    dragX.current = 0;
    setMoving(null);
  };

  const beginMoving = () => {
    measureStep();
    const from = measureScrollOrigin(stickyRef.current, pagerRef.current);
    origin.current = from;
    const lifts = Object.fromEntries(
      order.map((tab) => [tab, tab === value || from.offset === 0 ? 0 : from.offset - remembered(tab)]),
    ) as Record<T, number>;
    flushSync(() => setMoving(lifts));
  };

  const paintIndicator = (progress: number) => {
    if (indicatorRef.current) indicatorRef.current.style.transform = indicatorTransform(progress);
    if (indicatorLabelsRef.current) indicatorLabelsRef.current.style.transform = indicatorLabelsTransform(progress, tabs.length);
  };

  /** `velocity` is the finger's, in px/ms, negative towards the left. */
  const settle = (target: number, velocity = 0) => {
    const track = trackRef.current;
    const indicator = indicatorRef.current;
    const indicatorLabels = indicatorLabelsRef.current;
    if (!track || !indicator || !indicatorLabels || !canAnimate()) {
      commit(target);
      return;
    }
    const from = dragX.current;
    const to = (index - target) * step.current;
    const progress = progressAt(from);
    const timing = settleTiming(Math.abs(to - from), Math.max(0, Math.sign(to - from) * velocity));
    animations.current = [
      track.animate([{ transform: trackTransform(from) }, { transform: trackTransform(to) }], timing),
      indicator.animate([{ transform: indicatorTransform(progress) }, { transform: indicatorTransform(target) }], timing),
      indicatorLabels.animate(
        [
          { transform: indicatorLabelsTransform(progress, tabs.length) },
          { transform: indicatorLabelsTransform(target, tabs.length) },
        ],
        timing,
      ),
    ];
    animations.current[0].onfinish = () => commit(target);
  };

  const select = (tab: T) => {
    const target = order.indexOf(tab);
    if (target === index || moving) return;
    if (!canAnimate()) {
      commit(target);
      return;
    }
    beginMoving();
    settle(target);
  };

  // The panels end where their content does; the page below them is still the
  // tab's, so a swipe that starts there turns the tab too.
  useHorizontalSwipe(pagerRef, {
    onSwipeStart: () => {
      dragging.current = !moving;
      if (!dragging.current) return;
      dragX.current = 0;
      beginMoving();
    },
    onSwipeMove: (dx) => {
      if (!dragging.current) return;
      const pastEdge = (index === 0 && dx > 0) || (index === lastIndex && dx < 0);
      dragX.current = pastEdge ? dx * EDGE_RESISTANCE : dx;
      if (trackRef.current) trackRef.current.style.transform = trackTransform(dragX.current);
      paintIndicator(progressAt(dragX.current));
    },
    onSwipeEnd: (dx, velocity) => {
      if (!dragging.current) return;
      dragging.current = false;
      const flick = Math.abs(velocity) > COMMIT_VELOCITY ? Math.sign(velocity) : 0;
      const far = Math.abs(dx) > step.current * COMMIT_SHARE ? Math.sign(dx) : 0;
      const direction = flick || far;
      settle(clamp(index - direction, 0, lastIndex), velocity);
    },
  }, { leftEdgeReserved, reachesPageBottom: true });

  return (
    <>
      <div
        ref={stickyRef}
        className="sticky top-[calc(4rem+var(--content-safe-top))] z-10 -mx-4 bg-background px-4 pb-2.5 pt-1"
      >
        <div
          role="tablist"
          aria-label={label}
          data-tour={tourAnchor}
          style={{ '--tab-index': index, '--tab-count': tabs.length } as CSSProperties}
          className="relative grid grid-cols-[repeat(var(--tab-count),minmax(0,1fr))] rounded-lg border-[1.5px] border-outline bg-surface p-1 shadow-[var(--shadow-hard-sm)]"
        >
          {tabs.map((tab, tabIndex) => {
            const selected = value === tab.value;
            return (
              <button
                key={tab.value}
                type="button"
                role="tab"
                id={`${id}-${tab.value}`}
                aria-controls={`${id}-${tab.value}-panel`}
                aria-selected={selected}
                aria-label={tab.badge ? `${tab.label} ${tab.badge}` : undefined}
                data-tour={tab.tourAnchor}
                tabIndex={selected ? 0 : -1}
                onClick={() => select(tab.value)}
                onKeyDown={(event) => {
                  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
                  event.preventDefault();
                  const next = event.key === 'Home'
                    ? 0
                    : event.key === 'End'
                      ? lastIndex
                      : clamp(tabIndex + (event.key === 'ArrowRight' ? 1 : -1), 0, lastIndex);
                  select(order[next]);
                  document.getElementById(`${id}-${order[next]}`)?.focus();
                }}
                className={`${TAB_FACE} rounded-[5px] text-muted transition-colors hover:text-foreground`}
              >
                <TabFace tab={tab} />
              </button>
            );
          })}
          {/* The pill carries its own inverted copy of the labels, shifted back
              into line, so whatever sits under it reads inverted mid-swipe too. */}
          <span
            ref={indicatorRef}
            aria-hidden="true"
            data-testid="tabs-indicator"
            className="pointer-events-none absolute inset-y-1 left-1 w-[calc((100%-8px)/var(--tab-count))] overflow-hidden rounded-[5px] bg-emphasis [transform:translate3d(calc(var(--tab-index)*100%),0,0)]"
          >
            <span
              ref={indicatorLabelsRef}
              className="grid h-full w-[calc(var(--tab-count)*100%)] grid-cols-[repeat(var(--tab-count),minmax(0,1fr))] text-emphasis-fg [transform:translate3d(calc(var(--tab-index)*-100%/var(--tab-count)),0,0)]"
            >
              {tabs.map((tab) => (
                <span key={tab.value} className={TAB_FACE}>
                  <TabFace tab={tab} />
                </span>
              ))}
            </span>
          </span>
        </div>
      </div>

      {/* The pager reaches into the page gutter so card shadows are not clipped. */}
      <div ref={pagerRef} className="-mx-4 overflow-x-clip px-4">
        <div
          ref={trackRef}
          style={{ left: restingLeft(index) }}
          className={`relative flex items-start gap-8 ${moving ? 'will-change-transform' : ''}`}
        >
          {tabs.map((tab) => {
            const active = tab.value === value;
            return (
              // A panel out of view stays laid out, just folded to no height,
              // so opening it for a swipe costs a repaint instead of laying out
              // a whole panel under the finger.
              <section
                key={tab.value}
                role="tabpanel"
                id={`${id}-${tab.value}-panel`}
                aria-labelledby={`${id}-${tab.value}`}
                aria-hidden={active ? undefined : true}
                inert={!active}
                style={moving && !active ? { transform: `translate3d(0, ${moving[tab.value] ?? 0}px, 0)` } : undefined}
                className={`w-full min-w-0 shrink-0 ${active || moving ? '' : 'h-0 overflow-hidden'}`}
              >
                <div className="pb-5 pt-3">{tab.content}</div>
              </section>
            );
          })}
        </div>
      </div>
    </>
  );
}
