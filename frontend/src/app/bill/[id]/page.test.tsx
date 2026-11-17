import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import type { BillDetail } from '@/types/api';
import { billFixture } from '@/test/billFixtures';

const state = vi.hoisted(() => ({
  currentUser: { id: 10, telegram_id: 100, username: 'alice', name: 'Alice', surname: null, avatar_url: null },
  setCurrentBill: vi.fn(),
  router: { push: vi.fn(), replace: vi.fn() },
  params: { id: '1' },
  refresh: undefined as undefined | (() => Promise<void>),
}));
vi.mock('next/navigation', () => ({ useParams: () => state.params, useRouter: () => state.router }));
vi.mock('next/dynamic', () => ({ default: () => () => null }));
vi.mock('@/lib/store/useStore', () => ({ useStore: () => state }));
vi.mock('@/lib/api/bills', () => ({ getBill: vi.fn() }));
vi.mock('@/lib/i18n/useTranslation', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/lib/telegram/init', () => ({ showBackButton: () => () => {} }));
vi.mock('@/hooks/useBillAutoRefresh', () => ({ useBillAutoRefresh: () => {} }));
vi.mock('@/hooks/useBillEvents', () => ({ useBillEvents: (_id: number, refresh: () => Promise<void>) => { state.refresh = refresh; } }));
vi.mock('@/components/layout/AppHeader', () => ({ default: ({ children }: { children: ReactNode }) => <header>{children}</header> }));
vi.mock('@/components/bill/BillDetailsCreator', () => ({ default: ({ bill, setBill }: { bill: BillDetail; setBill: (bill: BillDetail) => void }) => <><p>{bill.title}</p><button onClick={() => setBill({ ...bill, title: 'Mutation result' })}>Assign</button></> }));
vi.mock('@/components/bill/BillDetailsParticipant', () => ({ default: () => null }));
vi.mock('@/components/bill/BillTitleEditor', () => ({ default: () => null }));
vi.mock('@/components/ui/SettingsMenu', () => ({ default: () => null }));
vi.mock('@/components/profile/ProfileChip', () => ({ default: () => null }));
vi.mock('@/components/pro/ProButton', () => ({ default: () => null }));
vi.mock('@/components/bill/invite/ShareBillButton', () => ({ default: () => null }));
vi.mock('@/lib/toast', () => ({ showToast: vi.fn() }));

import { getBill } from '@/lib/api/bills';
import { useTour } from '@/lib/tour/useTour';
import BillPage from './page';

const deferred = () => {
  let resolve!: (bill: BillDetail) => void;
  const promise = new Promise<BillDetail>((done) => { resolve = done; });
  return { promise, resolve };
};
beforeEach(() => { vi.mocked(getBill).mockReset(); state.params = { id: '1' }; });

describe('bill snapshot ordering', () => {
  it('does not overwrite a mutation response with an older pending refresh', async () => {
    const pending = deferred();
    vi.mocked(getBill).mockResolvedValueOnce(billFixture({ title: 'Initial' })).mockReturnValueOnce(pending.promise);
    render(<BillPage />);
    expect(await screen.findByText('Initial')).toBeInTheDocument();
    act(() => { void state.refresh?.(); });
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }));
    await act(async () => pending.resolve(billFixture({ title: 'Stale refresh' })));
    expect(screen.getByText('Mutation result')).toBeInTheDocument();
    expect(screen.queryByText('Stale refresh')).not.toBeInTheDocument();
  });

  it('keeps the newest refresh when two GETs finish out of order', async () => {
    const older = deferred();
    const newer = deferred();
    vi.mocked(getBill).mockResolvedValueOnce(billFixture()).mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);
    render(<BillPage />);
    await screen.findByText('Dinner');
    act(() => { void state.refresh?.(); void state.refresh?.(); });
    await act(async () => newer.resolve(billFixture({ title: 'Newest' })));
    await act(async () => older.resolve(billFixture({ title: 'Older' })));
    expect(screen.getByText('Newest')).toBeInTheDocument();
    expect(screen.queryByText('Older')).not.toBeInTheDocument();
  });

  it('discards a pending response after navigating to another bill', async () => {
    const older = deferred();
    vi.mocked(getBill).mockReturnValueOnce(older.promise).mockResolvedValueOnce(billFixture({ id: 2, title: 'Other bill' }));
    const view = render(<BillPage />);
    state.params = { id: '2' };
    view.rerender(<BillPage />);
    await waitFor(() => expect(screen.getByText('Other bill')).toBeInTheDocument());
    await act(async () => older.resolve(billFixture({ title: 'Wrong bill' })));
    expect(screen.queryByText('Wrong bill')).not.toBeInTheDocument();
  });
});

describe('losing the bill while it is open', () => {
  it('shows why when a refresh is refused, instead of the old amounts', async () => {
    vi.mocked(getBill)
      .mockResolvedValueOnce(billFixture({ title: 'Initial' }))
      .mockRejectedValueOnce({ response: { status: 403 } });
    render(<BillPage />);
    expect(await screen.findByText('Initial')).toBeInTheDocument();

    await act(async () => { await state.refresh?.(); });

    expect(screen.getByText('errors.forbiddenTitle')).toBeInTheDocument();
    expect(screen.queryByText('Initial')).not.toBeInTheDocument();
  });

  it('keeps the bill on screen through a refresh that merely failed', async () => {
    vi.mocked(getBill)
      .mockResolvedValueOnce(billFixture({ title: 'Initial' }))
      .mockRejectedValueOnce(new Error('Network Error'));
    render(<BillPage />);
    expect(await screen.findByText('Initial')).toBeInTheDocument();

    await act(async () => { await state.refresh?.(); });

    expect(screen.getByText('Initial')).toBeInTheDocument();
  });
});

describe('the guided tour’s bill', () => {
  it('sends a stray demo bill home instead of showing it', async () => {
    vi.mocked(getBill).mockResolvedValueOnce(billFixture({ title: 'Demo', is_demo: true }));
    render(<BillPage />);

    await waitFor(() => expect(state.router.replace).toHaveBeenCalledWith('/'));
    expect(screen.queryByText('Demo')).not.toBeInTheDocument();
  });

  it('shows the demo bill while the tour walks through it', async () => {
    useTour.setState({ active: true });
    vi.mocked(getBill).mockResolvedValueOnce(billFixture({ title: 'Demo', is_demo: true }));
    render(<BillPage />);

    expect(await screen.findByText('Demo')).toBeInTheDocument();
    useTour.getState().stop();
  });
});
