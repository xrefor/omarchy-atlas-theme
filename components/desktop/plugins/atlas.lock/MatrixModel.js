// Port of ttfx/terminaltexteffects matrix, matching
// ~/.local/bin/omarchy-screensaver flags. Cell grid, not a terminal.

var SYMBOLS = [
  "2", "5", "9", "8", "Z", "*", ")", ":", ".", "\"", "=", "+", "-", "¦", "|", "_",
  "ｦ", "ｱ", "ｳ", "ｴ", "ｵ", "ｶ", "ｷ", "ｹ", "ｺ", "ｻ", "ｼ", "ｽ", "ｾ", "ｿ",
  "ﾀ", "ﾂ", "ﾃ", "ﾅ", "ﾆ", "ﾇ", "ﾈ", "ﾊ", "ﾋ", "ﾎ", "ﾏ", "ﾐ", "ﾑ", "ﾒ", "ﾓ",
  "ﾔ", "ﾕ", "ﾗ", "ﾘ", "ﾜ"
]

var CONFIG = {
  background: "#100e0c",
  highlight: "#f2ebe0",
  rainStops: ["#2a2622", "#3a342c", "#6e675c", "#8a847a", "#3a342c", "#6e675c", "#2a2622", "#ff5a12"],
  rainGradientSteps: 6,
  fallMin: 6,
  fallMax: 18,
  columnDelayMin: 5,
  columnDelayMax: 14,
  rainTimeMs: 18000,
  symbolSwap: 0.005,
  colorSwap: 0.012,
  resolveDelay: 5,
  finalStops: ["#d6cfc4", "#9a948c"],
  finalSteps: 12,
  finalFrames: 3,
  resolveBlendSteps: 8,
  dropChance: 0.08
}

// Appearance follows the same shell palette and font as the lock field.
var fontFamily = "monospace"

function setAppearance(background, foreground, muted, accent, secondary, family) {
  CONFIG.background = background
  CONFIG.highlight = foreground
  CONFIG.rainStops = [muted, secondary, muted, secondary, muted, accent]
  CONFIG.finalStops = [foreground, secondary]
  fontFamily = family
}

function randInt(min, max) {
  return min + Math.floor(Math.random() * (max - min + 1))
}

function pick(list) {
  return list[Math.floor(Math.random() * list.length)]
}

function hexToRgb(hex) {
  var h = String(hex || "").replace("#", "")
  if (h.length === 3) h = h.charAt(0) + h.charAt(0) + h.charAt(1) + h.charAt(1) + h.charAt(2) + h.charAt(2)
  return {
    r: parseInt(h.slice(0, 2), 16) || 0,
    g: parseInt(h.slice(2, 4), 16) || 0,
    b: parseInt(h.slice(4, 6), 16) || 0
  }
}

function rgbToHex(r, g, b) {
  function byte(n) {
    var s = Math.max(0, Math.min(255, Math.round(n))).toString(16)
    return s.length === 1 ? "0" + s : s
  }
  return "#" + byte(r) + byte(g) + byte(b)
}

function lerpColor(a, b, t) {
  var A = hexToRgb(a)
  var B = hexToRgb(b)
  return rgbToHex(A.r + (B.r - A.r) * t, A.g + (B.g - A.g) * t, A.b + (B.b - A.b) * t)
}

function expandGradient(stops, steps) {
  var out = []
  if (!stops || !stops.length) return out
  if (stops.length === 1 || steps <= 1) return stops.slice()
  for (var i = 0; i < stops.length - 1; i++) {
    for (var s = 0; s < steps; s++) out.push(lerpColor(stops[i], stops[i + 1], s / steps))
  }
  out.push(stops[stops.length - 1])
  return out
}

function darken(hex, factor) {
  var c = hexToRgb(hex)
  return rgbToHex(c.r * factor, c.g * factor, c.b * factor)
}

function shuffle(list) {
  for (var i = list.length - 1; i > 0; i--) {
    var j = Math.floor(Math.random() * (i + 1))
    var tmp = list[i]
    list[i] = list[j]
    list[j] = tmp
  }
  return list
}

function parseBrand(text) {
  var raw = String(text || "").replace(/\s+$/, "")
  if (!raw) return []
  return raw.split("\n")
}

