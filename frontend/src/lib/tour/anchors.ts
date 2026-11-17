/** The elements the guided tour points at, marked with `data-tour`.
 *  Where one anchor repeats — a seat's button, a dish row — `data-tour-key`
 *  or the order on screen tells them apart. */
export const TourAnchor = {
  CreateBill: 'create-bill',
  PeopleMore: 'people-more',
  PeopleLess: 'people-less',
  WizardNext: 'wizard-next',
  PaymentChooser: 'payment-chooser',
  CardField: 'card-field',
  ScanReceipt: 'scan-receipt',
  BillTabs: 'bill-tabs',
  ParticipantsTab: 'participants-tab',
  ReceiptTab: 'receipt-tab',
  Invite: 'invite',
  Participants: 'participants',
  OpenSeat: 'open-seat',
  AssignItems: 'assign-items',
  AssignDish: 'assign-dish',
  ItemAssign: 'item-assign',
  ItemPerson: 'item-person',
  AssignConfirm: 'assign-confirm',
  CloseBill: 'close-bill',
  SplitRemainder: 'split-remainder',
  MySeat: 'my-seat',
  ChooseItems: 'choose-items',
  PickSheet: 'pick-sheet',
  MyShare: 'my-share',
  IPaid: 'i-paid',
} as const;

export type TourAnchorId = (typeof TourAnchor)[keyof typeof TourAnchor];

export interface TourTarget {
  anchor: TourAnchorId;
  key?: string | number;
  /** Which of several matching elements, in document order. */
  index?: number;
}

export function targetSelector({ anchor, key }: TourTarget): string {
  const base = `[data-tour="${anchor}"]`;
  return key === undefined ? base : `${base}[data-tour-key="${key}"]`;
}

export function findTarget(target: TourTarget, root: ParentNode = document): HTMLElement | null {
  return root.querySelectorAll<HTMLElement>(targetSelector(target))[target.index ?? 0] ?? null;
}
