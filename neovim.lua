return {
  {
    "bjarneo/aether.nvim",
    branch = "v3",
    name = "aether",
    priority = 1000,
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
    },
  },
  {
    "LazyVim/LazyVim",
    opts = {
      colorscheme = "aether",
    },
  },
}
