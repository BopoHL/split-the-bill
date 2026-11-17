import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, waitFor, fireEvent } from '@testing-library/react';
import type { AssignableUser } from '@/types/api';

vi.mock('@/lib/store/useStore', () => {
  const state = { language: 'en' };
  return {
    useStore: (selector?: (s: typeof state) => unknown) =>
      selector ? selector(state) : state,
  };
});

vi.mock('@/lib/api/bills', () => ({ getAssignableUsers: vi.fn() }));

import { getAssignableUsers } from '@/lib/api/bills';
import AssignUserPicker from './AssignUserPicker';

const mkUser = (over: Partial<AssignableUser> = {}): AssignableUser => ({
  user_id: 7,
  username: 'kolyan',
  name: 'Kolya',
  surname: null,
  avatar_url: null,
  ...over,
});

const setup = (onPick = vi.fn().mockResolvedValue(undefined)) => {
  render(<AssignUserPicker billId={1} isOpen onClose={vi.fn()} onPick={onPick} />);
  return onPick;
};

describe('AssignUserPicker', () => {
  beforeEach(() => {
    vi.mocked(getAssignableUsers).mockResolvedValue([mkUser()]);
  });

  it('lists who the bill can be handed to', async () => {
    setup();

    expect(await screen.findByText('Kolya')).toBeInTheDocument();
    expect(screen.getByText('@kolyan')).toBeInTheDocument();
  });

  it('passes the picked person up', async () => {
    const onPick = setup();

    fireEvent.click(await screen.findByText('Kolya'));

    await waitFor(() => expect(onPick).toHaveBeenCalledWith(mkUser()));
  });

  it('says so when there is nobody to suggest', async () => {
    vi.mocked(getAssignableUsers).mockResolvedValue([]);
    setup();

    expect(await screen.findByText('Nobody to suggest yet')).toBeInTheDocument();
  });

  it('asks for more letters before looking a stranger up', async () => {
    setup();
    await screen.findByText('Kolya');

    fireEvent.change(screen.getByPlaceholderText('Name or @username'), {
      target: { value: 'ko' },
    });

    expect(await screen.findByText('Type at least 3 characters')).toBeInTheDocument();
    // And we never asked the server about two letters.
    expect(vi.mocked(getAssignableUsers).mock.calls.every(([, q]) => q === undefined)).toBe(true);
  });
});

describe('AssignUserPicker — answers out of order', () => {
  beforeEach(() => {
    vi.mocked(getAssignableUsers).mockReset();
    vi.mocked(getAssignableUsers).mockResolvedValue([mkUser()]);
  });

  it('shows only what the latest request found', async () => {
    let answerFirst: (users: AssignableUser[]) => void = () => {};
    vi.mocked(getAssignableUsers).mockImplementation((_bill, q) =>
      q === 'kol'
        ? new Promise<AssignableUser[]>((resolve) => { answerFirst = resolve; })
        : Promise.resolve([mkUser({ user_id: 8, username: 'recent', name: 'Recent' })]),
    );
    setup();
    await screen.findByText('Recent');

    // Typed a name, then thought better of it: the box is empty again and
    // the acquaintances are back before the lookup has answered.
    fireEvent.change(screen.getByPlaceholderText('Name or @username'), { target: { value: 'kol' } });
    await waitFor(() => expect(getAssignableUsers).toHaveBeenLastCalledWith(1, 'kol'));
    fireEvent.change(screen.getByPlaceholderText('Name or @username'), { target: { value: '' } });
    await screen.findByText('Recent');

    await act(async () => {
      answerFirst([mkUser({ user_id: 9, username: 'kolyan', name: 'Kolya' })]);
      await Promise.resolve();
    });

    // A late answer to a question nobody is asking any more is not shown.
    expect(screen.getByText('Recent')).toBeInTheDocument();
    expect(screen.queryByText('Kolya')).toBeNull();
  });

  it('does not count the @ toward the three characters', async () => {
    setup();
    await screen.findByText('Kolya');

    fireEvent.change(screen.getByPlaceholderText('Name or @username'), { target: { value: '@ko' } });

    expect(await screen.findByText('Type at least 3 characters')).toBeInTheDocument();
    expect(vi.mocked(getAssignableUsers).mock.calls.every(([, q]) => q === undefined)).toBe(true);
  });
});

describe('AssignUserPicker — handing the invite over yourself', () => {
  beforeEach(() => {
    vi.mocked(getAssignableUsers).mockResolvedValue([mkUser()]);
  });

  it('offers the personal invite under the list, for whoever is not on it', async () => {
    // The list only holds people the bot can reach. Everyone else used to need
    // a separate button on the seat itself; now it is the last line of this
    // sheet, where you end up once the list turns out not to have them.
    const onSendPersonalInvite = vi.fn().mockResolvedValue(undefined);
    render(
      <AssignUserPicker
        billId={1}
        isOpen
        onClose={vi.fn()}
        onPick={vi.fn()}
        onSendPersonalInvite={onSendPersonalInvite}
      />,
    );

    fireEvent.click(await screen.findByText(/send a personal invite to one person/i));

    await waitFor(() => expect(onSendPersonalInvite).toHaveBeenCalledTimes(1));
  });

  it('keeps the row out when there is nothing to send', async () => {
    setup();
    await screen.findByText('Kolya');

    expect(screen.queryByText(/send a personal invite to one person/i)).toBeNull();
  });
});
