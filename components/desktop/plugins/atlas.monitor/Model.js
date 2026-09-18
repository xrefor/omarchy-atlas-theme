function clampBrightness(value) {
  var n = Number(value)
  if (!isFinite(n)) return 1
  return Math.max(1, Math.min(100, Math.round(n)))
}

function scaleNumber(scale) {
  if ((typeof scale !== "number" && typeof scale !== "string")
      || String(scale).trim() === "") return NaN
  return Number(scale)
}

function normalizeScale(scale) {
  var n = scaleNumber(scale)
  if (!isFinite(n) || n <= 0) return ""
  var rounded = Math.round(n * 100) / 100
  return isFinite(rounded) && rounded > 0 ? String(rounded) : ""
}

function gcd(a, b) {
  while (b) {
    var remainder = a % b
    a = b
    b = remainder
  }
  return a
}

function cleanScale(scale, width, height) {
  var requested = scaleNumber(scale)
  var modeWidth = Number(width)
  var modeHeight = Number(height)
  if (!isFinite(requested) || !isFinite(modeWidth) || !isFinite(modeHeight)
      || requested <= 0 || modeWidth <= 0 || modeHeight <= 0) return ""

  var widthUnits = Math.round(modeWidth * 120)
  var heightUnits = Math.round(modeHeight * 120)
  if (!Number.isSafeInteger(widthUnits) || !Number.isSafeInteger(heightUnits)) return ""
  var divisor = gcd(widthUnits, heightUnits)
  var scaleUnits = Math.round(requested * 120)
  if (divisor <= 0 || scaleUnits <= 0 || !Number.isSafeInteger(scaleUnits)) return ""
  if (scaleUnits > divisor) scaleUnits = divisor
  while (divisor % scaleUnits !== 0) scaleUnits++
  return normalizeScale(scaleUnits / 120)
}

function matchingScaleIndex(scales, currentScale, width, height) {
  var current = scaleNumber(currentScale)
  if (!Array.isArray(scales) || !isFinite(current) || current <= 0) return -1

  var bestIndex = -1
  var bestDistance = Infinity
  var normalizedCurrent = normalizeScale(current)
  if (!normalizedCurrent) return -1
  for (var i = 0; i < scales.length; i++) {
    if (cleanScale(scales[i], width, height) !== normalizedCurrent) continue

    var distance = Math.abs(Number(scales[i]) - current)
    if (distance < bestDistance) {
      bestIndex = i
      bestDistance = distance
    }
  }
  return bestIndex
}

function availableScales(scales, width, height) {
  if (!Array.isArray(scales)) return []
  scales = scales.filter(function(scale) {
    var value = scaleNumber(scale)
    return isFinite(value) && value > 0
  })
  if (!isFinite(Number(width)) || !isFinite(Number(height))
      || Number(width) <= 0 || Number(height) <= 0) return scales.map(String)

  var byEffectiveScale = {}
  for (var i = 0; i < scales.length; i++) {
    var requested = Number(scales[i])
    var cleaned = cleanScale(requested, width, height)
    if (!cleaned) continue
    var effective = Number(cleaned)

    if (!isFinite(requested) || !isFinite(effective)) continue

    var key = normalizeScale(effective)
    var existing = byEffectiveScale[key]
    if (!existing || Math.abs(requested - effective) < existing.distance) {
      byEffectiveScale[key] = {
        value: String(scales[i]),
        index: i,
        distance: Math.abs(requested - effective)
      }
    }
  }

  return Object.keys(byEffectiveScale)
    .map(function(key) { return byEffectiveScale[key] })
    .sort(function(a, b) { return a.index - b.index })
    .map(function(candidate) { return candidate.value })
}

function brightnessName(percent) {
  var p = Math.round(percent)
  if (p >= 95) return "Sun blast"
  if (p >= 80) return "Solar flare"
  if (p >= 65) return "Golden hour"
  if (p >= 45) return "Even day"
  if (p >= 30) return "Soft glow"
  if (p >= 20) return "Lamp light"
  if (p >= 10) return "Candlelit"
  return "Night owl"
}

function parseDisplays(raw) {
  var displays = []
  try {
    displays = raw ? JSON.parse(String(raw)) : []
  } catch (e) {
    displays = []
  }
  if (!Array.isArray(displays)) displays = []
  // The producer emits named objects with a boolean enabled flag. Ignore
  // malformed rows so they cannot make the last-output guard count a phantom.
  var seen = Object.create(null)
  displays = displays.filter(function(display) {
    var valid = display && typeof display === "object" && !Array.isArray(display)
      && typeof display.name === "string" && display.name.trim().length > 0
      && typeof display.enabled === "boolean"
    if (!valid || seen[display.name]) return false
    seen[display.name] = true
    return true
  })

  var count = 0
  for (var i = 0; i < displays.length; i++) {
    if (displays[i] && displays[i].enabled) count++
  }

  return {
    displays: displays,
    enabledDisplayCount: count
  }
}

function parseNightlightState(raw, exitCode) {
  if (exitCode !== 0) return null
  var state
  try { state = JSON.parse(raw) } catch (e) { return null }
  if (!state || typeof state !== "object" || Array.isArray(state)
      || typeof state.enabled !== "boolean") return null
  // No running daemon is a valid Off state; the toggle command can start it.
  if (state.temperature !== null
      && (typeof state.temperature !== "number" || !isFinite(state.temperature)
          || state.temperature <= 0)) return null
  return { enabled: state.enabled, temperature: state.temperature }
}

if (typeof module !== "undefined") {
  module.exports = {
    clampBrightness: clampBrightness,
    normalizeScale: normalizeScale,
    cleanScale: cleanScale,
    matchingScaleIndex: matchingScaleIndex,
    availableScales: availableScales,
    brightnessName: brightnessName,
    parseDisplays: parseDisplays,
    parseNightlightState: parseNightlightState
  }
}
