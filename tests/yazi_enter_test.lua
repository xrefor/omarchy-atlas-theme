local plugin = dofile("components/apps/atlas-enter.lua")
local events = {}
ya = { emit = function(action, args) events[#events + 1] = {action, args} end }
cx = { active = { current = {} } }

cx.active.current.hovered = { cha = { is_dir = true } }
plugin.entry()
assert(#events == 1 and events[1][1] == "enter", "directories must stay in Yazi")

cx.active.current.hovered = { cha = { is_dir = false } }
plugin.entry()
assert(#events == 2 and events[2][1] == "open", "files must use the existing opener")
assert(next(events[2][2]) == nil, "do not force hovered-only opening or override file selection")

cx.active.current.hovered = nil
plugin.entry()
assert(#events == 2, "an empty directory must not launch an opener")
print("PASS: Yazi Enter navigates folders, preserves file opening, and ignores empty lists")
