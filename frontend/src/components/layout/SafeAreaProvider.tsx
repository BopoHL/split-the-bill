'use client';

import { useEffect } from 'react';
import {
  getContentSafeAreaInsets,
  getSafeAreaInsets,
  isFullscreen,
  onViewportChanged,
} from '@/lib/telegram/init';

const EDGES = ['top', 'right', 'bottom', 'left'] as const;

const cssVariable = (kind: 'safe' | 'content-safe', edge: (typeof EDGES)[number]) =>
  `--${kind}-${edge}`;

/**
 * Publishes the usable area as CSS variables so layout code never has to know
 * whether the insets came from Telegram or from the browser.
 *
 * Two independent sources stack up in fullscreen: the device cutout
 * (`safeAreaInset`) and Telegram's own floating controls (`contentSafeAreaInset`).
 * `--safe-*` is the cutout alone; `--content-safe-*` additionally clears the
 * close/menu buttons and is what fixed or edge-aligned UI should use.
 *
 * On clients without Bot API 8.0 the variables fall back to `env(safe-area-inset-*)`,
 * which is why the defaults live in globals.css rather than here.
 */
export default function SafeAreaProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const root = document.documentElement;

    const apply = () => {
      const safe = getSafeAreaInsets();
      const content = getContentSafeAreaInsets();

      root.classList.toggle('tg-fullscreen', isFullscreen());

      EDGES.forEach((edge) => {
        const safeValue = safe?.[edge];
        const contentValue = content?.[edge];
        const safeName = cssVariable('safe', edge);
        const contentName = cssVariable('content-safe', edge);

        if (typeof safeValue === 'number') {
          root.style.setProperty(safeName, `${safeValue}px`);
        } else {
          // Keep the stylesheet's env(safe-area-inset-*) fallback for every
          // edge the Telegram client did not report.
          root.style.removeProperty(safeName);
        }

        if (typeof safeValue === 'number' && typeof contentValue === 'number') {
          root.style.setProperty(contentName, `${safeValue + contentValue}px`);
        } else if (typeof safeValue === 'number') {
          root.style.setProperty(contentName, `${safeValue}px`);
        } else if (typeof contentValue === 'number') {
          // A partially implemented client may expose only the content inset.
          // Add it to the browser-backed device inset instead of replacing the
          // real cutout with an assumed zero.
          root.style.setProperty(contentName, `calc(var(${safeName}) + ${contentValue}px)`);
        } else {
          root.style.removeProperty(contentName);
        }
      });
    };

    apply();
    const unsubscribe = onViewportChanged(apply);
    window.addEventListener('resize', apply);
    window.addEventListener('orientationchange', apply);

    return () => {
      unsubscribe();
      window.removeEventListener('resize', apply);
      window.removeEventListener('orientationchange', apply);
      root.classList.remove('tg-fullscreen');
      EDGES.forEach((edge) => {
        root.style.removeProperty(cssVariable('safe', edge));
        root.style.removeProperty(cssVariable('content-safe', edge));
      });
    };
  }, []);

  return <>{children}</>;
}
