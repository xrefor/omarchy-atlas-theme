-- Run with nvim --headless --clean -i NONE -l tests/neovim_ui_test.lua.
-- Uses installed plugins without fetching or changing the user's configuration.
local lazy = vim.fn.expand("~/.local/share/nvim/lazy/")
for _, plugin in ipairs({ "aether", "lualine.nvim" }) do
  if vim.fn.isdirectory(lazy .. plugin) == 0 then
    print("SKIP: Neovim UI integration needs installed " .. plugin)
    vim.cmd.qa()
    return
  end
  vim.opt.runtimepath:prepend(lazy .. plugin)
end
-- Redirect only this preference into a real temporary file. Installed plugins
-- still come from the reference home; no desktop/editor configuration is edited.
local preference = vim.fn.tempname()
local expand = vim.fn.expand
vim.fn.expand = function(path, ...)
  if path == "~/.config/atlas/neovim-readability" then return preference end
  return expand(path, ...)
end
local spec = dofile("neovim.lua")
spec[1].init()
local opts = vim.deepcopy(spec[1].opts)
local function apply(config)
  require("aether").setup(config)
  vim.cmd.colorscheme("aether")
end
local function hl(name) return vim.api.nvim_get_hl(0, { name = name, link = false }) end
opts.on_highlights = nil
apply(opts)
local semantic = {}
for _, name in ipairs({ "String", "Function", "Keyword", "Number", "DiagnosticError", "NeoTreeGitAdded", "NeoTreeGitModified", "BlinkCmpKindFunction", "@comment.todo", "@comment.error", "@comment.warning" }) do
  semantic[name] = hl(name)
end
local standard = { Comment = hl("Comment"), SpecialComment = hl("SpecialComment") }
opts = vim.deepcopy(spec[1].opts)
apply(opts)
local line = { options = {}, sections = { lualine_a = { "mode" }, lualine_b = { "branch" } } }
spec[2].opts(nil, line)
require("lualine").setup(line)
local function assert_ui(accent)
  local color = tonumber(accent:sub(2), 16)
  for _, name in ipairs({ "NeoTreeDirectoryName", "SnacksPickerMatch", "BlinkCmpLabelMatch", "NoiceCmdlinePopupBorder", "WhichKeyGroup", "FloatTitle" }) do
    assert(hl(name).fg == color, name .. " must follow the current accent")
  end
  assert(hl("lualine_a_normal").bg == color, "Lualine normal mode must use current accent")
  assert(hl("lualine_a_insert").bg == tonumber(opts.colors.green:sub(2), 16), "Insert mode retains its semantic color")
end
assert_ui(opts.colors.accent)
assert(hl("BlinkCmpMenuSelection").bg == tonumber(opts.colors.selection:sub(2), 16))
for name, before in pairs(semantic) do
  assert(vim.deep_equal(before, hl(name)), "Changed semantic color: " .. name)
end
local function focus() vim.api.nvim_exec_autocmds("FocusGained", {}) end
vim.fn.writefile({ "readable" }, preference)
focus()
for name, before in pairs(standard) do
  local expected = vim.deepcopy(before)
  expected.fg = tonumber(opts.colors.readable_comment:sub(2), 16)
  assert(vim.deep_equal(hl(name), expected), name .. " must change only foreground")
end
assert(vim.deep_equal(hl("@comment"), hl("Comment")), "Treesitter comments follow the preset")
for name, before in pairs(semantic) do
  assert(vim.deep_equal(before, hl(name)), "Readable preset changed semantic color: " .. name)
end
spec[1].init()
assert(#vim.api.nvim_get_autocmds({ group = "AtlasReadability" }) == 1, "No duplicate refresh handlers")
-- Palette regeneration updates the readable role along with the UI accent.
opts.colors.readable_comment = "#909090"
opts.colors.accent = "#6a8aa0"
apply(opts)
assert_ui(opts.colors.accent)
assert(hl("Comment").fg == 0x909090, "Readable comments follow the current palette")
vim.fn.writefile({ "standard" }, preference)
focus()
for name, before in pairs(standard) do
  assert(vim.deep_equal(hl(name), before), "Standard preset restores " .. name)
end
vim.cmd.colorscheme("habamax")
vim.fn.writefile({ "readable" }, preference)
focus()
assert(vim.g.colors_name == "habamax", "Preference changes must leave other colorschemes alone")
assert(line.options.theme() == "auto", "A different theme must use its own lualine colors")
apply(opts)
assert_ui(opts.colors.accent)
assert(hl("Comment").fg == 0x909090, "Returning to Aether restores the saved choice")
vim.fn.writefile({ "invalid" }, preference)
focus()
assert(vim.deep_equal(hl("Comment"), standard.Comment), "Invalid preferences safely use standard comments")
vim.fn.delete(preference)
vim.fn.expand = expand
print("PASS: editor UI, comment presets, focus refresh, semantic colors, lualine and theme switching")
vim.cmd.qa()
