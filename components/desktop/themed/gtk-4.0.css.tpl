/* Omarchy palette. Public libadwaita 1.9 color variables; retain
 * widget geometry, semantic status colors, and application behavior. */
@define-color accent_bg_color {{ accent }};
@define-color accent_fg_color {{ selection_foreground }};
@define-color accent_color {{ accent }};
@define-color window_bg_color {{ background }};
@define-color window_fg_color {{ foreground }};
@define-color view_bg_color {{ dark_background }};
@define-color view_fg_color {{ foreground }};
@define-color headerbar_bg_color {{ lighter_background }};
@define-color headerbar_fg_color {{ foreground }};
@define-color headerbar_backdrop_color {{ background }};
@define-color sidebar_bg_color {{ background }};
@define-color sidebar_fg_color {{ foreground }};
@define-color sidebar_backdrop_color {{ background }};
@define-color secondary_sidebar_bg_color {{ lighter_background }};
@define-color secondary_sidebar_fg_color {{ foreground }};
@define-color secondary_sidebar_backdrop_color {{ background }};
@define-color card_bg_color {{ lighter_background }};
@define-color card_fg_color {{ foreground }};
@define-color dialog_bg_color {{ lighter_background }};
@define-color dialog_fg_color {{ foreground }};
@define-color popover_bg_color {{ lighter_background }};
@define-color popover_fg_color {{ foreground }};

:root {
  --accent-bg-color: {{ accent }};
  --accent-fg-color: {{ selection_foreground }};
  --accent-color: {{ accent }};
  --window-bg-color: {{ background }};
  --window-fg-color: {{ foreground }};
  --view-bg-color: {{ dark_background }};
  --view-fg-color: {{ foreground }};
  --headerbar-bg-color: {{ lighter_background }};
  --headerbar-fg-color: {{ foreground }};
  --headerbar-border-color: {{ muted }};
  --headerbar-backdrop-color: {{ background }};
  --sidebar-bg-color: {{ background }};
  --sidebar-fg-color: {{ foreground }};
  --sidebar-backdrop-color: {{ background }};
  --sidebar-border-color: {{ muted }};
  --secondary-sidebar-bg-color: {{ lighter_background }};
  --secondary-sidebar-fg-color: {{ foreground }};
  --secondary-sidebar-backdrop-color: {{ background }};
  --secondary-sidebar-border-color: {{ muted }};
  --card-bg-color: {{ lighter_background }};
  --card-fg-color: {{ foreground }};
  --dialog-bg-color: {{ lighter_background }};
  --dialog-fg-color: {{ foreground }};
  --popover-bg-color: {{ lighter_background }};
  --popover-fg-color: {{ foreground }};
}
