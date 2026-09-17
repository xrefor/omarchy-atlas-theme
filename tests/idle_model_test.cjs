const assert = require('node:assert/strict');
const { test } = require('node:test');
const model = require('../components/desktop/plugins/atlas.idle/IdleModel.js');

test('idle timeouts accept numeric settings, floor fractions and retain explicit zero', () => {
  for (const [value, expected] of [[150, 150], ['300', 300], [12.9, 12], [' 12.9 ', 12], [0, 0], ['0', 0], [2147483, 2147483]]) {
    assert.equal(model.secondsFromConfig(value, 300), expected);
  }
});

test('missing or malformed idle settings use the configured fallback', () => {
  for (const value of [undefined, null, '', ' ', false, true, [], [15], {}, -1, '-3', NaN, Infinity, 'never', 2147484, Number.MAX_VALUE]) {
    assert.equal(model.secondsFromConfig(value, 300), 300, String(value));
  }
});

test('native event parser receives the requested field count and keeps its receiver', () => {
  const event = { data: 'address,workspace,class,title,with,commas', parse(count) {
    assert.equal(this, event);
    assert.equal(count, 4);
    return ['address', 'workspace', 'class', 'title,with,commas'];
  } };
  assert.deepEqual(model.eventParts(event, 4), ['address', 'workspace', 'class', 'title,with,commas']);
});

test('legacy event data still parses when the native parser is absent or throws', () => {
  for (const extra of [{}, { parse() { throw new Error('unsupported'); } }, { parse: true }]) {
    assert.deepEqual(model.eventParts({ data: 'address,workspace,class,title', ...extra }, 4),
                     ['address', 'workspace', 'class', 'title']);
  }
  assert.deepEqual(model.eventParts(null, 1), ['']);
  assert.deepEqual(model.eventParts({}, 1), ['']);
});

test('screensaver windows track multiple outputs and repeated/open/close events without mutating input', () => {
  let windows = Object.freeze({});
  for (const [address, visible, expected] of [
    ['0xa', true, ['0xa']], ['0xb', true, ['0xa', '0xb']],
    ['0xa', true, ['0xa', '0xb']], ['0xunknown', false, ['0xa', '0xb']],
    ['0xa', false, ['0xb']], ['0xa', false, ['0xb']], ['0xb', false, []]
  ]) {
    const before = { ...windows };
    const next = model.screensaverWindowsAfter(windows, address, visible);
    assert.deepEqual(windows, before);
    assert.equal(next.count, expected.length);
    assert.deepEqual(Object.keys(next.windows).sort(), expected.sort());
    windows = Object.freeze(next.windows);
  }
  assert.deepEqual(model.screensaverWindowsAfter(null, '', true), { windows: {}, count: 0 });
  assert.equal(model.screensaverWindowsAfter({ '0xa': true, '0xb': false }, null, false).count, 1);
});
