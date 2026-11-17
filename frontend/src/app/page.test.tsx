import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BillStatus } from '@/types/api';
import { listedBillFixture } from '@/test/billFixtures';

const getUserBills = vi.hoisted(() => vi.fn());
const getBillCounts = vi.hoisted(() => vi.fn());
const updatePaymentStatus = vi.hoisted(() => vi.fn());
const sendReminders = vi.hoisted(() => vi.fn());
const deleteBill = vi.hoisted(() => vi.fn());
const createBill = vi.hoisted(() => vi.fn());
const track = vi.hoisted(() => vi.fn());
const storeState = vi.hoisted(() => ({
  currentUser: {
    id: 1,
    username: 'tester',
    avatar_url: null,
    settings: { onboarding_completed: true },
  },
  setCurrentUser: vi.fn(),
  completeOnboarding: vi.fn().mockResolvedValue(true),
  language: 'ru',
  currency: 'uzs',
}));

vi.mock('@/lib/store/useStore', () => {
  const useStore = Object.assign(
    (selector?: (state: typeof storeState) => unknown) =>
      selector ? selector(storeState) : storeState,
    { getState: () => storeState },
  );

  return { useStore };
});

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/lib/api/bills', () => ({
  createBill,
  addBillItem: vi.fn(),
  getUserBills,
  getBillCounts,
  updatePaymentStatus,
  deleteBill,
}));

vi.mock('@/lib/api/receipts', () => ({
  receiptsApi: { attachToBill: vi.fn() },
}));