function brandAt(lines, cols, rows, x, y) {
  if (!lines.length) return " "
  var height = lines.length
  var width = 0
  for (var i = 0; i < lines.length; i++) {
    if (lines[i].length > width) width = lines[i].length
  }
  var x0 = Math.floor((cols - width) / 2)
  var y0 = Math.floor((rows - height) / 2)
  var lx = x - x0
  var ly = y - y0
  if (ly < 0 || ly >= height || lx < 0) return " "
  var line = lines[ly]
  if (lx >= line.length) return " "
  var ch = line.charAt(lx)
  return ch ? ch : " "
}

function brandBounds(lines, cols, rows) {
  var height = lines.length
  var width = 0
  for (var i = 0; i < lines.length; i++) {
    if (lines[i].length > width) width = lines[i].length
  }
  return {
    left: Math.floor((cols - width) / 2),
    top: Math.floor((rows - height) / 2),
    right: Math.floor((cols - width) / 2) + Math.max(width, 1) - 1,
    bottom: Math.floor((rows - height) / 2) + Math.max(height, 1) - 1
  }
}

function radialFinal(x, y, bounds, stops, steps) {
  var cx = (bounds.left + bounds.right) / 2
  var cy = (bounds.top + bounds.bottom) / 2
  var dx = bounds.right === bounds.left ? 0 : (x - cx) / ((bounds.right - bounds.left) / 2)
  var dy = bounds.bottom === bounds.top ? 0 : (y - cy) / ((bounds.bottom - bounds.top) / 2)
  var t = Math.min(1, Math.sqrt(dx * dx + dy * dy))
  if (steps > 1) t = Math.round(t * (steps - 1)) / (steps - 1)
  if (stops.length === 1) return stops[0]
  var scaled = t * (stops.length - 1)
  var i = Math.min(stops.length - 2, Math.floor(scaled))
  return lerpColor(stops[i], stops[i + 1], scaled - i)
}

function setupColumn(col, phase) {
  col.phase = phase
  col.pending = []
  col.visible = []
  for (var i = 0; i < col.chars.length; i++) {
    var ch = col.chars[i]
    ch.visible = false
    ch.resolving = false
    ch.y = ch.homeY
    col.pending.push(ch)
  }
  if (phase === "fill") {
    col.fallDelay = randInt(Math.max(Math.floor(CONFIG.fallMin / 3), 1), Math.max(Math.floor(CONFIG.fallMax / 3), 1))
    col.length = col.chars.length
  } else {
    col.fallDelay = randInt(CONFIG.fallMin, CONFIG.fallMax)
    col.length = randInt(Math.max(1, Math.floor(col.chars.length * 0.1)), col.chars.length)
  }
  col.fallLeft = 0
  col.holdTime = col.length === col.chars.length ? randInt(20, 45) : 0
  col.dropChance = CONFIG.dropChance
}

function trimColumn(col, rainColors) {
  if (!col.visible.length) return
  var popped = col.visible.shift()
  popped.visible = false
  if (col.visible.length > 1) {
    col.visible[0].color = darken(pick(rainColors.slice(-3)), 0.65)
  }
}

function dropColumn(col, rows) {
  var kept = []
  for (var i = 0; i < col.visible.length; i++) {
    var ch = col.visible[i]
    ch.y += 1
    if (ch.y >= rows) ch.visible = false
    else kept.push(ch)
  }
  col.visible = kept
}

function tickColumn(col, rows, rainColors) {
  if (!col.fallLeft) {
    if (col.pending.length) {
      var next = col.pending.shift()
      next.ch = pick(SYMBOLS)
      next.color = CONFIG.highlight
      next.visible = true
      next.y = next.homeY
      if (col.visible.length) col.visible[col.visible.length - 1].color = pick(rainColors)
      col.visible.push(next)
    } else if (col.visible.length) {
      var head = col.visible[col.visible.length - 1]
      if (head.color === CONFIG.highlight) head.color = pick(rainColors)
      if (col.holdTime) {
        col.holdTime -= 1
      } else if (col.phase === "rain") {
        if (Math.random() < col.dropChance) dropColumn(col, rows)
        trimColumn(col, rainColors)
      }
    }

    if (col.visible.length > col.length) trimColumn(col, rainColors)
    col.fallLeft = col.fallDelay
  } else {
    col.fallLeft -= 1
  }

  for (var i = 0; i < col.visible.length; i++) {
    var ch = col.visible[i]
    if (Math.random() < CONFIG.symbolSwap) ch.ch = pick(SYMBOLS)
    if (Math.random() < CONFIG.colorSwap) ch.color = pick(rainColors)
  }
}

