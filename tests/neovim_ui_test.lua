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
local spec = dofile("neovim.lua")
local opts = vim.deepcopy(spec[1].opts)
local function apply(config)
  require("aether").setup(config)
  vim.cmd.colorscheme("aether")
end
local function hl(name) return vim.api.nvim_get_hl(0, { name = name, link = false }) end
opts.on_highlights = nil
apply(opts)
local semantic = {}
for _, name in ipairs({ "String", "Function", "Keyword", "Number", "DiagnosticError", "NeoTreeGitAdded", "NeoTreeGitModified", "BlinkCmpKindFunction" }) do
  semantic[name] = hl(name)
end
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
opts.colors.accent = "#6a8aa0"
apply(opts)
assert_ui(opts.colors.accent)
vim.cmd.colorscheme("habamax")
assert(line.options.theme() == "auto", "A different theme must use its own lualine colors")
apply(opts)
assert_ui(opts.colors.accent)
print("PASS: editor UI, semantic colors, lualine and repeated theme switching")
vim.cmd.qa()
