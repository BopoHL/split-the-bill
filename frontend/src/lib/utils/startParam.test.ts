import { describe, expect, it } from 'vitest';

import {
  parseBillStartParam,
  parseInviteStartParam,
  parseSeatInviteStartParam,
  startParamKind,
  startSource,
} from './startParam';

describe('startParamKind', () => {
  it.each([
    [null, 'none'],
    ['', 'none'],
    ['pro', 'pro'],
    ['inv_abc_pay', 'invite'],
    ['seat_open_42_tok', 'seat'],
    ['join_tok', 'join'],
    ['bill_tok', 'bill'],
    ['scan_tok', 'scan'],
    ['src_tiktok', 'source'],
    ['ad_autumn', 'other'],
  ])('%s → %s', (param, kind) => {
    expect(startParamKind(param)).toBe(kind);
  });
});

describe('startSource', () => {
  it.each([
    ['src_tiktok', 'tiktok'],
    ['src_Channel-Post_2', 'channel-post_2'],
    ['src_ad!<b>', 'adb'],
    ['src_', null],
    ['inv_abc', null],
    [null, null],
  ])('%s → %s', (param, source) => {
    expect(startSource(param)).toBe(source);
  });
});

describe('parseSeatInviteStartParam', () => {
  it('keeps legacy personal invite links as claim-and-confirm', () => {
    expect(parseSeatInviteStartParam('seat_42_pub_token')).toEqual({
      participantId: 42,
      token: 'pub_token',
      confirmPayment: true,
    });
  });

  it('parses open-only personal invite links without payment confirmation', () => {
    expect(parseSeatInviteStartParam('seat_open_42_pub_token')).toEqual({
      participantId: 42,
      token: 'pub_token',
      confirmPayment: false,
    });
  });

  it('ignores malformed personal invite links', () => {
    expect(parseSeatInviteStartParam('seat_0_pub_token')).toBeNull();
    expect(parseSeatInviteStartParam('seat_open_bad_pub_token')).toBeNull();
    expect(parseSeatInviteStartParam('join_pub_token')).toBeNull();
  });
});

describe('parseBillStartParam', () => {
  it('opens a bill the bot linked to', () => {
    expect(parseBillStartParam('bill_abc123')).toEqual({ token: 'abc123', scan: false });
  });

  it('asks for the scanner when the bot sent the scan link', () => {
    expect(parseBillStartParam('scan_abc123')).toEqual({ token: 'abc123', scan: true });
  });

  it('leaves the invite links to their own parser', () => {
    expect(parseBillStartParam('join_abc123')).toBeNull();
    expect(parseBillStartParam('seat_4_abc123')).toBeNull();
    expect(parseBillStartParam('inv_abc123')).toBeNull();
    expect(parseBillStartParam(null)).toBeNull();
  });
});

describe('parseInviteStartParam', () => {
  it('reads a minted invite', () => {
    expect(parseInviteStartParam('inv_AbC-123_x')).toEqual({
      code: 'AbC-123_x',
      confirmPayment: false,
    });
  });

  it('reads the pay variant of a seat invite', () => {
    expect(parseInviteStartParam('inv_AbC123_pay')).toEqual({
      code: 'AbC123',
      confirmPayment: true,
    });
  });

  it('ignores the older link formats', () => {
    expect(parseInviteStartParam('join_token')).toBeNull();
    expect(parseInviteStartParam('seat_1_token')).toBeNull();
    expect(parseInviteStartParam(null)).toBeNull();
  });
});
