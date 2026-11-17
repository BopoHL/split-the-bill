export interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

/**
 * Where a lit element stands:
 * - `hidden`: not laid out for the person — folded away, inert, off to the side;
 * - `below-fold`: there, but scrolled out of view;
 * - `covered`: in view, under something else — a sheet on its way out;
 * - `ready`: on top and in view, safe to light up.
 */
export type TargetView =
  | { kind: 'hidden' }
  | { kind: 'below-fold' }
  | { kind: 'covered' }
  | { kind: 'ready'; box: Box };

/** Close enough when narrowing down where a bar starts to cover an element. */
const EDGE_PRECISION_PX = 2;

export function inspectTarget(element: HTMLElement, ignore: Element | null): TargetView {
  const rect = element.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0 || element.closest('[inert]')) return { kind: 'hidden' };

  const x = rect.left + rect.width / 2;
  const y = rect.top + rect.height / 2;
  if (x < 0 || x > window.innerWidth) return { kind: 'hidden' };
  if (y < 0 || y > window.innerHeight) return { kind: 'below-fold' };

  if (typeof document.elementsFromPoint !== 'function') {
    return { kind: 'ready', box: { top: rect.top, left: rect.left, width: rect.width, height: rect.height } };
  }

  // Whatever the finger would hit at a height, looking through the tour itself.
  const onTop = (at: number) => {
    const hit = document.elementsFromPoint(x, at).find((node) => !ignore?.contains(node));
    return !hit || element.contains(hit) || hit.contains(element);
  };
  if (!onTop(y)) return { kind: 'covered' };

  // A long element may run under a bar that stays put — a header above, a dock
  // below. Only the part in the clear is lit.
  const top = clearEdge(onTop, y, Math.max(rect.top, 0));
  const bottom = clearEdge(onTop, y, Math.min(rect.bottom, window.innerHeight) - 1);
  return { kind: 'ready', box: { top, left: rect.left, width: rect.width, height: bottom + 1 - top } };
}

/** How far from `inside` towards `edge` the element stays uncovered, assuming
 *  whatever covers it comes in from the edge. */
function clearEdge(onTop: (at: number) => boolean, inside: number, edge: number): number {
  if (onTop(edge)) return edge;
  let clear = inside;
  let covered = edge;
  while (Math.abs(covered - clear) > EDGE_PRECISION_PX) {
    const middle = (clear + covered) / 2;
    if (onTop(middle)) clear = middle;
    else covered = middle;
  }
  return clear;
}

export function sameBox(a: Box | null, b: Box | null): boolean {
  if (a === b) return true;
  if (!a || !b) return false;
  return Math.abs(a.top - b.top) < 0.5
    && Math.abs(a.left - b.left) < 0.5
    && Math.abs(a.width - b.width) < 0.5
    && Math.abs(a.height - b.height) < 0.5;
}
