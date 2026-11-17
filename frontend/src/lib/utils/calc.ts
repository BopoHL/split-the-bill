// Tiny arithmetic engine for the amount keypad. Expressions are stored in a
// canonical ASCII form (`+ - * /`, `.`); the keypad maps display glyphs
// (× ÷ −) to these on input and back on render. Values are money, so results
// are rounded to 2 decimals (the tiin precision the backend stores).

const DISPLAY_GLYPH: Record<string, string> = {
  '+': '+',
  '-': '−',
  '*': '×',
  '/': '÷',
};

const isOperator = (c: string) => c === '+' || c === '-' || c === '*' || c === '/';
const isNumberChar = (c: string) => (c >= '0' && c <= '9') || c === '.';

type Token = { type: 'num'; value: number } | { type: 'op'; value: string };

/** A leading `-`/`+` (at the start or right after another operator) belongs to
 *  the following number, not a binary subtraction. */
function tokenize(expr: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;
  while (i < expr.length) {
    const c = expr[i];
    if (c === ' ') {
      i++;
      continue;
    }
    if (isOperator(c)) {
      const prev = tokens[tokens.length - 1];
      const unary = (c === '-' || c === '+') && (!prev || prev.type === 'op');
      if (unary) {
        let raw = c === '-' ? '-' : '';
        i++;
        while (i < expr.length && isNumberChar(expr[i])) raw += expr[i++];
        tokens.push({ type: 'num', value: Number(raw) });
      } else {
        tokens.push({ type: 'op', value: c });
        i++;
      }
    } else if (isNumberChar(c)) {
      let raw = '';
      while (i < expr.length && isNumberChar(expr[i])) raw += expr[i++];
      tokens.push({ type: 'num', value: Number(raw) });
    } else {
      i++;
    }
  }
  return tokens;
}

function reduceTokens(tokens: Token[]): number | null {
  let t = tokens;
  if (t.length && t[t.length - 1].type === 'op') t = t.slice(0, -1);
  if (!t.length || t[0].type !== 'num') return null;

  for (let k = 0; k < t.length; k++) {
    const expectNum = k % 2 === 0;
    if (expectNum && (t[k].type !== 'num' || Number.isNaN((t[k] as { value: number }).value)))
      return null;
    if (!expectNum && t[k].type !== 'op') return null;
  }

  const afterMulDiv: Token[] = [t[0]];
  for (let k = 1; k < t.length; k += 2) {
    const op = (t[k] as { value: string }).value;
    const next = t[k + 1] as { value: number };
    if (op === '*' || op === '/') {
      const prev = afterMulDiv.pop() as { value: number };
      if (op === '/' && next.value === 0) return null;
      afterMulDiv.push({
        type: 'num',
        value: op === '*' ? prev.value * next.value : prev.value / next.value,
      });
    } else {
      afterMulDiv.push(t[k], t[k + 1]);
    }
  }

  let acc = (afterMulDiv[0] as { value: number }).value;
  for (let k = 1; k < afterMulDiv.length; k += 2) {
    const op = (afterMulDiv[k] as { value: string }).value;
    const next = (afterMulDiv[k + 1] as { value: number }).value;
    acc = op === '+' ? acc + next : acc - next;
  }
  return acc;
}

function round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100;
}

/** Normalize keypad glyphs and decimal comma to the canonical ASCII form. */
export function normalizeExpression(expr: string): string {
  return expr.replace(/×/g, '*').replace(/÷/g, '/').replace(/−/g, '-').replace(/,/g, '.');
}

/**
 * Evaluate an expression with standard precedence (× ÷ before + −), left to
 * right within a precedence level. A trailing operator is ignored (so a live
 * preview works mid-typing). Returns null for empty/invalid input or division
 * by zero. The result is rounded to 2 decimals.
 */
export function evaluate(expr: string): number | null {
  const result = reduceTokens(tokenize(normalizeExpression(expr)));
  return result == null ? null : round2(result);
}

function formatNumberPart(part: string): string {
  const negative = part.startsWith('-');
  const body = negative ? part.slice(1) : part;
  const dot = body.indexOf('.');
  const intPart = dot === -1 ? body : body.slice(0, dot);
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  const tail = dot === -1 ? '' : '.' + body.slice(dot + 1);
  return (negative ? '−' : '') + grouped + tail;
}

/** Pretty-print an in-progress expression: grouped numbers, spaced glyph
 *  operators, e.g. "52000+3000" → "52 000 + 3 000", "-5000" → "−5 000". */
export function formatExpression(expr: string): string {
  const src = normalizeExpression(expr);
  let out = '';
  let numBuf = '';
  const flush = () => {
    if (numBuf !== '') {
      out += formatNumberPart(numBuf);
      numBuf = '';
    }
  };
  for (let i = 0; i < src.length; i++) {
    const c = src[i];
    if (isOperator(c) && (i === 0 || isOperator(src[i - 1])) && (c === '-' || c === '+')) {
      numBuf += c === '-' ? '-' : '';
    } else if (isOperator(c)) {
      flush();
      out += ` ${DISPLAY_GLYPH[c]} `;
    } else {
      numBuf += c;
    }
  }
  flush();
  return out.trim();
}

/** Whether the expression contains a binary operator (used to decide if the
 *  header shows the expression line above the live total). */
export function hasBinaryOperator(expr: string): boolean {
  const src = normalizeExpression(expr);
  for (let i = 1; i < src.length; i++) {
    if (isOperator(src[i]) && isNumberChar(src[i - 1])) return true;
  }
  return false;
}

/** Format a numeric result with thousands separators and a sign, dropping a
 *  trailing ".00" — e.g. 55000 → "55 000", -5000 → "−5 000", 5000.5 → "5 000.5". */
export function formatResult(n: number): string {
  const rounded = round2(n);
  const [intRaw, decRaw = ''] = Math.abs(rounded).toFixed(2).split('.');
  const grouped = intRaw.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  const dec = decRaw === '00' ? '' : '.' + decRaw.replace(/0+$/, '');
  const sign = rounded < 0 ? '−' : '';
  return sign + grouped + dec;
}

/** Collapse an expression to the plain numeric string the parent stores
 *  (parseable by parseFloat): 55000 → "55000", -5000 → "-5000". Empty/invalid
 *  expressions collapse to "". */
export function collapseExpression(expr: string): string {
  const result = evaluate(expr);
  return result == null ? '' : String(result);
}
