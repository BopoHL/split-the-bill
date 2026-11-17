import { TourAnchor, type TourTarget } from './anchors';

/**
 * What a step asks of the person:
 * - `tap`: press the lit element for real; the app does the rest.
 * - `look`: read about the lit element, then carry on from the bubble.
 * - `use`: work in the lit part as long as it takes — a sheet with several
 *   things to tick; the tour carries on once it has closed.
 * - `stage`: press the lit element, but the tour plays the press — what would
 *   happen, for things it must not really do, like messaging someone; or the
 *   press itself, on a row whose parts do other things when hit directly.
 * - `scene`: a screen of the tour's own, with nothing lit behind it.
 */
export type TourStepKind = 'tap' | 'look' | 'use' | 'stage' | 'scene';

export type TourStage = 'fillCard' | 'startScan' | 'openSeat' | 'inviteFriends';
export type TourScene = 'scan' | 'finale';

export type TourStepId =
  | 'createBill' | 'peopleMore' | 'peopleLess' | 'people' | 'card' | 'paymentNext'
  | 'scan' | 'scanning' | 'billReady'
  | 'openSeat' | 'assign' | 'dish' | 'confirmDishes'
  | 'receiptTab' | 'itemAssign' | 'itemPerson' | 'itemConfirm'
  | 'participantsTab' | 'invite' | 'friends' | 'closeBill' | 'remainder' | 'finale'
  | 'guestSeat' | 'guestPick' | 'guestDishes' | 'guestShare' | 'guestPaid';

interface StepBase {
  id: TourStepId;
  /** Passed over when its element is not on the screen at all — what there is
   *  to pay, before anything has been picked. */
  optional?: boolean;
}

export type TourStep =
  | (StepBase & { kind: 'tap' | 'look' | 'use'; target: TourTarget })
  | (StepBase & { kind: 'stage'; target: TourTarget; stage: TourStage })
  | (StepBase & { kind: 'scene'; scene: TourScene; waitFor?: TourTarget });

/**
 * The walk through one bill, from the empty home screen to closing it. The
 * table is laid before anyone is invited — dishes on seats, a card on the bill
 * — because that is what lets friends take their seat and pay from the chat.
 */
export const TOUR_STEPS: readonly TourStep[] = [
  { id: 'createBill', kind: 'tap', target: { anchor: TourAnchor.CreateBill } },
  { id: 'peopleMore', kind: 'tap', target: { anchor: TourAnchor.PeopleMore } },
  { id: 'peopleLess', kind: 'tap', target: { anchor: TourAnchor.PeopleLess } },
  { id: 'people', kind: 'tap', target: { anchor: TourAnchor.WizardNext } },
  { id: 'card', kind: 'stage', target: { anchor: TourAnchor.PaymentChooser }, stage: 'fillCard' },
  { id: 'paymentNext', kind: 'tap', target: { anchor: TourAnchor.WizardNext } },
  { id: 'scan', kind: 'stage', target: { anchor: TourAnchor.ScanReceipt }, stage: 'startScan' },
  { id: 'scanning', kind: 'scene', scene: 'scan' },
  { id: 'billReady', kind: 'look', target: { anchor: TourAnchor.BillTabs } },
  { id: 'openSeat', kind: 'stage', target: { anchor: TourAnchor.OpenSeat, key: 1 }, stage: 'openSeat' },
  { id: 'assign', kind: 'tap', target: { anchor: TourAnchor.AssignItems, key: 1 } },
  { id: 'dish', kind: 'tap', target: { anchor: TourAnchor.AssignDish } },
  { id: 'confirmDishes', kind: 'tap', target: { anchor: TourAnchor.AssignConfirm } },
  { id: 'receiptTab', kind: 'tap', target: { anchor: TourAnchor.ReceiptTab } },
  { id: 'itemAssign', kind: 'tap', target: { anchor: TourAnchor.ItemAssign } },
  { id: 'itemPerson', kind: 'tap', target: { anchor: TourAnchor.ItemPerson, key: 2 } },
  { id: 'itemConfirm', kind: 'tap', target: { anchor: TourAnchor.AssignConfirm } },
  { id: 'participantsTab', kind: 'tap', target: { anchor: TourAnchor.ParticipantsTab } },
  { id: 'invite', kind: 'stage', target: { anchor: TourAnchor.Invite }, stage: 'inviteFriends' },
  { id: 'friends', kind: 'look', target: { anchor: TourAnchor.Participants } },
  { id: 'closeBill', kind: 'tap', target: { anchor: TourAnchor.CloseBill } },
  { id: 'remainder', kind: 'tap', target: { anchor: TourAnchor.SplitRemainder } },
  { id: 'finale', kind: 'scene', scene: 'finale', waitFor: { anchor: TourAnchor.CreateBill } },
];

/** host: the newcomer's own bill, on a demo. guest: a bill they were invited
 *  to, the real one — its finished steps are what they did there. */
export type TourName = 'host' | 'guest';

export interface Tour {
  name: TourName;
  steps: readonly TourStep[];
}

export const HOST_TOUR: Tour = { name: 'host', steps: TOUR_STEPS };

/**
 * Someone who has just taken a seat on another person's bill: which seat is
 * theirs, how to say what they ate, what they owe and where it goes. On the
 * bill itself — what they tick is really ticked, so paying is only pointed at.
 * Nothing to pay shows before anything is picked, hence the optional steps.
 */
export function guestTour({ canPickItems }: { canPickItems: boolean }): Tour {
  const picking: TourStep[] = [
    { id: 'guestPick', kind: 'tap', target: { anchor: TourAnchor.ChooseItems } },
    { id: 'guestDishes', kind: 'use', target: { anchor: TourAnchor.PickSheet } },
  ];
  return {
    name: 'guest',
    steps: [
      { id: 'guestSeat', kind: 'look', target: { anchor: TourAnchor.MySeat } },
      ...(canPickItems ? picking : []),
      { id: 'guestShare', kind: 'look', target: { anchor: TourAnchor.MyShare }, optional: true },
      { id: 'guestPaid', kind: 'look', target: { anchor: TourAnchor.IPaid }, optional: true },
    ],
  };
}

/** The card the tour «types in»; the demo bill carries it, nobody saves it. */
export const DEMO_CARD = '8600 1234 5678 9010';
