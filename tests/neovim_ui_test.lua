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
-- Exercise custom style preferences as well as the defaults from Aether.
opts.styles = { comments = { italic = true }, keywords = { italic = true }, functions = { bold = true } }
local function apply(config)
  require("aether").setup(config)
  vim.cmd.colorscheme("aether")
end
local function hl(name) return vim.api.nvim_get_hl(0, { name = name, link = false }) end
local decorate = opts.on_highlights
opts.on_highlights = nil
apply(opts)
local semantic = {}
for _, name in ipairs({
  "String", "Function", "Constant", "Type", "@variable", "@variable.member", "@variable.parameter",
  "@property", "@lsp.type.property",
  "DiagnosticError", "DiagnosticWarn", "DiagnosticInfo", "DiagnosticHint",
  "DiagnosticVirtualTextError", "DiagnosticVirtualTextWarn", "DiagnosticUnderlineError",
  "NeoTreeGitAdded", "NeoTreeGitModified", "NeoTreeGitDeleted", "GitSignsAdd", "GitSignsDelete",
  "@comment.todo", "@comment.error", "@comment.warning", "@comment.note",
  "@constructor.tsx", "@tag.delimiter.tsx", "@tag.javascript", "@string.documentation",
}) do
  semantic[name] = hl(name)
end
local terminal = {}
for index = 0, 15 do terminal[index] = vim.g["terminal_color_" .. index] end
local text_roles = {
  secondary_text = {
    "Comment", "SpecialComment", "LineNr", "LineNrAbove", "LineNrBelow",
    "LspCodeLens", "LspCodeLensSeparator", "LspInlayHint", "DiagnosticUnnecessary",
    "BlinkCmpLabelDeprecated", "Delimiter",
    "@punctuation.bracket", "@punctuation.delimiter",
  },
  syntax_keyword = {
    "Keyword", "Conditional", "Repeat", "Exception", "Define",
    "@keyword", "@keyword.function", "@string.escape",
  },
  syntax_number = { "Number", "Boolean", "Float" },
  bright_yellow = { "@lsp.type.enumMember" },
}
local before_text = {}
for _, names in pairs(text_roles) do
  for _, name in ipairs(names) do before_text[name] = hl(name) end
end
opts.on_highlights = decorate
apply(opts)
local function color(value) return tonumber(value:sub(2), 16) end
local function assert_preserved()
  for name, before in pairs(semantic) do
    assert(vim.deep_equal(before, hl(name)), "Changed preserved semantic or language-specific highlight: " .. name)
  end
  for index = 0, 15 do
    assert(vim.g["terminal_color_" .. index] == terminal[index], "Changed ANSI color " .. index)
  end
end
local function assert_text_roles(brighter)
  for role, names in pairs(text_roles) do
    for _, name in ipairs(names) do
      local expected = vim.deepcopy(before_text[name])
      local comment = name == "Comment" or name == "SpecialComment"
      expected.fg = color(opts.colors[brighter and comment and "readable_comment" or role])
      assert(vim.deep_equal(hl(name), expected), name .. " must change only foreground for " .. role)
    end
  end
  assert(vim.deep_equal(hl("@comment"), hl("Comment")), "Treesitter comments follow the preset")
  for _, pair in ipairs({
    { "@number", "Number" }, { "@number.float", "Float" }, { "@boolean", "Boolean" },
    { "@keyword.conditional", "Conditional" }, { "@keyword.repeat", "Repeat" },
    { "@keyword.return", "@keyword" }, { "@keyword.exception", "Exception" },
  }) do
    assert(vim.deep_equal(hl(pair[1]), hl(pair[2])), pair[1] .. " must inherit its semantic role")
  end
