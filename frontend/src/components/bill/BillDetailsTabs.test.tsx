import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BillDetailsTabs, { type BillTab } from './BillDetailsTabs';

vi.mock('@/lib/i18n/useTranslation', () => ({
  useTranslation: () => ({
    t: (key: string) =>
      ({
        'bill.detailsTabs': 'Bill details',
        'bill.participants': 'Participants',
        'bill.receipt': 'Receipt',
      })[key] ?? key,
  }),
}));

function ControlledTabs({
  participants = <div>Participant content</div>,
  receipt = <div>Receipt content</div>,
}: {
  participants?: React.ReactNode;
  receipt?: React.ReactNode;
}) {
  const [value, setValue] = useState<BillTab>('participants');
  return (
    <BillDetailsTabs
      value={value}
      onChange={setValue}
      participants={participants}
      receipt={receipt}
    />
  );
}

type Point = { x: number; y: number };

const touchAt = ({ x, y }: Point, identifier = 1) => ({ identifier, clientX: x, clientY: y });

function swipe(target: Element, start: Point, end: Point) {
  const first = touchAt(start);
  const middle = touchAt({ x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 });
  const last = touchAt(end);
  fireEvent.touchStart(target, { touches: [first], changedTouches: [first] });
  fireEvent.touchMove(target, { touches: [middle], changedTouches: [middle] });
  fireEvent.touchMove(target, { touches: [last], changedTouches: [last] });
  fireEvent.touchEnd(target, { touches: [], changedTouches: [last] });
}

const selectedTab = () => screen.getByRole('tab', { selected: true });

afterEach(() => {
  vi.restoreAllMocks();
});

describe('BillDetailsTabs segmented control', () => {
  it('draws the tabs as one segmented control with a touch-safe height', () => {
    render(<ControlledTabs />);
    const participants = screen.getByRole('tab', { name: 'Participants' });

    expect(participants).toHaveClass('min-h-10', 'text-[13px]');
    expect(participants.parentElement).toHaveAttribute('role', 'tablist');
    expect(screen.getByRole('tablist').style.getPropertyValue('--tab-index')).toBe('0');
    expect(screen.getByTestId('tabs-indicator')).toHaveTextContent('ParticipantsReceipt');
  });

  it('moves the indicator with the selection', async () => {
    render(<ControlledTabs />);

    await userEvent.click(screen.getByRole('tab', { name: 'Receipt' }));

    expect(selectedTab()).toHaveAccessibleName('Receipt');
    expect(screen.getByRole('tablist').style.getPropertyValue('--tab-index')).toBe('1');
  });

  it('updates controlled state and focus with arrow, Home, and End keys', () => {
    render(<ControlledTabs />);
    const participants = screen.getByRole('tab', { name: 'Participants' });
    const receipt = screen.getByRole('tab', { name: 'Receipt' });

    participants.focus();
    fireEvent.keyDown(participants, { key: 'ArrowRight' });
    expect(receipt).toHaveAttribute('aria-selected', 'true');
    expect(receipt).toHaveFocus();

    fireEvent.keyDown(receipt, { key: 'ArrowLeft' });
    expect(participants).toHaveAttribute('aria-selected', 'true');
    expect(participants).toHaveFocus();

    fireEvent.keyDown(participants, { key: 'End' });
    expect(receipt).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(receipt, { key: 'Home' });
    expect(participants).toHaveAttribute('aria-selected', 'true');
  });
});

