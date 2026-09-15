local script = arg[0] or "tests/mount_cross_test.lua"
local root = script:match("^(.*)/tests/[^/]+$") or "."

local calls = {}
local responses = {}
local notifications = {}
local fixtures = {}
local hide_count = 0
local drop_count = 0

local function status(success)
  return { success = success }
end

local function output(success, stdout, stderr)
  return { status = status(success), stdout = stdout or "", stderr = stderr or "" }
end

local function queue(value, err)
  responses[#responses + 1] = { value = value, err = err }
end

local function copy_array(values)
  local result = {}
  for i, value in ipairs(values) do result[i] = value end
  return result
end

Command = setmetatable({ INHERIT = {} }, {
  __call = function(_, program)
    local builder = { program = program, args = {} }

    function builder:arg(values)
      for _, value in ipairs(values) do self.args[#self.args + 1] = value end
      return self
    end

    function builder:stdin(value)
      self.input = value
      return self
    end

    function builder:output()
      calls[#calls + 1] = {
        program = self.program,
        args = copy_array(self.args),
        input = self.input,
      }
      local response = table.remove(responses, 1)
      if not response then error("unexpected command: " .. self.program, 2) end
      return response.value, response.err
    end

    return builder
  end,
})

ya = {
  json_decode = function(value)
    local fixture = fixtures[value]
    if not fixture then error("unknown JSON fixture: " .. tostring(value), 2) end
    return fixture
  end,
  notify = function(notification)
    notifications[#notifications + 1] = notification
  end,
}

ui = {
  hide = function()
    hide_count = hide_count + 1
    return {
      drop = function()
        drop_count = drop_count + 1
      end,
    }
  end,
}

local mount = assert(loadfile(root .. "/components/apps/mount-cross.lua"))()

local function reset()
  calls = {}
  responses = {}
  notifications = {}
  fixtures = {}
  hide_count = 0
  drop_count = 0
end

local function assert_equal(actual, expected, message)
  if actual ~= expected then
    error(string.format("%s: expected %s, got %s", message, tostring(expected), tostring(actual)), 2)
  end
end

local function assert_args(call, expected)
  assert_equal(#call.args, #expected, call.program .. " argument count")
  for i, value in ipairs(expected) do
    assert_equal(call.args[i], value, call.program .. " argument " .. i)
  end
end

local function assert_no_program(program)
  for _, call in ipairs(calls) do
    if call.program == program then error("unexpected program: " .. program, 2) end
  end
end

local function fixture(nodes)
  fixtures.lsblk = { blockdevices = nodes }
  queue(output(true, "lsblk"))
end

local function internal_drive()
  return {
    path = "/dev/nvme0n1",
    tran = "nvme",
    rm = false,
    hotplug = false,
    mountpoints = {},
    children = {
      {
        path = "/dev/nvme0n1p1",
        tran = "nvme",
        rm = false,
        hotplug = false,
        mountpoints = { "/boot" },
      },
    },
  }
end

local function usb_drive(first_mounts, second_mounts)
  local children = {
    {
      path = "/dev/sdb1",
      tran = "usb",
      rm = false,
      hotplug = true,
      mountpoints = first_mounts or {},
    },
  }
  if second_mounts then
    children[#children + 1] = {
      path = "/dev/sdb2",
      tran = "usb",
      rm = false,
      hotplug = true,
      mountpoints = second_mounts,
    }
  end
  return {
    path = "/dev/sdb",
    tran = "usb",
    rm = false,
    hotplug = true,
    mountpoints = {},
    children = children,
  }
end

local tests = {}

function tests.optical_drive_is_not_offered_as_usb_storage()
  fixture { { path = "/dev/sr0", type = "rom", tran = "usb", rm = true } }
  mount.operate("eject", { src = "/dev/sr0", sub = "sr0" })
  assert_equal(#calls, 1, "command count")
  assert_equal(#notifications, 1, "notification count")
  assert_no_program("udisksctl")
end

function tests.internal_drive_is_never_acted_on()
  fixture { internal_drive() }
  mount.operate("eject", { src = "/dev/nvme0n1p1", sub = "p1" })

  assert_equal(#calls, 1, "command count")
  assert_equal(calls[1].program, "lsblk", "discovery command")
  assert_equal(#notifications, 1, "notification count")
  assert_no_program("udisksctl")
end

function tests.failed_unmount_stops_power_off()
  fixture { usb_drive({ "/run/media/test-user/USB" }) }
  queue(output(false, "", "device is busy"))
  mount.operate("eject", { src = "/dev/sdb1", sub = "1" })

  assert_equal(#calls, 2, "command count")
  assert_equal(calls[2].program, "udisksctl", "unmount command")
  assert_args(calls[2], { "unmount", "-b", "/dev/sdb1", "--no-user-interaction" })
  assert_equal(#notifications, 1, "notification count")
  assert_equal(notifications[1].content, "device is busy", "unmount error")
end

function tests.mounted_sibling_refuses_eject()
  fixture { usb_drive({}, { "/run/media/test-user/USB-DATA" }) }
  mount.operate("eject", { src = "/dev/sdb1", sub = "1" })

  assert_equal(#calls, 1, "command count")
  assert_equal(#notifications, 1, "notification count")
  assert_equal(
    notifications[1].content,
    "Unmount the other volumes on this drive before ejecting it.",
    "sibling refusal"
  )
end

function tests.clean_unmounted_usb_powers_off()
  fixture { usb_drive({}) }
  queue(output(true))
  mount.operate("eject", { src = "/dev/sdb1", sub = "1" })

  assert_equal(#calls, 2, "command count")
  assert_equal(calls[2].program, "udisksctl", "power-off command")
  assert_args(calls[2], { "power-off", "-b", "/dev/sdb1", "--no-user-interaction" })
  assert_equal(#notifications, 0, "notification count")
end

function tests.mount_uses_an_argument_array()
  fixture { usb_drive({}) }
  queue(output(true))
  mount.operate("mount", { src = "/dev/sdb1", sub = "1" })

  assert_equal(#calls, 2, "command count")
  assert_equal(calls[2].program, "udisksctl", "mount command")
  assert_args(calls[2], { "mount", "-b", "/dev/sdb1", "--no-user-interaction" })
end

function tests.authorization_uses_interactive_udisks_without_sudo()
  fixture { usb_drive({}) }
  queue(output(
    false,
    "",
    "GDBus.Error:org.freedesktop.UDisks2.Error.NotAuthorizedCanObtain: authentication required"
  ))
  queue(output(true))
  mount.operate("mount", { src = "/dev/sdb1", sub = "1" })

  assert_equal(#calls, 3, "command count")
  assert_equal(calls[2].program, "udisksctl", "non-interactive command")
  assert_args(calls[2], { "mount", "-b", "/dev/sdb1", "--no-user-interaction" })
  assert_equal(calls[3].program, "udisksctl", "interactive command")
  assert_args(calls[3], { "mount", "-b", "/dev/sdb1" })
  assert_equal(calls[3].input, Command.INHERIT, "interactive stdin")
  assert_equal(hide_count, 1, "UI hide count")
  assert_equal(drop_count, 1, "UI permit drop count")
  assert_no_program("sudo")
  assert_no_program("gdbus")
end

local names = {}
for name in pairs(tests) do names[#names + 1] = name end
table.sort(names)

local passed = 0
for _, name in ipairs(names) do
  reset()
  local ok, err = pcall(tests[name])
  if ok then
    passed = passed + 1
    io.write("ok - ", name, "\n")
  else
    io.stderr:write("not ok - ", name, ": ", tostring(err), "\n")
  end
end

if passed ~= #names then os.exit(1) end
io.write(string.format("%d tests passed\n", passed))