vi.mock('@/lib/api/users', () => ({
  updateUserSettings: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('@/lib/toast', () => ({ showToast: vi.fn() }));
vi.mock('@/lib/analytics', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/analytics')>()),
  track,
}));
vi.mock('@/lib/api/reminders', () => ({
  getOwed: vi.fn(() => Promise.resolve({ totals: [], people: 0, bills: 0, remindable: 0 })),
  remindEveryoneWhoOwes: vi.fn(),
  sendReminders,
}));
vi.mock('@/lib/utils/image', () => ({ compressImage: vi.fn() }));

vi.mock('@/components/bill/create/CreateBillWizard', () => ({
  default: ({
    isOpen,
    existingBills,
    onSubmit,
  }: {
    isOpen: boolean;
    existingBills: Array<{ title: string }>;
    onSubmit: (data: { title: string; total_sum: number }) => Promise<void>;
  }) =>
    isOpen ? (
      <div
        role="dialog"
        data-existing-bills={existingBills.map((bill) => bill.title).join('|')}
      >
        create-bill-modal
        <button type="button" onClick={() => void onSubmit({ title: 'Обед', total_sum: 0 })}>submit-bill</button>
      </div>
    ) : null,
}));

vi.mock('@/components/ui/FloatingCreateButton', () => ({
  default: ({ onClick }: { onClick: () => void }) => (
    <button type="button" aria-label="fab-create" onClick={onClick} />
  ),
}));

vi.mock('@/components/ui/SettingsMenu', () => ({ default: () => null }));
vi.mock('@/components/profile/ProfileChip', () => ({ default: () => null }));
vi.mock('@/components/pro/ProButton', () => ({ default: () => null }));
vi.mock('@/components/ui/HomeScreenBanner', () => ({ default: () => null }));
vi.mock('@/components/onboarding/LanguageStep', () => ({
  default: ({ onContinue }: { onContinue: () => void }) => (
    <button type="button" data-testid="language-step" onClick={onContinue}>language</button>
  ),
}));

import { useTour } from '@/lib/tour/useTour';
import { useInvitePrompt } from '@/lib/store/useInvitePrompt';
import HomePage from './page';

const ME = 1;
const mine = listedBillFixture({
  id: 7, title: 'Ужин', owner_id: ME, total_sum: 296000, payers_count: 3, payers_paid: 1, expected_people: 4,
  collection: { left: 168000, remindable: 2, reminded_at: null, next_reminder_at: null },
});
const owing = listedBillFixture({
  id: 8, title: 'Такси', owner_id: 2, owner: { name: 'Alice', avatar_url: null },
  payment_details: '8600 1234 5678 9012', my_seat: { id: 81, amount: 42500, is_paid: false },
});
const settled = listedBillFixture({
  id: 9, title: 'Пицца', owner_id: 3, owner: { name: 'Bob', avatar_url: null },
  my_seat: { id: 91, amount: 38000, is_paid: true },
});
const closed = listedBillFixture({
  id: 42, title: 'Старый счёт', owner_id: ME, status: BillStatus.CLOSED, created_at: '2026-09-14T12:00:00',
});

describe('HomePage bill sections', () => {
  beforeEach(() => {
    getUserBills.mockReset();
    getUserBills.mockImplementation((_userId: number, _page: number, _limit: number, status: string) =>
      Promise.resolve(status === 'active' ? [mine, owing, settled] : [closed]),
    );
    getBillCounts.mockReset();
    getBillCounts.mockResolvedValue({ all: 1, owned: 1, joined: 0 });
    updatePaymentStatus.mockReset();
    updatePaymentStatus.mockResolvedValue({});
    sendReminders.mockReset();
    sendReminders.mockResolvedValue({ queued: 2, skipped: [] });
    deleteBill.mockReset();
    deleteBill.mockResolvedValue(undefined);
  });

  const panelOf = (tab: HTMLElement) => document.getElementById(tab.getAttribute('aria-controls')!);

  it('sorts open bills into what to collect, what to pay and what is paid', async () => {
    render(<HomePage />);

    const activeTab = await screen.findByRole('tab', { name: /Активные\s+03/ });
    const archiveTab = screen.getByRole('tab', { name: /Архив\s+01/ });
    const activePanel = panelOf(activeTab)!;

    expect(activeTab).toHaveAttribute('aria-selected', 'true');
    expect(panelOf(archiveTab)).toHaveAttribute('aria-hidden', 'true');
    expect(within(activePanel).getByRole('heading', { name: 'Собираю' }).closest('section')).toHaveTextContent('Ужин');
    expect(within(activePanel).getByRole('heading', { name: 'Вы должны' }).closest('section')).toHaveTextContent('Такси');
    expect(within(activePanel).getByRole('heading', { name: 'Оплачено · ждём закрытия' }).closest('section')).toHaveTextContent('Пицца');
    expect(activePanel).not.toHaveTextContent('Старый счёт');
  });

  it('rings the bell of a bill: everyone on it who owes gets a reminder', async () => {
    render(<HomePage />);

    await userEvent.click(await screen.findByRole('button', { name: 'Напомнить тем, кто не оплатил' }));

    expect(sendReminders).toHaveBeenCalledWith(7);
    await waitFor(() => expect(getUserBills).toHaveBeenCalledTimes(3));
  });

  it('marks my share paid from the list and lets me take it back', async () => {
    render(<HomePage />);

    await userEvent.click(await screen.findByRole('button', { name: 'Я оплатил(а)' }));
    expect(updatePaymentStatus).toHaveBeenCalledWith(8, 81, true, ME);
    expect(await screen.findByRole('status')).toHaveTextContent('Оплата отмечена');

    await userEvent.click(screen.getByRole('button', { name: 'Отменить' }));
    expect(updatePaymentStatus).toHaveBeenLastCalledWith(8, 81, false, ME);
    expect(await screen.findByRole('button', { name: 'Я оплатил(а)' })).toBeInTheDocument();
  });

  it('switches to the archive, gathered by month', async () => {
    render(<HomePage />);

    const archiveTab = await screen.findByRole('tab', { name: /Архив/ });
    await userEvent.click(archiveTab);

    const archivePanel = panelOf(archiveTab)!;
    expect(archiveTab).toHaveAttribute('aria-selected', 'true');
    expect(archivePanel).not.toHaveAttribute('aria-hidden');
    expect(within(archivePanel).getByRole('heading', { name: 'Сентябрь' })).toBeInTheDocument();
    expect(archivePanel).toHaveTextContent('Старый счёт');
    expect(archivePanel).toHaveTextContent('2 участника · ваш счёт');
  });

  it('deletes my bill from its bin after asking in the row', async () => {
    render(<HomePage />);

    const row = (await screen.findByText('Ужин')).closest('a')!.parentElement!;
    await userEvent.click(within(row).getByRole('button', { name: 'Удалить счёт' }));
    await userEvent.click(screen.getByRole('button', { name: 'Удалить' }));

    expect(deleteBill).toHaveBeenCalledWith(7, ME);
    await waitFor(() => expect(screen.queryByText('Ужин')).not.toBeInTheDocument());
  });

  it('searches the archive on the server and splits it by role', async () => {
    render(<HomePage />);

    await userEvent.click(await screen.findByRole('tab', { name: /Архив/ }));
    await userEvent.type(screen.getByRole('searchbox', { name: 'Поиск по архиву' }), 'taxi');
    await waitFor(() =>
      expect(getUserBills).toHaveBeenCalledWith(ME, 0, 15, 'closed', { query: 'taxi', role: undefined }),
    );
    expect(getBillCounts).toHaveBeenCalledWith(ME, 'closed', 'taxi');

    await userEvent.click(screen.getByRole('button', { name: /Участвовал/ }));
    await waitFor(() =>
      expect(getUserBills).toHaveBeenCalledWith(ME, 0, 15, 'closed', { query: 'taxi', role: 'participant' }),
    );
  });

  it('pages between active bills and the archive with a horizontal swipe', async () => {
    render(<HomePage />);

    const row = await screen.findByText('Ужин');
    const touch = (x: number, y: number) => ({ identifier: 1, clientX: x, clientY: y });
    const swipe = (target: Element, from: number, to: number) => {
      fireEvent.touchStart(target, { touches: [touch(from, 80)], changedTouches: [touch(from, 80)] });
      fireEvent.touchMove(target, { touches: [touch((from + to) / 2, 82)], changedTouches: [touch((from + to) / 2, 82)] });
      fireEvent.touchMove(target, { touches: [touch(to, 84)], changedTouches: [touch(to, 84)] });
      fireEvent.touchEnd(target, { touches: [], changedTouches: [touch(to, 84)] });
    };

    swipe(row, 220, 100);
    expect(screen.getByRole('tab', { selected: true })).toHaveAccessibleName(/Архив/);

    swipe(screen.getByText('Старый счёт'), 100, 220);
    expect(screen.getByRole('tab', { selected: true })).toHaveAccessibleName(/Активные/);
  });

  it('moves selection and focus with tab-list keyboard controls', async () => {
    const user = userEvent.setup();
    render(<HomePage />);

    const activeTab = await screen.findByRole('tab', { name: /Активные/ });
    const archiveTab = screen.getByRole('tab', { name: /Архив/ });

    activeTab.focus();
    await user.keyboard('{ArrowRight}');
    expect(archiveTab).toHaveFocus();
    expect(archiveTab).toHaveAttribute('aria-selected', 'true');

    await user.keyboard('{Home}');
    expect(activeTab).toHaveFocus();
    expect(activeTab).toHaveAttribute('aria-selected', 'true');
  });

  it('keeps the archive selectable when empty and offers both create entry points', async () => {
    getUserBills.mockResolvedValue([]);
    getBillCounts.mockResolvedValue({ all: 0, owned: 0, joined: 0 });

    render(<HomePage />);

    const archiveTab = await screen.findByRole('tab', { name: /Архив\s+00/ });
    expect(archiveTab).toBeEnabled();
    expect(screen.getByText('Активных счетов пока нет.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'fab-create' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Создать новый счет' })).toBeInTheDocument();

    await userEvent.click(archiveTab);
    expect(screen.getByText('Закрытых счетов пока нет.')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'fab-create' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('create-bill-modal');
  });

  it('passes active and recent closed bills to the create wizard', async () => {
    render(<HomePage />);

    await screen.findByText('Ужин');
    await waitFor(() => expect(getBillCounts).toHaveBeenCalled());
    await userEvent.click(screen.getByRole('button', { name: 'fab-create' }));

    expect(screen.getByRole('dialog')).toHaveAttribute('data-existing-bills', 'Ужин|Такси|Пицца|Старый счёт');
  });
});

describe('HomePage first run', () => {
  const regular = storeState.currentUser;
  const signedInWith = (settings: Record<string, boolean>) =>
    Object.assign(storeState, { currentUser: { ...regular, settings } });

  beforeEach(() => {
    getUserBills.mockResolvedValue([]);
    getBillCounts.mockResolvedValue({ all: 0, owned: 0, joined: 0 });
    storeState.completeOnboarding.mockClear();
  });

  afterEach(() => {
    Object.assign(storeState, { currentUser: regular });
    useTour.setState({ active: false, stepIndex: 0, arriving: false });
  });

  it('asks a newcomer for a language before anything else', async () => {
    signedInWith({});

    render(<HomePage />);

    expect(await screen.findByTestId('language-step')).toBeInTheDocument();
    expect(useTour.getState().active).toBe(false);
  });

  it('lands a newcomer on home once the language is chosen, with the tour offered rather than started', async () => {
    signedInWith({});
    render(<HomePage />);

    await userEvent.click(await screen.findByTestId('language-step'));

    expect(storeState.completeOnboarding).toHaveBeenCalled();
    expect(useTour.getState().active).toBe(false);
  });

  it('counts onboarding as completed once the server has kept it', async () => {
    signedInWith({});
    track.mockClear();
    render(<HomePage />);

    await userEvent.click(await screen.findByTestId('language-step'));

    await waitFor(() => expect(track).toHaveBeenCalledWith('onboarding_completed', { language: 'ru' }));
  });

  it('does not count onboarding the server did not keep', async () => {
    signedInWith({});
    track.mockClear();
    storeState.completeOnboarding.mockResolvedValueOnce(false);
    render(<HomePage />);

    await userEvent.click(await screen.findByTestId('language-step'));

    await waitFor(() => expect(storeState.completeOnboarding).toHaveBeenCalled());
    expect(track).not.toHaveBeenCalledWith('onboarding_completed', expect.anything());
  });

  it('lets someone who came as a guest straight in: their language came with them', async () => {
    signedInWith({ guest_tour_completed: true });

    render(<HomePage />);

    await waitFor(() => expect(storeState.completeOnboarding).toHaveBeenCalled());
    expect(useTour.getState().active).toBe(false);
    expect(screen.queryByTestId('language-step')).toBeNull();
  });

  it('starts the tour from the empty home screen when asked', async () => {
    signedInWith({ onboarding_completed: true });
    render(<HomePage />);

    await userEvent.click(await screen.findByRole('button', { name: 'Как это работает' }));

    expect(useTour.getState().active).toBe(true);
    expect(useTour.getState().tour.name).toBe('host');
  });

  it('keeps its welcome back while an invite is on its way to the bill', () => {
    signedInWith({});
    useTour.setState({ arriving: true });

    render(<HomePage />);

    expect(screen.queryByTestId('language-step')).toBeNull();
  });
});

describe('HomePage — inviting the table to a bill just made', () => {
  beforeEach(() => {
    getUserBills.mockResolvedValue([]);
    getBillCounts.mockResolvedValue({ all: 0, owned: 0, joined: 0 });
    createBill.mockReset();
    createBill.mockResolvedValue({ id: 55 });
    useInvitePrompt.setState({ billId: null });
  });

  afterEach(() => useTour.setState({ active: false, stepIndex: 0, arriving: false }));

  const createByHand = async () => {
    render(<HomePage />);
    await userEvent.click(await screen.findByRole('button', { name: 'fab-create' }));
    await userEvent.click(screen.getByRole('button', { name: 'submit-bill' }));
    await waitFor(() => expect(createBill).toHaveBeenCalled());
  };

  it('offers to invite the table to a bill made by hand', async () => {
    await createByHand();

    await waitFor(() => expect(useInvitePrompt.getState().billId).toBe(55));
  });

  it('offers nothing during the tour, which shows the invite its own way', async () => {
    useTour.setState({ active: true });

    await createByHand();

    await waitFor(() => expect(track).toHaveBeenCalledWith('bill_created', { source: 'manual', bill_id: 55 }));
    expect(useInvitePrompt.getState().billId).toBeNull();
  });
});