end
local function assert_completion()
  for kind, role in pairs({
    Function = "blue", Method = "blue", Constructor = "yellow", Class = "yellow",
    Interface = "yellow", Struct = "yellow", Enum = "yellow", TypeParameter = "yellow",
    Constant = "bright_yellow", EnumMember = "bright_yellow", Parameter = "cyan",
    Field = "cyan", Property = "bright_cyan", Operator = "fg", Variable = "fg",
    Keyword = "syntax_keyword", Value = "syntax_number", Folder = "accent",
  }) do
    for _, prefix in ipairs({ "BlinkCmpKind", "CmpItemKind" }) do
      assert(hl(prefix .. kind).fg == color(opts.colors[role]), prefix .. kind .. " must use " .. role)
    end
  end
  for _, prefix in ipairs({ "BlinkCmpKind", "CmpItemKind" }) do
    for _, name in ipairs({ "@property", "@lsp.type.property" }) do
      assert(hl(prefix .. "Property").fg == hl(name).fg, prefix .. "Property must match " .. name)
    end
  end
end
local function luminance(rgb)
  local channels = { math.floor(rgb / 65536), math.floor(rgb / 256) % 256, rgb % 256 }
  local weights, value = { 0.2126, 0.7152, 0.0722 }, 0
  for index, channel in ipairs(channels) do
    channel = channel / 255
    value = value + weights[index] * (channel <= 0.04045 and channel / 12.92 or ((channel + 0.055) / 1.055) ^ 2.4)
  end
  return value
end
local function contrast(fg, bg)
  local a, b = luminance(fg), luminance(bg)
  return (math.max(a, b) + 0.05) / (math.min(a, b) + 0.05)
end
-- ATLAS's opaque code surfaces meet 4.5:1, including current/selected lines.
-- Compositor transparency is outside Neovim's control and is not measured here.
for _, name in ipairs({
  "Comment", "SpecialComment", "LineNr", "LspCodeLens", "LspInlayHint", "DiagnosticUnnecessary",
  "Keyword", "@keyword", "@keyword.function", "@string.escape", "Number", "Boolean", "Float",
  "@punctuation.bracket", "@punctuation.delimiter", "Function", "String", "Type", "@variable.parameter",
}) do
  for _, background in ipairs({ "Normal", "CursorLine", "Visual" }) do
    local ratio = contrast(hl(name).fg, hl(background).bg)
    assert(ratio >= 4.5, string.format("%s on %s contrast is only %.2f:1", name, background, ratio))
  end
end
assert(hl("FloatBorder").fg == color(opts.colors.muted), "Decorative borders retain the quiet muted role")
assert(hl("NeoTreeIndentMarker").fg == color(opts.colors.muted), "Indent guides retain the quiet muted role")
assert_text_roles(false)
assert_completion()
assert_preserved()
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
local function focus() vim.api.nvim_exec_autocmds("FocusGained", {}) end
vim.fn.writefile({ "readable" }, preference)
focus()
assert_text_roles(true)
assert_completion()
assert_preserved()
assert(luminance(hl("Comment").fg) > luminance(color(opts.colors.secondary_text)), "Brighter comments remain a distinct option")
spec[1].init()
assert(#vim.api.nvim_get_autocmds({ group = "AtlasReadability" }) == 1, "No duplicate refresh handlers")
-- Palette regeneration updates all derived reading roles along with the UI accent.
opts.colors.readable_comment = "#b0b0b0"
opts.colors.secondary_text = "#909090"
opts.colors.syntax_keyword = "#bc8190"
opts.colors.syntax_number = "#c5a56a"
opts.colors.accent = "#6a8aa0"
apply(opts)
assert_ui(opts.colors.accent)
assert_text_roles(true)
assert_completion()
vim.fn.writefile({ "standard" }, preference)
focus()
assert_text_roles(false)
assert_completion()
vim.cmd.colorscheme("habamax")
vim.fn.writefile({ "readable" }, preference)
focus()
assert(vim.g.colors_name == "habamax", "Preference changes must leave other colorschemes alone")
assert(line.options.theme() == "auto", "A different theme must use its own lualine colors")
apply(opts)
assert_ui(opts.colors.accent)
assert_text_roles(true)
assert_completion()
vim.fn.writefile({ "invalid" }, preference)
focus()
assert_text_roles(false)
assert_preserved()
vim.fn.delete(preference)
vim.fn.expand = expand
print("PASS: readable syntax and secondary text, semantic completion, preserved styles/signals, comment presets, focus refresh and theme switching")
vim.cmd.qa()
