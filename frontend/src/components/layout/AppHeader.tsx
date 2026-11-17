'use client';

import { ReactNode } from 'react';

interface AppHeaderProps {
  children: ReactNode;
  /** Layout of the inner row — spacing differs per screen. */
  rowClassName?: string;
}

/**
 * The dark ink bar at the top of every screen.
 *
 * Owns only the chrome — background, stacking, and the padding that keeps
 * content clear of the notch and of Telegram's floating controls in fullscreen.
 * `sticky` rather than `fixed` on purpose: the padding already reserves the
 * inset, so no spacer element (and no height measurement) is needed.
 */
export default function AppHeader({
  children,
  rowClassName = 'gap-2.5 px-[18px] py-3.5',
}: AppHeaderProps) {
  return (
    <header className="sticky top-0 z-20 bg-bar pl-[var(--content-safe-left)] pr-[var(--content-safe-right)] pt-[var(--content-safe-top)] text-bar-fg">
      <div className={`mx-auto flex max-w-2xl items-center ${rowClassName}`}>{children}</div>
    </header>
  );
}
