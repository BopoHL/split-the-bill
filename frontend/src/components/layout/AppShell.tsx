'use client';

import { useEffect, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { usePathname, useRouter } from 'next/navigation';
import { useStore } from '@/lib/store/useStore';
import {
  initTelegramSDK,
  getTelegramUser,
  getTelegramTheme,
  waitForTelegramWebApp,
  getStartParam,
  isDevMockEnabled,
  requestWriteAccess,
} from '@/lib/telegram/init';
import { getUserByTelegramId, syncTelegramWriteAccess } from '@/lib/api/users';
import { initAnalytics, identifyUser, track, AnalyticsEvent } from '@/lib/analytics';
import {
  claimSeat,
  getSeatsByToken,
  joinByToken,
  joinWelcome,
  updatePaymentStatus,
} from '@/lib/api/bills';
import ExternalLanding from '@/components/ui/ExternalLanding';
import OfflineGate from '@/components/ui/OfflineGate';
import Toaster from '@/components/ui/Toaster';
import SafeAreaProvider from '@/components/layout/SafeAreaProvider';
import TourOverlay from '@/components/tour/TourOverlay';
import { arriveAsGuest } from '@/lib/tour/arrival';
import { useTour } from '@/lib/tour/useTour';
import Paywall from '@/components/pro/Paywall';
import { setPaymentRequiredHandler, type PaymentRequired } from '@/lib/api/client';
import { usePro, useProGate } from '@/lib/store/usePro';
import { schemeOf, shownTheme } from '@/lib/utils/themes';
import type { PaywallReason } from '@/types/pro';
import { showToast } from '@/lib/toast';
import { translateApiError } from '@/lib/utils/apiError';
import { useTranslation } from '@/lib/i18n/useTranslation';
import { useZoomLock } from '@/hooks/useZoomLock';
import { useViewportRestore } from '@/hooks/useViewportRestore';
import { HomeScreenShortcutProvider } from '@/hooks/useHomeScreenShortcut';
import {
  PRO_START,
  parseBillStartParam,
  parseInviteStartParam,
  parseSeatInviteStartParam,
  startParamKind,
  startSource,
} from '@/lib/utils/startParam';
import { resolveInvite } from '@/lib/api/invites';
import {
  shouldRequestTelegramWriteAccess,
  shouldSendJoinWelcome,
} from '@/lib/utils/joinWelcome';

// An unknown start parameter is a campaign's own label, kept for attribution.
const START_REF_MAX = 64;
const PAYWALL_FEATURES: readonly PaywallReason[] = ['analytics', 'reminders', 'themes'];

/** What the paywall opens over when a request turns out to need Pro. */
function paywallReason(detail: PaymentRequired): PaywallReason {
  if (detail.code === 'SCAN_LIMIT') return 'scans';
  return PAYWALL_FEATURES.find((reason) => reason === detail.feature) ?? 'general';
}

// Dev-only mock banner. The `process.env.NODE_ENV !== 'production'` guard
// is a compile-time constant — in a prod build this resolves to `false`,
// the conditional `dynamic(import(...))` call is dead, and the chunk for
// DevMockBanner is never emitted.
const DevMockBanner =
  process.env.NODE_ENV !== 'production'
    ? dynamic(() => import('@/components/dev/DevMockBanner'), { ssr: false })
    : null;

export default function AppShell({ children }: Readonly<{ children: React.ReactNode }>) {
  const { theme, setTheme, currentUser, setCurrentUser, language, applyServerSettings } = useStore();
  const [isTelegram, setIsTelegram] = useState<boolean | null>(null);
  const [mounted, setMounted] = useState(false);
  const router = useRouter();
  // Captured in a ref so the one-time init effect doesn't re-run on language change.
  const { t } = useTranslation();
  const tRef = useRef(t);
  tRef.current = t;

  useZoomLock();
  useViewportRestore();

  // An invite's page is up: home may welcome them when they come back to it.
  const pathname = usePathname();
  useEffect(() => {
    if (pathname !== '/') useTour.getState().setArriving(false);
  }, [pathname]);

  useEffect(() => {
    let cancelled = false;

    // In a non-prod build the dev mock is installed BEFORE we touch
    // `window.Telegram.WebApp`. The dynamic import + the guard on
    // `process.env.NODE_ENV` together ensure the mock module is not
    // bundled into production at all.
    const ensureMockReady = async () => {
      if (process.env.NODE_ENV !== 'production' && isDevMockEnabled()) {
        const mod = await import('@/lib/telegram/devMock');
        if (!window.Telegram?.WebApp?.initData) {
          mod.installMockWebApp();
        }
      }
    };

    const initialize = async () => {
      await ensureMockReady();
      if (cancelled) return;

      const isTG = await waitForTelegramWebApp();
      if (cancelled) return;
      // Read the invite before the account exists: first-touch attribution is
      // written when the row is created, and never again.
      const startParam = isTG ? getStartParam() : null;
      const inviteParam = parseInviteStartParam(startParam);
      const arrivesByInvite = Boolean(
        inviteParam || parseSeatInviteStartParam(startParam) || startParam?.startsWith('join_'),
      );
      // Home is only passed through on the way to the invite's bill: its
      // welcome and tour wait, from before home is first drawn.
      if (arrivesByInvite) useTour.getState().setArriving(true);
      setMounted(true);
      setIsTelegram(isTG);

      if (!isTG) return;

      const webApp = initTelegramSDK();
      if (!webApp) return;

      initAnalytics();
      const start = startParamKind(startParam);
      const source = startSource(startParam);
      track(AnalyticsEvent.AppOpen, {
        platform: webApp.platform,
        start,
        ...(source ? { source } : {}),
        ...(start === 'other' && startParam ? { start_ref: startParam.slice(0, START_REF_MAX) } : {}),
      });

      const telegramTheme = getTelegramTheme();
      setTheme(telegramTheme);

      const telegramUser = getTelegramUser();
      if (!telegramUser) return;

      const allowsWriteToPm = telegramUser.allows_write_to_pm === true;

      getUserByTelegramId(
        telegramUser.id,
        telegramUser.username || `${telegramUser.first_name} ${telegramUser.last_name || ''}`.trim(),
        telegramUser.photo_url,
        window.Telegram?.WebApp?.initData,
        inviteParam?.code,
        allowsWriteToPm,
        { start, source },
      ).then(async (user) => {
        if (!user || cancelled) {
          useTour.getState().setArriving(false);
          return;
        }
        setCurrentUser(user);
        void usePro.getState().load(user.id);
        if (startParam === PRO_START) usePro.getState().openPaywall();
        // Server-stored preferences win over the locally-persisted ones.
        applyServerSettings(user.settings);
        const { language: lang, currency: curr } = useStore.getState();
        identifyUser(user.id, {
          language: lang,
          currency: curr,
          isPremium: telegramUser.is_premium,
        });

        const syncWriteAccess = async (allowed: boolean): Promise<boolean> => {
          try {
            const updated = await syncTelegramWriteAccess(user.id, allowed);
            if (!cancelled) {
              setCurrentUser(updated);
              applyServerSettings(updated.settings);
            }
          } catch (err) {
            console.error('Failed to sync Telegram write access:', err);
          }
          return allowed;
        };

        const writeAccessPromise = shouldRequestTelegramWriteAccess(allowsWriteToPm)
          ? requestWriteAccess().then(syncWriteAccess)
          : Promise.resolve(true);

        const sendJoinWelcome = (billId: number) => {
          if (!shouldSendJoinWelcome(user.settings)) return;
          writeAccessPromise.then((granted) => {
            if (granted) {
              joinWelcome(billId, useStore.getState().language).catch(() => {});
            }
          });
        };

        // Leaving home, the flag goes once the next page is up (the pathname
        // effect below); staying on it, it goes when this is done. Lowered
        // right after the push, it let home start its tour on the way out.
        let leftHome = false;
        const leave = (path: string) => {
          leftHome = true;
          router.push(path);
        };

        try {
          if (inviteParam) {
            const invite = await resolveInvite(inviteParam.code).catch(() => null);
            if (!invite) {
              showToast(tRef.current('errors.billNotFound'));
              return;
            }
            // Seats have to be picked by hand; the code rides along so the detour
            // does not lose who did the inviting, and neither is the seat the
            // invite named — the picker asks about it before showing the rest.
            const pickSeatPath = invite.seat_participant_id
              ? `/join/${invite.public_token}?inv=${invite.code}&seat=${invite.seat_participant_id}`
              : `/join/${invite.public_token}?inv=${invite.code}`;
            try {
              if (invite.seat_participant_id) {
                await claimSeat(
                  invite.bill_id,
                  invite.seat_participant_id,
                  user.id,
                  invite.code,
                );
                if (inviteParam.confirmPayment) {
                  await updatePaymentStatus(
                    invite.bill_id,
                    invite.seat_participant_id,
                    true,
                    user.id,
                  );
                  track(AnalyticsEvent.PaymentMarked, { bill_id: invite.bill_id, paid: true, by: 'self', from: 'invite' });
                }
              } else {
                await joinByToken(invite.public_token, user.id, invite.code);
              }
              track(AnalyticsEvent.ParticipantJoined, {
                via: 'invite',
                channel: invite.channel,
                bill_id: invite.bill_id,
              });
              arriveAsGuest(invite.bill_id);
              sendJoinWelcome(invite.bill_id);
              leave(`/bill/${invite.bill_id}`);
            } catch (err) {
              console.error('Failed to accept invite:', err);
              const resp = (err as { response?: { status?: number; data?: { detail?: string } } })
                ?.response;
              const detail = resp?.data?.detail;
              if (detail === 'SEAT_REQUIRED') {
                leave(pickSeatPath);
              } else if (detail === 'SEAT_MOVE_CONFIRM') {
                // They already sit somewhere on this bill, so the link would move
                // them and swap their items. That is a decision, not a side
                // effect of a tap — hand them the seat picker, which shows what
                // is on every plate and asks before it moves anyone.
                leave(pickSeatPath);
              } else if (detail === 'SEAT_TAKEN') {
                showToast(tRef.current('bill.seatAlreadyTaken'));
                leave(pickSeatPath);
              } else if (detail === 'OWNER_SEAT_FIXED' || detail === 'SEAT_PAID') {
                // Somebody already on the bill tapped a link to another seat —
                // the owner opening the invite they sent, or a payer following
                // somebody else's. The seat is refused; the bill is theirs.
                showToast(translateApiError(detail, tRef.current));
                leave(`/bill/${invite.bill_id}`);
              } else if (detail === 'BILL_FULL' || detail === 'Bill is full') {
                showToast(tRef.current('errors.billFull'));
              } else if (resp?.status === 404 || detail === 'Bill not found') {
                showToast(tRef.current('errors.billNotFound'));
              } else if (
                detail === 'Bill is closed'
                || detail === 'Action not allowed on this bill state'
              ) {
                // A stranger following an invite to a bill that has since closed.
                // Whoever already has a seat on it never reaches here — they are
                // handed the bill itself, history and all.
                leave('/closed');
              } else {
                showToast(tRef.current('common.error'));
              }
            }
            return;
          }

          const seatInvite = parseSeatInviteStartParam(startParam);
          if (seatInvite) {
            let billId: number | null = null;
            try {
              const seats = await getSeatsByToken(seatInvite.token, user.id);
              billId = seats.bill_id;
              await claimSeat(seats.bill_id, seatInvite.participantId, user.id, null, false, seatInvite.token);
              if (seatInvite.confirmPayment) {
                await updatePaymentStatus(seats.bill_id, seatInvite.participantId, true, user.id);
                track(AnalyticsEvent.PaymentMarked, { bill_id: seats.bill_id, paid: true, by: 'self', from: 'invite' });
              }
              track(AnalyticsEvent.ParticipantJoined, { via: 'invite', channel: 'seat', bill_id: seats.bill_id });
              arriveAsGuest(seats.bill_id);
              sendJoinWelcome(seats.bill_id);
              leave(`/bill/${seats.bill_id}`);
            } catch (err) {
              console.error('Failed to accept personal seat invite:', err);
              const resp = (err as { response?: { status?: number; data?: { detail?: string } } })
                ?.response;
              const detail = resp?.data?.detail;
              if (detail === 'SEAT_MOVE_CONFIRM') {
                // Same as above: an occupied seat is never given up silently.
                leave(`/join/${seatInvite.token}?seat=${seatInvite.participantId}`);
              } else if (detail === 'SEAT_TAKEN') {
                showToast(tRef.current('bill.seatAlreadyTaken'));
                leave(`/join/${seatInvite.token}`);
              } else if ((detail === 'OWNER_SEAT_FIXED' || detail === 'SEAT_PAID') && billId) {
                showToast(translateApiError(detail, tRef.current));
                leave(`/bill/${billId}`);
              } else if (detail === 'BILL_FULL' || detail === 'Bill is full') {
                showToast(tRef.current('errors.billFull'));
                leave(`/join/${seatInvite.token}`);
              } else if (resp?.status === 404 || detail === 'Bill not found') {
                showToast(tRef.current('errors.billNotFound'));
              } else if (
                detail === 'Bill is closed'
                || detail === 'Action not allowed on this bill state'
              ) {
                leave('/closed');
              } else {
                showToast(tRef.current('common.error'));
              }
            }
            return;
          }

          const billLink = parseBillStartParam(startParam);
          if (billLink) {
            try {
              const seats = await getSeatsByToken(billLink.token, user.id);
              leave(`/bill/${seats.bill_id}${billLink.scan ? '?scan=1' : ''}`);
            } catch (err) {
              console.error('Failed to open bill from start param:', err);
              showToast(tRef.current('errors.billNotFound'));
            }
            return;
          }

          if (startParam && startParam.startsWith('join_')) {
            const token = startParam.slice('join_'.length);
            if (token) {
              try {
                const participant = await joinByToken(token, user.id);
                track(AnalyticsEvent.ParticipantJoined, { via: 'invite', channel: 'link', bill_id: participant.bill_id });
                // First invite-link join only: after the app-level write-access
                // check passes, send the one-time onboarding DM.
                arriveAsGuest(participant.bill_id);
                sendJoinWelcome(participant.bill_id);
                leave(`/bill/${participant.bill_id}`);
              } catch (err) {
                console.error('Failed to join bill from start param:', err);
                const resp = (err as { response?: { status?: number; data?: { detail?: string } } })
                  ?.response;
                const detail = resp?.data?.detail;
                if (detail === 'SEAT_REQUIRED') {
                  // The bill was laid out with a seat per person — the newcomer
                  // has to say which one is theirs before they're in the bill.
                  leave(`/join/${token}`);
                } else if (detail === 'BILL_FULL' || detail === 'Bill is full') {
                  showToast(tRef.current('errors.billFull'));
                } else if (resp?.status === 404 || detail === 'Bill not found') {
                  // The invite points at a bill that was deleted/never existed.
                  showToast(tRef.current('errors.billNotFound'));
                } else if (detail === 'Bill is closed') {
                  // A newcomer tapped an invite to a closed bill — a dedicated
                  // screen explains it instead of a bare error toast (STB-230).
                  leave('/closed');
                } else {
                  showToast(tRef.current('common.error'));
                }
              }
            }
          }
        } finally {
          if (!leftHome) useTour.getState().setArriving(false);
        }
      }).catch((error) => {
        console.error(' Telegram Sync: FAILED', error);
        useTour.getState().setArriving(false);
      });
    };

    void initialize();

    return () => { cancelled = true; };
  }, [setTheme, setCurrentUser, applyServerSettings, router]);

  // A Pro theme is shown until the app learns Pro is not there.
  const { locked: themesLocked } = useProGate('themes');
  const shown = shownTheme(theme, themesLocked);
  useEffect(() => {
    document.documentElement.dataset.theme = shown;
    document.documentElement.classList.toggle('dark', schemeOf(shown) === 'dark');
  }, [shown]);

  // A request that needs Pro opens the paywall over whatever asked, and the
  // status is fetched again — the one the app had was out of date.
  useEffect(() => {
    setPaymentRequiredHandler((detail) => {
      const user = useStore.getState().currentUser;
      if (user) void usePro.getState().load(user.id);
      usePro.getState().openPaywall(paywallReason(detail));
    });
    return () => setPaymentRequiredHandler(null);
  }, []);

  // `<html lang>` and the document title live in the server layout, so the
  // localized values are applied here once the persisted language is known.
  useEffect(() => {
    document.documentElement.lang = language;
    document.title = t('common.appTitle');
    document
      .querySelector('meta[name="description"]')
      ?.setAttribute('content', t('common.appDescription'));
  }, [language, t]);

  return (
    <SafeAreaProvider>
      {!mounted || isTelegram === null ? (
        <div className="min-h-screen bg-background flex items-center justify-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-accent"></div>
        </div>
      ) : (isTelegram === false && !currentUser) ? (
        <ExternalLanding />
      ) : (
        <HomeScreenShortcutProvider>
          {children}
          <TourOverlay />
        </HomeScreenShortcutProvider>
      )}
      {DevMockBanner ? <DevMockBanner /> : null}
      <OfflineGate />
      <Paywall />
      <Toaster />
    </SafeAreaProvider>
  );
}
