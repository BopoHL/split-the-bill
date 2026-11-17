import { describe, expect, it, vi, beforeEach } from 'vitest';
import { api, Unauthorized } from './api';

describe('admin api client', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  it('sends the session cookie with every request', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ email: 'a@b.c' }), { status: 200 }),
    );

    await api.me();

    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init?.credentials).toBe('include');
  });

  it('turns a 401 into a typed error so the shell can show the login form', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('', { status: 401 }));
    const signedOut = vi.fn();
    window.addEventListener('admin:unauthorized', signedOut);
    await expect(api.stats()).rejects.toBeInstanceOf(Unauthorized);
    window.removeEventListener('admin:unauthorized', signedOut);
    expect(signedOut).toHaveBeenCalledOnce();
  });

  it('requests a sender login code without caching it', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('{"code":null,"received_at":null}', { status: 200 }));

    await api.senderLoginCode(7);

    expect(fetch).toHaveBeenCalledWith('/api/admin/senders/7/login-code', expect.objectContaining({
      method: 'POST', cache: 'no-store', credentials: 'include',
    }));
  });

  it('surfaces other failures as plain errors', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('boom', { status: 500 }));
    await expect(api.stats()).rejects.toThrow('boom');
  });

  it('shows what the API said went wrong rather than its JSON', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: 'OpenAI has no model «gpt-6-sool» for this key' }), { status: 400 }),
    );
    await expect(api.saveSettings({ receipt_model: 'gpt-6-sool' })).rejects.toThrow(
      'OpenAI has no model «gpt-6-sool» for this key',
    );
  });

  it('asks for deleted bills only when told to', async () => {
    // A Response body can only be read once, so each call needs its own.
    vi.mocked(fetch).mockImplementation(async () => new Response('[]', { status: 200 }));

    await api.bills();
    await api.bills(true);

    const urls = vi.mocked(fetch).mock.calls.map(([url]) => String(url));
    expect(urls[0]).toContain('include_deleted=false');
    expect(urls[0]).toContain('limit=50');
    expect(urls[0]).toContain('offset=0');
    expect(urls[1]).toContain('include_deleted=true');
  });

  it('converts table pages into limit and offset', async () => {
    vi.mocked(fetch).mockImplementation(async () => new Response('{"items":[]}', { status: 200 }));

    await api.bills(false, 3, 25);
    await api.users(4, 10);

    const urls = vi.mocked(fetch).mock.calls.map(([url]) => String(url));
    expect(urls[0]).toContain('limit=25');
    expect(urls[0]).toContain('offset=50');
    expect(urls[1]).toContain('/users?limit=10&offset=30');
  });

  it('passes reminder filters through and drops the ones left empty', async () => {
    vi.mocked(fetch).mockImplementation(async () => new Response('{"items":[]}', { status: 200 }));

    await api.reminders();
    await api.reminders({ state: 'muted', only_sent: true, q: '@bob' }, 2, 25);

    const urls = vi.mocked(fetch).mock.calls.map(([url]) => String(url));
    expect(urls[0]).toBe('/api/admin/reminders?limit=50&offset=0');
    expect(urls[1]).toContain('limit=25&offset=25');
    expect(urls[1]).toContain('state=muted');
    expect(urls[1]).toContain('only_sent=true');
    expect(urls[1]).toContain('q=%40bob');
  });

  it('pages broadcast deliveries instead of asking for all of them', async () => {
    vi.mocked(fetch).mockImplementation(async () => new Response('{"items":[]}', { status: 200 }));

    await api.broadcastDeliveries(7, { status: 'failed' }, 2, 10);

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toBe('/api/admin/broadcasts/7/deliveries?limit=10&offset=10&status=failed');
  });

  it('lets an upload set its own multipart boundary', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('{}', { status: 200 }));

    await api.attachBroadcastPhoto(7, new File(['x'], 'cover.png', { type: 'image/png' }));

    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toContain('/broadcasts/7/photo');
    // A JSON content type here would leave the body unparseable on the server.
    expect((init?.headers as Record<string, string>)['Content-Type']).toBeUndefined();
  });

  it('sends only the scan filters that are set', async () => {
    vi.mocked(fetch).mockImplementation(async () => new Response('[]', { status: 200 }));

    await api.scans({ status: 'failed', source: '' });
    await api.scans();

    const urls = vi.mocked(fetch).mock.calls.map(([url]) => String(url));
    expect(urls[0]).toContain('/scans?status=failed');
    expect(urls[0]).not.toContain('source=');
    expect(urls[1]).toMatch(/\/scans$/);
  });

  it('saves the scan mode and asks for the comparison separately', async () => {
    vi.mocked(fetch).mockImplementation(async () => new Response('{}', { status: 200 }));

    await api.saveSettings({ scan_mode: 'hybrid' });
    await api.scanModes();

    const [settingsUrl, settingsInit] = vi.mocked(fetch).mock.calls[0];
    expect(String(settingsUrl)).toBe('/api/admin/settings');
    expect(settingsInit?.method).toBe('PUT');
    expect(String(settingsInit?.body)).toContain('hybrid');
    expect(String(vi.mocked(fetch).mock.calls[1][0])).toBe('/api/admin/scans/modes');
  });

  it('narrows the scan list to one reader', async () => {
    vi.mocked(fetch).mockImplementation(async () => new Response('[]', { status: 200 }));

    await api.scans({ mode: 'vision' });

    expect(String(vi.mocked(fetch).mock.calls[0][0])).toContain('mode=vision');
  });
});