describe('BillDetailsTabs swiping', () => {
  it('lets the vertical scroll through and keeps horizontal drags for itself', () => {
    render(<ControlledTabs />);
    const target = screen.getByText('Participant content');
    const start = touchAt({ x: 200, y: 100 });

    fireEvent.touchStart(target, { touches: [start], changedTouches: [start] });
    const down = touchAt({ x: 204, y: 140 });
    expect(fireEvent.touchMove(target, { touches: [down], changedTouches: [down] })).toBe(true);
    fireEvent.touchEnd(target, { touches: [], changedTouches: [down] });

    fireEvent.touchStart(target, { touches: [start], changedTouches: [start] });
    const aside = touchAt({ x: 160, y: 106 });
    expect(fireEvent.touchMove(target, { touches: [aside], changedTouches: [aside] })).toBe(false);
  });

  it('pages between the panels with a horizontal swipe in either direction', () => {
    render(<ControlledTabs />);

    swipe(screen.getByText('Participant content'), { x: 220, y: 80 }, { x: 100, y: 88 });
    expect(selectedTab()).toHaveAccessibleName('Receipt');

    swipe(screen.getByText('Receipt content'), { x: 100, y: 80 }, { x: 220, y: 84 });
    expect(selectedTab()).toHaveAccessibleName('Participants');
  });

  it('leaves a swipe from the screen\'s left edge to going back', () => {
    render(<ControlledTabs />);

    swipe(screen.getByText('Participant content'), { x: 220, y: 80 }, { x: 100, y: 84 });
    expect(selectedTab()).toHaveAccessibleName('Receipt');

    swipe(screen.getByText('Receipt content'), { x: 10, y: 80 }, { x: 220, y: 84 });
    expect(selectedTab()).toHaveAccessibleName('Receipt');
  });

  it('stays put when swiped past the first or the last panel', () => {
    render(<ControlledTabs />);

    swipe(screen.getByText('Participant content'), { x: 100, y: 80 }, { x: 260, y: 80 });
    expect(selectedTab()).toHaveAccessibleName('Participants');
  });

  it('starts a swipe on a button without also pressing it', () => {
    const onPress = vi.fn();
    render(
      <ControlledTabs
        participants={<button type="button" onClick={onPress}>Row</button>}
      />,
    );
    const row = screen.getByRole('button', { name: 'Row' });

    swipe(row, { x: 220, y: 40 }, { x: 100, y: 44 });
    fireEvent.click(row);

    expect(selectedTab()).toHaveAccessibleName('Receipt');
    expect(onPress).not.toHaveBeenCalled();
  });

  it('lets a later deliberate press through after a swipe', () => {
    const onPress = vi.fn();
    const now = vi.spyOn(performance, 'now').mockReturnValue(1000);
    render(<ControlledTabs participants={<button type="button" onClick={onPress}>Row</button>} />);

    swipe(screen.getByRole('button', { name: 'Row' }), { x: 220, y: 40 }, { x: 100, y: 44 });
    fireEvent.click(screen.getByRole('tab', { name: 'Participants' }));
    now.mockReturnValue(2000);
    fireEvent.click(screen.getByRole('button', { name: 'Row' }));

    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it('calls the swipe off when a second finger lands', () => {
    render(<ControlledTabs />);
    const target = screen.getByText('Participant content');
    const first = touchAt({ x: 220, y: 80 });
    const moved = touchAt({ x: 150, y: 80 });
    const second = touchAt({ x: 40, y: 90 }, 2);

    fireEvent.touchStart(target, { touches: [first], changedTouches: [first] });
    fireEvent.touchMove(target, { touches: [moved], changedTouches: [moved] });
    fireEvent.touchStart(target, { touches: [moved, second], changedTouches: [second] });
    const further = touchAt({ x: 60, y: 80 });
    fireEvent.touchMove(target, { touches: [further, second], changedTouches: [further] });
    fireEvent.touchEnd(target, { touches: [second], changedTouches: [further] });
    fireEvent.touchEnd(target, { touches: [], changedTouches: [second] });
    expect(selectedTab()).toHaveAccessibleName('Participants');

    swipe(target, { x: 220, y: 80 }, { x: 100, y: 80 });
    expect(selectedTab()).toHaveAccessibleName('Receipt');
  });

  it('snaps back when the browser takes the gesture over', () => {
    render(<ControlledTabs />);
    const target = screen.getByText('Participant content');
    const first = touchAt({ x: 220, y: 80 });
    const moved = touchAt({ x: 100, y: 80 });

    fireEvent.touchStart(target, { touches: [first], changedTouches: [first] });
    fireEvent.touchMove(target, { touches: [moved], changedTouches: [moved] });
    fireEvent.touchCancel(target, { touches: [], changedTouches: [moved] });
    expect(selectedTab()).toHaveAccessibleName('Participants');

    swipe(target, { x: 220, y: 80 }, { x: 100, y: 80 });
    expect(selectedTab()).toHaveAccessibleName('Receipt');
  });

  it('ignores vertical, form-control, and horizontal-strip gestures', () => {
    const onChange = vi.fn();
    render(
      <BillDetailsTabs
        value="participants"
        onChange={onChange}
        participants={
          <div>
            <span>Plain text</span>
            <input aria-label="Amount" />
            <textarea aria-label="Note" />
            <select aria-label="Card"><option>Card</option></select>
            <div data-no-swipe><span>Horizontal strip</span></div>
          </div>
        }
        receipt={<div>Receipt content</div>}
      />,
    );
    const text = screen.getByText('Plain text');

    swipe(text, { x: 220, y: 40 }, { x: 170, y: 190 });
    for (const target of [
      screen.getByLabelText('Amount'),
      screen.getByLabelText('Note'),
      screen.getByLabelText('Card'),
      screen.getByText('Horizontal strip'),
    ]) {
      swipe(target, { x: 220, y: 40 }, { x: 100, y: 44 });
    }

    expect(onChange).not.toHaveBeenCalled();
  });

  it('leaves a sideways drag to a strip that can scroll that way, and pages over it otherwise', () => {
    render(<ControlledTabs participants={<div data-sideways-scroller data-testid="strip"><span>Receipts</span></div>} />);
    const strip = screen.getByTestId('strip');
    const size = (scrollWidth: number, clientWidth: number, scrollLeft: number) => {
      Object.defineProperty(strip, 'scrollWidth', { configurable: true, value: scrollWidth });
      Object.defineProperty(strip, 'clientWidth', { configurable: true, value: clientWidth });
      strip.scrollLeft = scrollLeft;
    };

    size(500, 200, 0);
    swipe(screen.getByText('Receipts'), { x: 220, y: 80 }, { x: 100, y: 84 });
    expect(selectedTab()).toHaveAccessibleName('Participants');

    size(500, 200, 300);
    swipe(screen.getByText('Receipts'), { x: 220, y: 80 }, { x: 100, y: 84 });
    expect(selectedTab()).toHaveAccessibleName('Receipt');
  });

  it('pages over a strip that fits without scrolling', () => {
    render(<ControlledTabs participants={<div data-sideways-scroller><span>One receipt</span></div>} />);

    swipe(screen.getByText('One receipt'), { x: 220, y: 80 }, { x: 100, y: 84 });

    expect(selectedTab()).toHaveAccessibleName('Receipt');
  });

  it('returns to where the reader left each panel', () => {
    const scrollTo = vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    const scrollTop = (y: number) => Object.defineProperty(window, 'scrollY', { configurable: true, value: y });
    // The panels start 200px down the page; the tabs have no height here.
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(
      () => ({ top: 200 - window.scrollY }) as DOMRect,
    );
    render(<ControlledTabs />);

    scrollTop(500);
    swipe(screen.getByText('Participant content'), { x: 220, y: 80 }, { x: 100, y: 80 });
    expect(scrollTo).toHaveBeenLastCalledWith(0, 200);

    scrollTop(450);
    swipe(screen.getByText('Receipt content'), { x: 100, y: 80 }, { x: 220, y: 80 });
    expect(scrollTo).toHaveBeenLastCalledWith(0, 500);
    scrollTop(0);
  });

  it('keeps each panel\'s place when the tab is switched from outside', () => {
    const scrollTo = vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    const scrollTop = (y: number) => Object.defineProperty(window, 'scrollY', { configurable: true, value: y });
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(
      () => ({ top: 200 - window.scrollY }) as DOMRect,
    );
    function ExternallyDriven() {
      const [value, setValue] = useState<BillTab>('participants');
      return (
        <>
          <button type="button" onClick={() => setValue('receipt')}>Pick items</button>
          <BillDetailsTabs value={value} onChange={setValue} participants={<p>P</p>} receipt={<p>R</p>} />
        </>
      );
    }
    render(<ExternallyDriven />);

    scrollTop(500);
    fireEvent.click(screen.getByRole('button', { name: 'Pick items' }));
    expect(scrollTo).toHaveBeenLastCalledWith(0, 200);

    scrollTop(260);
    fireEvent.click(screen.getByRole('tab', { name: 'Participants' }));
    expect(scrollTo).toHaveBeenLastCalledWith(0, 500);
    scrollTop(0);
  });

  it('keeps the panel out of view mounted and laid out, folded away from the reader', async () => {
    render(
      <ControlledTabs
        participants={<input aria-label="Participant note" />}
        receipt={<input aria-label="Receipt note" />}
      />,
    );
    const participantInput = screen.getByLabelText('Participant note');
    const receiptInput = screen.getByLabelText('Receipt note');

    await userEvent.type(participantInput, 'mine');
    await userEvent.click(screen.getByRole('tab', { name: 'Receipt' }));
    const participantPanel = participantInput.closest('[role="tabpanel"]');
    expect(participantPanel).toHaveAttribute('aria-hidden', 'true');
    expect(participantPanel).toHaveAttribute('inert');
    expect(participantPanel).toHaveClass('h-0', 'overflow-hidden');
    await userEvent.type(receiptInput, 'receipt');

    await userEvent.click(screen.getByRole('tab', { name: 'Participants' }));
    expect(participantInput).toHaveValue('mine');
    expect(receiptInput).toHaveValue('receipt');
    expect(receiptInput.closest('[role="tabpanel"]')).toHaveAttribute('aria-hidden', 'true');
    expect(participantInput.closest('[role="tabpanel"]')).not.toHaveAttribute('aria-hidden');
  });
});