function makeColumns(cols, rows, lines, rainColors) {
  var bounds = brandBounds(lines, cols, rows)
  var pending = []
  for (var x = 0; x < cols; x++) {
    var chars = []
    for (var y = 0; y < rows; y++) {
      var input = brandAt(lines, cols, rows, x, y)
      chars.push({
        x: x,
        homeY: y,
        y: y,
        ch: " ",
        color: CONFIG.highlight,
        visible: false,
        resolving: false,
        input: input,
        finalColor: radialFinal(x, y, bounds, CONFIG.finalStops, CONFIG.finalSteps),
        resolveColors: null,
        resolveIndex: 0,
        resolveHold: 0
      })
    }
    var col = { chars: chars, pending: [], visible: [], phase: "rain", fallDelay: 1, fallLeft: 0, length: 1, holdTime: 0, dropChance: CONFIG.dropChance }
    setupColumn(col, "rain")
    pending.push(col)
  }
  return shuffle(pending)
}

function create(cols, rows, brandText, cellW, cellH, fontSize) {
  cols = Math.max(1, cols | 0)
  rows = Math.max(1, rows | 0)
  var lines = parseBrand(brandText)
  var rainColors = expandGradient(CONFIG.rainStops, CONFIG.rainGradientSteps)
  return {
    cols: cols,
    rows: rows,
    cellW: Math.max(1, cellW || 11),
    cellH: Math.max(1, cellH || 18),
    fontSize: Math.max(1, fontSize || 18),
    lines: lines,
    rainColors: rainColors,
    pending: makeColumns(cols, rows, lines, rainColors),
    active: [],
    full: [],
    resolving: [],
    settled: [],
    phase: "rain",
    columnDelay: 0,
    resolveWait: CONFIG.resolveDelay,
    rainComplete: false,
    finalFrameShown: false,
    rainStart: Date.now()
  }
}

function startResolve(ch) {
  var colors = expandGradient([CONFIG.highlight, ch.finalColor], CONFIG.resolveBlendSteps)
  ch.ch = ch.input
  ch.y = ch.homeY
  ch.visible = true
  ch.resolving = true
  ch.resolveColors = colors
  ch.resolveIndex = 0
  ch.resolveHold = CONFIG.finalFrames
  ch.color = colors[0]
}

function tickResolving(sim) {
  var kept = []
  for (var i = 0; i < sim.resolving.length; i++) {
    var ch = sim.resolving[i]
    if (!ch.resolving) continue
    ch.resolveHold -= 1
    if (ch.resolveHold <= 0) {
      ch.resolveIndex += 1
      ch.resolveHold = CONFIG.finalFrames
      if (ch.resolveIndex >= ch.resolveColors.length) {
        ch.color = ch.finalColor
        ch.resolving = false
        sim.settled.push(ch)
        continue
      }
      ch.color = ch.resolveColors[ch.resolveIndex]
    }
    kept.push(ch)
  }
  sim.resolving = kept
}

function collectDraw(sim) {
  var list = []
  function addCol(columns) {
    for (var i = 0; i < columns.length; i++) {
      var vis = columns[i].visible
      for (var j = 0; j < vis.length; j++) {
        if (vis[j].visible) list.push(vis[j])
      }
    }
  }
  addCol(sim.active)
  addCol(sim.full)
  for (var r = 0; r < sim.resolving.length; r++) {
    if (sim.resolving[r].visible) list.push(sim.resolving[r])
  }
  for (var s = 0; s < sim.settled.length; s++) {
    if (sim.settled[s].visible) list.push(sim.settled[s])
  }
  sim.draw = list
}

