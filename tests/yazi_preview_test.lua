local plugin = dofile("components/apps/atlas-preview.lua")
local events = {}
rt = { mgr = { ratio = { 1, 4, 3 } } }
ya = { emit = function(action, args) events[#events + 1] = { action, args } end }

local function ratio_is(parent, current, preview)
  local ratio = rt.mgr.ratio
  return ratio[1] == parent and ratio[2] == current and ratio[3] == preview
end

for iteration = 1, 3 do
  plugin:entry()
  assert(ratio_is(0, 1, 7), "expanded preview must retain a navigable file list")
  plugin:entry()
  assert(ratio_is(1, 4, 3), "second invocation must restore the browsing layout")
end

-- Derive state from the live ratio, including a ratio changed by another plugin.
rt.mgr.ratio = { 1, 1, 1 }
plugin:entry()
assert(ratio_is(0, 1, 7), "external layout changes must not leave a stale toggle state")
plugin:entry()
assert(ratio_is(1, 1, 1), "custom browsing ratios must be restored")

-- A fresh plugin instance can recover from an already expanded layout.
local fresh = dofile("components/apps/atlas-preview.lua")
rt.mgr.ratio = { 0, 1, 7 }
fresh:entry()
assert(ratio_is(1, 4, 3), "an expanded layout without a saved ratio must use ATLAS defaults")
assert(#events == 9, "every layout change must refresh the UI and preview size")
for _, event in ipairs(events) do
  assert(event[1] == "app:resize" and next(event[2]) == nil,
    "use the native resize event without changing navigation or file selection")
end
print("PASS: Yazi preview expands, restores browsing, and refreshes on every toggle")
