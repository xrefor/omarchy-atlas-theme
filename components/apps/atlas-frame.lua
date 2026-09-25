--- @since 26.8.15

-- Frame native manager components, keeping their navigation, mouse handlers,
-- markers and preview sizing. Uses Yazi's supported Tab.build extension point.
local M = {}

local function enabled()
  local home = os.getenv("HOME")
  if not home then return false end
  local file = io.open(home .. "/.config/atlas/layout.conf", "r")
  if not file then return false end
  local preference = file:read("*a")
  file:close()
  return preference:match("^%s*set %-g @atlas%-layout framed%s*$") ~= nil
end

function M:setup()
  if self.installed or not enabled() then return end
  self.installed = true
  local build = Tab.build
  Tab.build = function(tab, ...)
    local sections = tab._chunks
    -- Decoration must not consume the last useful rows or a narrow file list.
    for _, area in ipairs(sections) do
      if area.w > 0 and (area.w < 6 or area.h < 5) then
        return build(tab, ...)
      end
    end
    local names = { "Parent", "Files", "Preview" }
    local framed = {}
    tab._base = tab._base or {}
    for index, area in ipairs(sections) do
      framed[index] = area
      if area.w > 0 then
        tab._base[#tab._base + 1] = ui.Text(""):area(area):style(th.app.overall)
        tab._base[#tab._base + 1] = ui.Border(ui.Edge.ALL)
          :area(area):type(ui.Border.PLAIN):style(th.mgr.border_style)
        local label = " " .. names[index] .. " "
        if area.w >= #label + 4 then
          tab._base[#tab._base + 1] = ui.Line(label)
            :area(ui.Rect { x = area.x + 2, y = area.y, w = area.w - 4, h = 1 })
            :style(th.mgr.cwd)
        end
        -- Native Current already pads both sides. Parent/Preview omit their
        -- inner padding when Current is visible, so reserve that border here.
        local right = index == 1 and sections[2].w > 0 and 1 or 0
        local left = index == 3 and sections[2].w > 0 and 1 or 0
        framed[index] = area:pad(ui.Pad(1, right, 1, left))
      end
    end
    tab._chunks = framed
    return build(tab, ...)
  end
end

return M
