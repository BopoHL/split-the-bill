import { initPostHog, isReady, posthog } from './posthog';
import type { AnalyticsEventName, AnalyticsEventProps } from './events';

export { AnalyticsEvent } from './events';
export type { AnalyticsEventName, AnalyticsEventProps } from './events';

export interface AnalyticsIdentity {
  language: string;
  currency: string;
  isPremium?: boolean;
}

export interface AnalyticsPersonProperties {
  pro: boolean;
  pro_trial: boolean;
  pro_subscription: boolean;
}

/** Properties every event carries while they hold, such as being inside the
 *  guided tour. Kept in memory so a reload never inherits a stale one. */
export interface AnalyticsContext {
  in_tour?: 'host' | 'guest';
}

let context: AnalyticsContext = {};

export function initAnalytics(): void {
  initPostHog();
}

export function identifyUser(userId: number, traits: AnalyticsIdentity): void {
  if (!isReady()) return;
  posthog.identify(String(userId), traits);
}

export function setPersonProperties(properties: AnalyticsPersonProperties): void {
  if (!isReady()) return;
  posthog.setPersonProperties(properties);
}

export function setAnalyticsContext(next: AnalyticsContext): void {
  context = next;
}

export function track<E extends AnalyticsEventName>(event: E, props: AnalyticsEventProps[E]): void {
  if (!isReady()) return;
  posthog.capture(event, { ...context, ...props });
}
