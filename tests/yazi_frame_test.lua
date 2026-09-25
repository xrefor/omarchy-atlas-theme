-- Exercise layout geometry independently of Yazi, including its native padding.
local function rect(x, y, w, h)
  return setmetatable({ x = x, y = y, w = w, h = h }, {
    __index = { pad = function(self, p)
      return rect(self.x + math.min(p[4], self.w), self.y + math.min(p[1], self.h),
        math.max(0, self.w - p[2] - p[4]), math.max(0, self.h - p[1] - p[3]))
    end },
  })
end
local function element(kind, text)
  return {
    kind = kind, text = text,
    area = function(self, value) self.region = value; return self end,
    style = function(self, value) self.paint = value; return self end,
    type = function(self, value) self.border_type = value; return self end,
  }
end
ui = {
  Rect = function(a) return rect(a.x, a.y, a.w, a.h) end,
  Pad = function(...) return { ... } end,
  Text = function(text) return element("backing", text) end,
  Line = function(text) return element("label", text) end,
  Border = setmetatable({ PLAIN = "plain" }, { __call = function() return element("border") end }),
  Edge = { ALL = "all" },
}
th = { app = { overall = {} }, mgr = { border_style = {}, cwd = {} } }
local native_calls = 0
local function native(tab)
  native_calls = native_calls + 1
  local c = tab._chunks
  local inner = c[2].w > 0 and 0 or 1
  tab.children = {
    c[1]:pad({ 0, inner, 0, 1 }),
    c[2]:pad({ 0, 1, 0, 1 }),
    c[3]:pad({ 0, 1, 0, inner }),
  }
  return "native result"
end
local original_open, original_getenv = io.open, os.getenv
local preference, closes = nil, 0
os.getenv = function(key) assert(key == "HOME"); return "/test-home" end
io.open = function(path, mode)
  assert(path == "/test-home/.config/atlas/layout.conf" and mode == "r")
  if preference == nil then return nil end
  return {
    read = function(_, format) assert(format == "*a"); return preference end,
    close = function() closes = closes + 1 end,
  }
end
local function setup(value)
  preference = value
  Tab = { build = native }
  local plugin = dofile("components/apps/atlas-frame.lua")
  plugin:setup()
  return plugin
end
for _, value in ipairs({ "", "set -g @atlas-layout classic\n", "framed", "set -g @atlas-layout framed\nextra" }) do
  setup(value)
  assert(Tab.build == native, "invalid/Classic preferences must preserve native layout")
end
setup(nil)
assert(Tab.build == native, "missing preference must preserve native layout")
local plugin = setup("set -g @atlas-layout framed\n")
local installed = Tab.build
plugin:setup()
assert(Tab.build == installed, "repeated setup must not apply padding twice")
local function build(widths, height)
  local x, chunks = 0, {}
  for index, width in ipairs(widths) do
    chunks[index] = rect(x, 2, width, height)
    x = x + width
  end
  local prior = { kind = "user-decoration" }
  local tab = { _chunks = chunks, _base = { prior } }
  assert(Tab.build(tab) == "native result", "retain underlying build result")
  assert(tab._base[1] == prior, "preserve existing decoration")
  return tab, chunks
end
local function check_sections(widths, height)
  local tab, original = build(widths, height)
  local borders, backgrounds = 0, 0
  for _, item in ipairs(tab._base) do
    if item.kind == "border" then
      borders = borders + 1
      assert(item.paint == th.mgr.border_style and item.border_type == "plain")
    elseif item.kind == "backing" then
      backgrounds = backgrounds + 1
      assert(item.paint == th.app.overall)
    end
  end
  local visible = 0
  for index, area in ipairs(original) do
    if area.w > 0 then
      visible = visible + 1
      local child = tab.children[index]
      assert(child.x == area.x + 1 and child.y == area.y + 1,
        "native content must start inside the frame")
      assert(child.w == area.w - 2 and child.h == area.h - 2,
        "all native content must fit inside its complete border")
    else
      assert(tab.children[index].w == 0, "hidden parent must remain hidden")
    end
  end
  assert(borders == visible and backgrounds == visible)
end
check_sections({ 12, 50, 38 }, 28)
check_sections({ 0, 12, 88 }, 28)
check_sections({ 50, 0, 50 }, 28)
for _, dimensions in ipairs({ { { 3, 12, 9 }, 8 }, { { 12, 50, 38 }, 4 } }) do
  local tab, original = build(dimensions[1], dimensions[2])
  assert(tab._chunks == original and #tab._base == 1, "small windows need native content space")
end
-- The existing T plugin remains the source of expanded/restored proportions.
local preview = dofile("components/apps/atlas-preview.lua")
rt = { mgr = { ratio = { 1, 4, 3 } } }
local resizes = 0
ya = { emit = function(action) assert(action == "app:resize"); resizes = resizes + 1 end }
preview:entry()
check_sections({ rt.mgr.ratio[1] * 12, rt.mgr.ratio[2] * 12, rt.mgr.ratio[3] * 12 }, 20)
preview:entry()
check_sections({ rt.mgr.ratio[1] * 12, rt.mgr.ratio[2] * 12, rt.mgr.ratio[3] * 12 }, 20)
assert(resizes == 2 and native_calls == 7 and closes == 5)
io.open, os.getenv = original_open, original_getenv
print("PASS: Yazi framing preserves native geometry, fallback, user setup and T preview ratios")
