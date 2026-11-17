import posthog, { type Properties } from 'posthog-js';

const DEFAULT_HOST = 'https://eu.i.posthog.com';

let ready = false;

// A join link holds the bill's public token and an invite code, either of which
// lets someone in: PostHog gets the page, not the keys.
const hideKeys = (value: unknown) =>
  typeof value === 'string' ? value.replace(/\/join\/[^/?#]+/g, '/join/:token').replace(/([?&]inv=)[^&#]*/g, '$1:code') : value;

const scrub = (properties?: Properties) => {
  for (const key of Object.keys(properties ?? {})) properties![key] = hideKeys(properties![key]);
};

export function initPostHog(): void {
  if (ready || typeof window === 'undefined') return;
  const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
  if (!key) return;

  // Telegram opens the app at …#tgWebAppData=<signed login>, valid for a day,
  // and PostHog would send that URL along as $current_url. The Telegram script
  // read it at load and keeps it, so the address no longer needs it.
  if (window.location.hash) {
    window.history.replaceState(window.history.state, '', window.location.pathname + window.location.search);
  }

  posthog.init(key, {
    api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST || DEFAULT_HOST,
    person_profiles: 'identified_only',
    capture_pageview: true,
    capture_pageleave: true,
    before_send: (event) => {
      scrub(event?.properties);
      scrub(event?.$set);
      scrub(event?.$set_once);
      return event;
    },
    autocapture: false,
    // Replays are opt-in because bill pages contain names, item details and
    // payment data. Set the flag to "0" only after an explicit privacy review.
    disable_session_recording: process.env.NEXT_PUBLIC_POSTHOG_DISABLE_REPLAY !== '0',
    session_recording: {
      maskAllInputs: true,
      maskTextSelector: '*',
    },
  });
  // The server and the bot send to the same project and say where they are from.
  posthog.register({ surface: 'mini_app' });
  ready = true;
}

export function isReady(): boolean {
  return ready;
}

export { posthog };
