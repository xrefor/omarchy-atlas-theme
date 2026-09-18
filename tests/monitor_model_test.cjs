const assert = require('node:assert/strict');
const { test } = require('node:test');
const model = require('../components/desktop/plugins/atlas.monitor/Model.js');
const presets = Object.freeze(['1', '1.25', '1.6', '2', '3', '4']);

test('night light accepts actual CLI state, including an absent daemon', () => {
  for (const state of [{ enabled: true, temperature: 4000 },
                       { enabled: false, temperature: 6000 },
                       { enabled: false, temperature: 6500 },
                       { enabled: false, temperature: null }]) {
    assert.deepEqual(model.parseNightlightState(JSON.stringify(state) + '\n', 0), state);
  }
});

test('night light rejects failed commands and malformed status instead of reporting Off', () => {
  const valid = JSON.stringify({ enabled: true, temperature: 4000 });
  for (const code of [1, -1, 127, undefined]) assert.equal(model.parseNightlightState(valid, code), null);
  for (const raw of ['', '{', 'null', '[]', '{}', 'true',
                     '{"enabled":"false","temperature":6500}',
                     '{"enabled":false}', '{"enabled":false,"temperature":"6500"}',
                     '{"enabled":false,"temperature":0}', '{"enabled":false,"temperature":1e999}']) {
    assert.equal(model.parseNightlightState(raw, 0), null, raw);
  }
});

test('brightness rounds input and stays in the usable 1–100 range', () => {
  for (const [value, expected] of [[0, 1], [-20, 1], [1000, 100], [45.4, 45], [45.5, 46], ['73', 73], [100, 100]]) {
    assert.equal(model.clampBrightness(value), expected);
  }
  for (const value of [undefined, null, NaN, Infinity, 'bad']) assert.equal(model.clampBrightness(value), 1);
});

test('scale labels normalize equivalent numeric values', () => {
  for (const [value, expected] of [[1, '1'], ['1.2500', '1.25'], [' 1.6 ', '1.6'], [1.333333, '1.33']]) {
    assert.equal(model.normalizeScale(value), expected);
  }
});

test('invalid scale labels cannot become usable settings', () => {
  for (const value of [undefined, null, '', ' ', false, true, [], [2], {}, 0, -1, NaN, Infinity, Number.MAX_VALUE, '1.25junk']) {
    assert.equal(model.normalizeScale(value), '', String(value));
  }
});

test('ordinary display modes retain supported scaling presets', () => {
  for (const [width, height] of [[1920, 1080], [3840, 2160]]) {
    for (const scale of presets) assert.equal(model.cleanScale(scale, width, height), scale);
    assert.deepEqual(model.availableScales(presets, width, height), presets);
  }
});

test('fractional scales resolve to compatible logical display dimensions', () => {
  assert.equal(model.cleanScale('3', 2560, 1440), '3.2');
  assert.equal(model.cleanScale('1.25', 1366, 768), '2');
  assert.equal(model.cleanScale('1.6', 1366, 768), '2');
});

test('invalid or unrepresentable scales and display dimensions are rejected', () => {
  for (const value of [0, -1, NaN, Infinity, Number.MAX_VALUE, 'bad', true, [], 0.001]) {
    assert.equal(model.cleanScale(value, 1920, 1080), '', String(value));
  }
  for (const [width, height] of [[0, 1080], [1920, -1], [NaN, 1080], [1920, Infinity], [Number.MAX_VALUE, 1080], [0.001, 0.001]]) {
    assert.equal(model.cleanScale(1, width, height), '');
  }
});

test('duplicate effective scales keep the closest preset and preserve menu order', () => {
  assert.deepEqual(model.availableScales(presets, 1366, 768), ['1', '2']);
  assert.deepEqual(model.availableScales(['1', '1.6', '1.25'], 1366, 768), ['1', '1.6']);
  assert.deepEqual(presets, ['1', '1.25', '1.6', '2', '3', '4']);
});

test('invalid presets do not appear as zero scale or other spurious menu options', () => {
  assert.deepEqual(model.availableScales(['bad', '0', '-1', '', null, true, [], '1', '1.25'], 1920, 1080),
                   ['1', '1.25']);
});

test('missing mode information retains valid presets while a non-array yields no options', () => {
  for (const [width, height] of [[undefined, undefined], [0, 0], [NaN, 1080]]) {
    assert.deepEqual(model.availableScales(['bad', '1', '1.25'], width, height), ['1', '1.25']);
  }
  for (const value of [null, undefined, {}, '1.25']) assert.deepEqual(model.availableScales(value, 1920, 1080), []);
});

test('current scale selects the closest equivalent preset or reports no match', () => {
  assert.equal(model.matchingScaleIndex(presets, '2', 1366, 768), 3);
  assert.equal(model.matchingScaleIndex(presets, '3.2', 2560, 1440), 4);
  assert.equal(model.matchingScaleIndex(presets, '1.1', 1920, 1080), -1);
  for (const value of [undefined, NaN, 0, -1]) assert.equal(model.matchingScaleIndex(presets, value, 1920, 1080), -1);
  assert.equal(model.matchingScaleIndex(null, 1, 1920, 1080), -1);
});

test('brightness descriptions change at their displayed rounded thresholds', () => {
  for (const [percent, name] of [[1, 'Night owl'], [9.5, 'Candlelit'], [20, 'Lamp light'], [30, 'Soft glow'],
                                [45, 'Even day'], [65, 'Golden hour'], [80, 'Solar flare'], [94.5, 'Sun blast']]) {
    assert.equal(model.brightnessName(percent), name);
  }
});

test('invalid display JSON and non-array payloads become an empty display list', () => {
  for (const raw of [undefined, '', '{', 'null', '{}', 'false', '"text"']) {
    assert.deepEqual(model.parseDisplays(raw), { displays: [], enabledDisplayCount: 0 });
  }
});

test('display records preserve mode data and count only real enabled outputs', () => {
  const displays = [
    { name: 'eDP-1', enabled: true, focused: true, width: 1920, height: 1080 },
    { name: 'DP-1', enabled: false, focused: false, width: 2560, height: 1440 },
    { name: 'HDMI-A-1', enabled: true, focused: false, width: 3840, height: 2160 }
  ];
  assert.deepEqual(model.parseDisplays(JSON.stringify(displays)), { displays, enabledDisplayCount: 2 });
});

test('malformed display rows cannot inflate the last-enabled-display guard', () => {
  const display = { name: 'eDP-1', enabled: true, width: 1920, height: 1080 };
  const invalid = [null, 1, 'DP-1', [], {}, { name: '', enabled: true }, { name: 'DP-1', enabled: 'false' }];
  assert.deepEqual(model.parseDisplays(JSON.stringify([display, ...invalid])),
                   { displays: [display], enabledDisplayCount: 1 });
});

test('duplicate display names count once and keep the first valid record', () => {
  for (const name of ['eDP-1', '__proto__']) {
    const display = { name, enabled: true, width: 1920, height: 1080 };
    assert.deepEqual(model.parseDisplays(JSON.stringify([display, display, { name, enabled: false }])),
                     { displays: [display], enabledDisplayCount: 1 });
  }
});