function tick(sim) {
  if (!sim) return false

  tickResolving(sim)

  if (sim.phase === "rain" || sim.phase === "fill") {
    if (!sim.columnDelay) {
      if (sim.phase === "rain") {
        var n = randInt(1, 3)
        for (var a = 0; a < n && sim.pending.length; a++) sim.active.push(sim.pending.shift())
        sim.columnDelay = randInt(CONFIG.columnDelayMin, CONFIG.columnDelayMax)
      } else {
        while (sim.pending.length) sim.active.push(sim.pending.shift())
        sim.columnDelay = 1
      }
    } else {
      sim.columnDelay -= 1
    }

    // Completed fill columns still shimmer while the others fill, but belong
    // only to full so collectDraw paints each glyph once. Tick them before
    // active columns so a column completed below is not ticked twice.
    for (var b = 0; b < sim.full.length; b++) tickColumn(sim.full[b], sim.rows, sim.rainColors)

    var stillActive = []
    for (var i = 0; i < sim.active.length; i++) {
      var col = sim.active[i]
      tickColumn(col, sim.rows, sim.rainColors)
      if (!col.pending.length) {
        if (col.phase === "fill") {
          sim.full.push(col)
          continue
        } else if (!col.visible.length) {
          setupColumn(col, sim.phase)
          sim.pending.push(col)
          continue
        }
      }
      if (col.visible.length) stillActive.push(col)
    }
    sim.active = stillActive

    if (sim.phase === "fill" && !sim.pending.length) {
      var filling = false
      for (var f = 0; f < sim.active.length; f++) {
        if (sim.active[f].pending.length || sim.active[f].phase !== "fill") filling = true
      }
      if (!filling) {
        sim.phase = "resolve"
        sim.active = []
      }
    }

    if (sim.phase === "rain" && Date.now() - sim.rainStart > CONFIG.rainTimeMs) {
      sim.rainComplete = true
      sim.phase = "fill"
      for (var d = 0; d < sim.active.length; d++) {
        sim.active[d].holdTime = 0
        sim.active[d].dropChance = 1
      }
      for (var p = 0; p < sim.pending.length; p++) setupColumn(sim.pending[p], "fill")
    }
  } else if (sim.phase === "resolve") {
    var stillFull = []
    for (var c = 0; c < sim.full.length; c++) {
      var column = sim.full[c]
      tickColumn(column, sim.rows, sim.rainColors)
      if (column.visible.length) {
        if (!sim.resolveWait) {
          var count = randInt(1, 4)
          for (var k = 0; k < count && column.visible.length; k++) {
            var idx = randInt(0, column.visible.length - 1)
            var next = column.visible.splice(idx, 1)[0]
            if (next.input !== " ") {
              startResolve(next)
              sim.resolving.push(next)
            } else {
              next.visible = false
            }
          }
          sim.resolveWait = CONFIG.resolveDelay
        } else {
          sim.resolveWait -= 1
        }
        if (column.visible.length) stillFull.push(column)
      }
    }
    sim.full = stillFull
  }

  var live = sim.full.length || sim.active.length || sim.resolving.length || sim.pending.length || !sim.rainComplete
  if (!live) {
    if (sim.finalFrameShown) return false
    sim.finalFrameShown = true
  }

  collectDraw(sim)
  return true
}

function paint(ctx, sim, width, height) {
  ctx.fillStyle = CONFIG.background
  ctx.fillRect(0, 0, width, height)
  if (!sim) return

  var cellW = sim.cellW
  var cellH = sim.cellH
  var ox = Math.floor((width - sim.cols * cellW) / 2)
  var oy = Math.floor((height - sim.rows * cellH) / 2)
  ctx.font = (sim.fontSize || cellH) + "px \"" + fontFamily + "\""
  ctx.textBaseline = "top"
  ctx.textAlign = "left"

  var list = sim.draw || []
  for (var i = 0; i < list.length; i++) {
    var ch = list[i]
    if (!ch.visible || ch.y < 0 || ch.y >= sim.rows) continue
    ctx.fillStyle = ch.color
    ctx.fillText(ch.ch, ox + ch.x * cellW, oy + ch.y * cellH)
  }
}

if (typeof module !== "undefined") {
  module.exports = {
    CONFIG: CONFIG,
    create: create,
    tick: tick,
    paint: paint,
    parseBrand: parseBrand,
    brandAt: brandAt,
    expandGradient: expandGradient
  }
}
