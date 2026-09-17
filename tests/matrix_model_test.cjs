// Deterministic model tests: no desktop, session lock, or authentication calls.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'components/desktop/plugins/atlas.lock/MatrixModel.js'), 'utf8');
const brand = fs.readFileSync(path.join(root, 'components/desktop/branding/screensaver.txt'), 'utf8');
// Each call gets fresh model state and local clock/randomness. Avoid changing
// process-wide globals or adding VM proxy overhead to every animation tick.
const loadModel = new Function('Math', 'Date', 'module', source + '\nreturn module.exports;');

function harness(seed = 1337) {
  let now = 0;
  const math = Object.create(Math);
  math.random = () => ((seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0) / 2 ** 32);
  const model = loadModel(math, { now: () => now }, { exports: {} });
  return { model, advance: () => { now += 16; } };
}

function assertPaintsOnce(model, sim, width, height) {
  let clears = 0;
  const painted = new Set();
  const context = {
    fillRect(x, y, w, h) {
      assert.deepEqual([x, y, w, h], [0, 0, width, height]);
      clears++;
    },
    fillText(text, x, y) {
      const cell = `${x},${y}`;
      assert.ok(!painted.has(cell), `painted a cell twice: ${cell}`);
      painted.add(cell);
    }
  };
  model.paint(context, sim, width, height);
  assert.equal(clears, 1);
  assert.equal(painted.size, sim.draw.length);
}

test('completed fill columns have one owner and keep animating', () => {
  const { model } = harness();
  const sim = model.create(2, 3, 'ATLAS', 11, 22, 18);
  sim.phase = 'fill';
  sim.rainComplete = true;
  // One column fills immediately while its neighbor still has pending glyphs.
  for (const [index, column] of sim.pending.entries()) {
    column.phase = 'fill';
    column.length = sim.rows;
    column.fallDelay = index === 0 ? 0 : 100;
  }
  for (let frame = 0; frame < sim.rows; frame++) model.tick(sim);
  assert.equal(sim.full.length, 1);
  const completed = sim.full[0];
  assert.ok(!sim.active.includes(completed), 'completed column remains active');
  assert.equal(new Set(sim.draw).size, sim.draw.length);
  assertPaintsOnce(model, sim, 22, 66);

  model.CONFIG.symbolSwap = 1;
  model.CONFIG.colorSwap = 1;
  for (const glyph of completed.visible) {
    glyph.ch = 'sentinel';
    glyph.color = '#010203';
  }
  model.tick(sim);
  assert.equal(sim.phase, 'fill');
  assert.equal(completed.visible.length, sim.rows);
  for (const glyph of completed.visible) {
    assert.notEqual(glyph.ch, 'sentinel', 'completed column froze during fill');
    assert.ok(sim.rainColors.includes(glyph.color));
  }
});

for (const [name, width, height, text, seed] of [
  ['1080p branding', 1920, 1080, brand, 1337],
  ['4K branding', 3840, 2160, brand, 1337],
  ['small clipped branding', 330, 176, brand, 42],
  ['minimum grid', 1, 1, 'ATLAS', 7],
  ['empty branding', 187, 132, '', 99]
]) {
  test(`${name}: unique glyphs through rain, fill, resolve and restart`, () => {
    const { model, advance } = harness(seed);
    let previousGlyphs = new Set();
    for (let cycle = 0; cycle < 2; cycle++) {
      const sim = model.create(Math.floor(width / 11), Math.floor(height / 22), text, 11, 22, 18);
      const allGlyphs = sim.pending.flatMap(column => Array.from(column.chars));
      assert.ok(allGlyphs.every(glyph => !previousGlyphs.has(glyph)), 'restart reused old glyph state');
      const expected = new Set(allGlyphs.filter(glyph => glyph.input !== ' '));
      const phases = new Set([sim.phase]);
      let finished = false;
      let sawCompletedFill = false;
      for (let frame = 0; frame < 10000; frame++) {
        advance();
        if (!model.tick(sim)) {
          finished = true;
          break;
        }
        const label = `${name}, cycle ${cycle}, frame ${frame}, phase ${sim.phase}`;
        assert.equal(new Set(sim.draw).size, sim.draw.length, `duplicate glyph: ${label}`);
        assert.ok(sim.draw.every(glyph => glyph.visible), `hidden glyph: ${label}`);
        if (sim.phase === 'rain' || sim.phase === 'fill') {
          const columns = [...sim.pending, ...sim.active, ...sim.full];
          assert.equal(columns.length, sim.cols, `missing or duplicated column: ${label}`);
          assert.equal(new Set(columns).size, sim.cols, `column has two owners: ${label}`);
        }
        if (!phases.has(sim.phase) || (sim.phase === 'fill' && sim.full.length && !sawCompletedFill)) {
          assertPaintsOnce(model, sim, width, height);
          if (sim.phase === 'fill' && sim.full.length) sawCompletedFill = true;
        }
        phases.add(sim.phase);
      }
      assert.ok(finished, `${name}: animation did not finish`);
      assert.deepEqual([...phases], ['rain', 'fill', 'resolve']);
      assert.ok(sim.finalFrameShown);
      assert.equal(sim.draw.length, expected.size, 'final branding lost or added glyphs');
      for (const glyph of sim.draw) {
        assert.ok(expected.has(glyph));
        assert.equal(glyph.ch, glyph.input);
        assert.equal(glyph.y, glyph.homeY);
        assert.equal(glyph.color, glyph.finalColor);
      }
      assertPaintsOnce(model, sim, width, height);
      assert.equal(model.tick(sim), false, 'completed animation should request a restart');
      previousGlyphs = new Set(allGlyphs);
    }
  });
}
