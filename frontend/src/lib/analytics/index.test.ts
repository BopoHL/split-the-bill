import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const mocks = vi.hoisted(() => ({
  init: vi.fn(),
  capture: vi.fn(),
  identify: vi.fn(),
  reset: vi.fn(),
  setPersonProperties: vi.fn(),
  register: vi.fn(),
}));

vi.mock('posthog-js', () => ({
  default: {
    init: mocks.init,
    capture: mocks.capture,
    identify: mocks.identify,
    reset: mocks.reset,
    setPersonProperties: mocks.setPersonProperties,
    register: mocks.register,
  },
}));

describe('analytics wrapper', () => {
  beforeEach(() => {
    vi.resetModules();
    Object.values(mocks).forEach((m) => m.mockClear());
  });
  afterEach(() => vi.unstubAllEnvs());

  it('is a no-op before init (no key configured)', async () => {
    const a = await import('./index');
    expect(() => a.track(a.AnalyticsEvent.AppOpen, { start: 'none' })).not.toThrow();
    expect(mocks.capture).not.toHaveBeenCalled();
    a.identifyUser(1, { language: 'en', currency: 'usd' });
    expect(mocks.identify).not.toHaveBeenCalled();
  });

  it('does not init PostHog when the key is absent', async () => {
    const a = await import('./index');
    a.initAnalytics();
    expect(mocks.init).not.toHaveBeenCalled();
  });

  it('captures typed events once initialised with a key', async () => {
    vi.stubEnv('NEXT_PUBLIC_POSTHOG_KEY', 'phc_test');
    const a = await import('./index');
    a.initAnalytics();
    a.track(a.AnalyticsEvent.BillCreated, { source: 'manual', bill_id: 1 });
    expect(mocks.init).toHaveBeenCalledOnce();
    expect(mocks.register).toHaveBeenCalledWith({ surface: 'mini_app' });
    expect(mocks.capture).toHaveBeenCalledWith('bill_created', { source: 'manual', bill_id: 1 });
    expect(mocks.init).toHaveBeenCalledWith(
      'phc_test',
      expect.objectContaining({
        api_host: 'https://eu.i.posthog.com',
        autocapture: false,
        disable_session_recording: true,
        session_recording: expect.objectContaining({ maskAllInputs: true, maskTextSelector: '*' }),
      }),
    );
  });

  it('enables replay only when explicitly opted in', async () => {
    vi.stubEnv('NEXT_PUBLIC_POSTHOG_KEY', 'phc_test');
    vi.stubEnv('NEXT_PUBLIC_POSTHOG_DISABLE_REPLAY', '0');
    const a = await import('./index');
    a.initAnalytics();
    expect(mocks.init).toHaveBeenCalledWith(
      'phc_test',
      expect.objectContaining({ disable_session_recording: false }),
    );
  });

  it('drops the Telegram login from the address before PostHog can report it', async () => {
    vi.stubEnv('NEXT_PUBLIC_POSTHOG_KEY', 'phc_test');
    window.history.replaceState(null, '', '/bill/7?x=1#tgWebAppData=user%3D1%26hash%3Dabc');
    const seenByPostHog: string[] = [];
    mocks.init.mockImplementationOnce(() => seenByPostHog.push(window.location.href));
    const a = await import('./index');
    a.initAnalytics();
    expect(seenByPostHog).toEqual([`${window.location.origin}/bill/7?x=1`]);
  });

  it('keeps the keys of a join link out of what PostHog is sent', async () => {
    vi.stubEnv('NEXT_PUBLIC_POSTHOG_KEY', 'phc_test');
    const a = await import('./index');
    a.initAnalytics();
    const { before_send: beforeSend } = mocks.init.mock.calls[0][1];
    const url = 'https://split.uz/join/AbC123?inv=SECRET&seat=4';

    const sent = beforeSend({
      event: '$pageview',
      properties: { $current_url: url, $pathname: '/join/AbC123', bill_id: 7 },
      $set: { $current_url: url },
      $set_once: { $initial_current_url: url },
    });

    expect(sent.properties).toEqual({
      $current_url: 'https://split.uz/join/:token?inv=:code&seat=4', $pathname: '/join/:token', bill_id: 7,
    });
    expect(JSON.stringify(sent)).not.toMatch(/AbC123|SECRET/);
  });

  it('identifies with a stringified distinct id', async () => {
    vi.stubEnv('NEXT_PUBLIC_POSTHOG_KEY', 'phc_test');
    const a = await import('./index');
    a.initAnalytics();
    a.identifyUser(123, { language: 'ru', currency: 'uzs' });
    expect(mocks.identify).toHaveBeenCalledWith('123', { language: 'ru', currency: 'uzs' });
  });

  it('adds the context to every event while it holds', async () => {
    vi.stubEnv('NEXT_PUBLIC_POSTHOG_KEY', 'phc_test');
    const a = await import('./index');
    a.initAnalytics();
    a.setAnalyticsContext({ in_tour: 'host' });
    a.track(a.AnalyticsEvent.BillCreated, { source: 'manual', bill_id: 1 });
    a.setAnalyticsContext({});
    a.track(a.AnalyticsEvent.BillCreated, { source: 'qr', bill_id: 2 });
    expect(mocks.capture).toHaveBeenNthCalledWith(1, 'bill_created', { in_tour: 'host', source: 'manual', bill_id: 1 });
    expect(mocks.capture).toHaveBeenNthCalledWith(2, 'bill_created', { source: 'qr', bill_id: 2 });
  });

  it('sets person properties only once initialised', async () => {
    const a = await import('./index');
    const pro = { pro: true, pro_trial: false, pro_subscription: true };
    a.setPersonProperties(pro);
    expect(mocks.setPersonProperties).not.toHaveBeenCalled();
    vi.stubEnv('NEXT_PUBLIC_POSTHOG_KEY', 'phc_test');
    a.initAnalytics();
    a.setPersonProperties(pro);
    expect(mocks.setPersonProperties).toHaveBeenCalledWith(pro);
  });
});
