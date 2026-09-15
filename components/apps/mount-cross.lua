-- ATLAS adaptation of MIT-licensed mount.yazi. See vendor/sources.json.
-- Disk actions use UDisks/Polkit, stop on unmount failures, and target removable media.
local M = {}

function M.fail(message)
  ya.notify { title = "Drives", content = message, timeout = 8, level = "error" }
end

function M.removable_sources()
  local output = Command("lsblk"):arg({ "-J", "-p", "-o", "PATH,TYPE,TRAN,RM,HOTPLUG,MOUNTPOINTS" }):output()
  local data = output and output.status.success and ya.json_decode(output.stdout)
  local sources = {}
  local function walk(node, eligible, drive)
    -- Optical tray ejection needs a different action than USB power-off.
    if node.type == "rom" then return end
    eligible = eligible or node.rm == true or node.rm == 1 or node.hotplug == true or node.hotplug == 1 or node.tran == "usb"
    drive = drive or node.path
    if eligible then
      sources[node.path] = { drive = drive, mounts = node.mountpoints or {} }
    end
    for _, child in ipairs(node.children or {}) do walk(child, eligible, drive) end
  end
  for _, node in ipairs(data and data.blockdevices or {}) do walk(node, false, nil) end
  return sources
end

local function run(action, src)
  local output, err = Command("udisksctl"):arg({ action, "-b", src, "--no-user-interaction" }):output()
  if output and (output.stderr or ""):find("org.freedesktop.UDisks2.Error.NotAuthorizedCanObtain", 1, true) then
    -- The desktop Polkit agent handles authentication; never collect sudo passwords here.
    local permit = ui.hide()
    output, err = Command("udisksctl"):arg({ action, "-b", src }):stdin(Command.INHERIT):output()
    permit:drop()
  end
  if not output or not output.status.success then
    M.fail(output and output.stderr or tostring(err))
    return false
  end
  return true
end

function M.operate(action, partition)
  if not partition or not partition.sub then return end
  if action ~= "mount" and action ~= "unmount" and action ~= "eject" then return end
  local sources = M.removable_sources()
  local entry = sources[partition.src]
  if not entry then M.fail("This drive is not removable media, or is no longer connected."); return end
  if action ~= "eject" then run(action, partition.src); return end
  -- Do not disturb mounted sibling volumes. The user can unmount those explicitly.
  for src, sibling in pairs(sources) do
    if src ~= partition.src and sibling.drive == entry.drive then
      for _, path in ipairs(sibling.mounts) do
        if type(path) == "string" and path ~= "" then
          M.fail("Unmount the other volumes on this drive before ejecting it."); return
        end
      end
    end
  end
  local mounted = false
  for _, path in ipairs(entry.mounts) do
    if type(path) == "string" and path ~= "" then mounted = true end
  end
  if mounted and not run("unmount", partition.src) then return end
  run("power-off", partition.src)
end

return M
