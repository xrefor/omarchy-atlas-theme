local function readable_comments()
  local path = vim.fn.expand("~/.config/atlas/neovim-readability")
  local info = (vim.uv or vim.loop).fs_lstat(path)
  if not info or info.type ~= "file" then return false end
  local file = io.open(path, "r")
  if not file then return false end
  local value = file:read(32) or ""
  file:close()
  return info.size <= 32 and vim.trim(value) == "readable"
end

local last_readability
return {
  {
    "bjarneo/aether.nvim",
    branch = "v3",
    name = "aether",
    priority = 1000,
    init = function()
      -- Refresh only on focus, with no timer or background process. Leave other
      -- colorschemes alone, and keep a single handler across template reloads.
      vim.api.nvim_create_autocmd("FocusGained", {
        group = vim.api.nvim_create_augroup("AtlasReadability", { clear = true }),
        callback = function()
          if vim.g.colors_name == "aether" and readable_comments() ~= last_readability then
            vim.cmd.colorscheme("aether")
          end
        end,
      })
    end,
    opts = {
      colors = {
        bg = "#100e0c",
        dark_bg = "#0a0908",
        darker_bg = "#050403",
        lighter_bg = "#1c1814",

        fg = "#d6cfc4",
        dark_fg = "#c4b8a8",
        light_fg = "#c4b8a8",
        bright_fg = "#f2ebe0",
        muted = "#3a342c",
        readable_comment = "#a59f96",

        red = "#c22e16",
        yellow = "#f0a202",
        orange = "#e24a0f",
        green = "#8a9a4a",
        cyan = "#6f9a92",
        blue = "#6a8aa0",
        magenta = "#a03c2a",
        brown = "#6a3a22",

        bright_red = "#e84528",
        bright_yellow = "#ffb020",
        bright_green = "#a8b85c",
        bright_cyan = "#8fb8b0",
        bright_blue = "#8aa8bc",
        bright_magenta = "#c45438",

        accent = "#ff5a12",
        cursor = "#f2ebe0",
        foreground = "#d6cfc4",
        background = "#100e0c",
        selection = "#2a160c",
        selection_foreground = "#100e0c",
        selection_background = "#ff5a12",
      },
      -- Navigation uses the UI accent; syntax and Git/diagnostic colors retain
      -- their semantic roles. Values follow the active Omarchy palette.
      on_highlights = function(hl, c)
        last_readability = readable_comments()
        if last_readability then
          for _, name in ipairs({ "Comment", "SpecialComment" }) do
            hl[name] = hl[name] or {}
            hl[name].fg = c.readable_comment
          end
        end
        hl.Directory = { fg = c.accent, bold = true }
        hl.CursorLine = { bg = c.lighter_bg }
        hl.CursorLineNr = { fg = c.accent, bold = true }

        hl.NeoTreeDirectoryIcon = { fg = c.accent }
        hl.NeoTreeDirectoryName = { fg = c.accent }
        hl.NeoTreeRootName = { fg = c.accent, bold = true }
        hl.NeoTreeFileName = { fg = c.fg }
        hl.NeoTreeFileNameOpened = { fg = c.fg }
        hl.NeoTreeCursorLine = { bg = c.selection }
        hl.NeoTreeIndentMarker = { fg = c.muted }
        hl.NeoTreeWinSeparator = { fg = c.muted }
        hl.NeoTreeTabActive = { fg = c.accent, bg = c.dark_bg, bold = true }
        hl.NeoTreeTabSeparatorActive = { fg = c.accent, bg = c.dark_bg }

        hl.SnacksPickerDirectory = { fg = c.accent }
        hl.SnacksPickerMatch = { fg = c.accent, bold = true }
        hl.SnacksPickerSelected = { fg = c.accent, bold = true }
        hl.SnacksPickerListCursorLine = { bg = c.selection }
        hl.SnacksPickerTree = { fg = c.muted }

        hl.NormalFloat = { fg = c.fg, bg = c.dark_bg }
        hl.FloatBorder = { fg = c.muted, bg = c.dark_bg }
        hl.FloatTitle = { fg = c.accent, bold = true }
        hl.Pmenu = { fg = c.fg, bg = c.dark_bg }
        hl.PmenuSel = { fg = c.bright_fg, bg = c.selection, bold = true }
        hl.PmenuMatch = { fg = c.accent, bold = true }
        hl.PmenuMatchSel = { fg = c.accent, bg = c.selection, bold = true }
        hl.Search = { fg = c.accent, bg = c.selection }
        hl.IncSearch = { fg = c.bg, bg = c.accent, bold = true }
        hl.CurSearch = { link = "IncSearch" }

        for _, name in ipairs({
          "BlinkCmpLabelMatch", "CmpItemAbbrMatch", "CmpItemAbbrMatchFuzzy",
          "BlinkCmpSignatureHelpActiveParameter", "NoiceCmdlineIcon",
          "NoiceCmdlineIconSearch", "NoiceCmdlinePopupTitle",
          "WhichKey", "WhichKeyGroup", "SnacksPickerPrompt",
          "SnacksPickerTitle", "SnacksInputTitle",
        }) do
          hl[name] = { fg = c.accent, bold = true }
        end
        for _, name in ipairs({
          "BlinkCmpMenu", "BlinkCmpDoc", "BlinkCmpSignatureHelp",
          "NoiceCmdlinePopup", "WhichKeyNormal", "WhichKeyFloat", "SnacksInputNormal",
        }) do
          hl[name] = { fg = c.fg, bg = c.dark_bg }
        end
        for _, name in ipairs({
          "BlinkCmpMenuBorder", "BlinkCmpDocBorder", "BlinkCmpSignatureHelpBorder",
          "WhichKeyBorder", "SnacksPickerBorder", "SnacksInputBorder",
        }) do
          hl[name] = { fg = c.muted, bg = c.dark_bg }
        end
        hl.NoiceCmdlinePopupBorder = { fg = c.accent, bg = c.dark_bg }
        hl.NoiceCmdlinePopupBorderSearch = { link = "NoiceCmdlinePopupBorder" }
        hl.BlinkCmpMenuSelection = { bg = c.selection }
        hl.BlinkCmpLabelDetail = { fg = c.dark_fg }
        hl.WhichKeyDesc = { fg = c.fg }
        hl.WhichKeyValue = { fg = c.dark_fg }
        hl.StatusLine = { fg = c.fg, bg = c.dark_bg }
        hl.StatusLineNC = { fg = c.dark_fg, bg = c.bg }

      end,
    },
  },
  {
    "nvim-lualine/lualine.nvim",
    optional = true,
    opts = function(_, opts)
      opts.options = opts.options or {}
      -- Lualine re-evaluates this function on ColorScheme. Resolve fresh colors
      -- so Omarchy's theme hotreload cannot leave yesterday's palette cached.
      opts.options.theme = function()
        if vim.g.colors_name ~= "aether" then return "auto" end
        local c = require("aether.colors").setup(require("aether.config").extend())
        local theme = {}
        for mode, color in pairs({
          normal = c.accent, command = c.accent, insert = c.green,
          visual = c.bright_magenta, replace = c.bright_red, terminal = c.green,
        }) do
          theme[mode] = {
            a = { fg = c.bg, bg = color, gui = "bold" },
            b = { fg = color, bg = c.dark_bg },
            c = { fg = c.fg, bg = c.bg },
          }
        end
        theme.inactive = {
          a = { fg = c.dark_fg, bg = c.dark_bg },
          b = { fg = c.dark_fg, bg = c.bg },
          c = { fg = c.dark_fg, bg = c.bg },
        }
        return theme
      end
    end,
  },
  {
    "LazyVim/LazyVim",
    opts = {
      colorscheme = "aether",
    },
  },
}
