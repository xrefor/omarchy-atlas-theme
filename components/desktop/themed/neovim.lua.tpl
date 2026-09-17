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
        bg = "{{ background }}",
        dark_bg = "{{ dark_background }}",
        darker_bg = "{{ darker_background }}",
        lighter_bg = "{{ lighter_background }}",

        fg = "{{ foreground }}",
        dark_fg = "{{ light_foreground }}",
        light_fg = "{{ light_foreground }}",
        bright_fg = "{{ bright_foreground }}",
        muted = "{{ muted }}",
        readable_comment = "{{ mix background foreground 75% }}",

        red = "{{ red }}",
        yellow = "{{ yellow }}",
        orange = "{{ orange }}",
        green = "{{ green }}",
        cyan = "{{ cyan }}",
        blue = "{{ blue }}",
        magenta = "{{ magenta }}",
        brown = "{{ brown }}",

        bright_red = "{{ bright_red }}",
        bright_yellow = "{{ bright_yellow }}",
        bright_green = "{{ bright_green }}",
        bright_cyan = "{{ bright_cyan }}",
        bright_blue = "{{ bright_blue }}",
        bright_magenta = "{{ bright_magenta }}",

        accent = "{{ accent }}",
        cursor = "{{ bright_foreground }}",
        foreground = "{{ foreground }}",
        background = "{{ background }}",
        selection = "{{ selection }}",
        selection_foreground = "{{ background }}",
        selection_background = "{{ accent }}",
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
